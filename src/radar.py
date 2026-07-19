#!/usr/bin/env python3
"""DevOps Job Radar.

Daily job pipeline: fetch DevOps jobs from the JSearch API, score them
against a personal profile, dedupe against SQLite history, and export
everything to JSON for the dashboard.

Modules (sections below): fetch, score, dedupe/store, export.

Env vars:
    RAPIDAPI_KEY       - RapidAPI key for the JSearch API (required to fetch)
    APIFY_TOKEN        - Apify token for the Naukri scraper (optional)
    MAX_API_CALLS      - optional override of the daily JSearch query budget
    MAX_NAUKRI_RESULTS - optional override of listings per Naukri run
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "jobs.db"
JSON_PATH = DATA_DIR / "jobs.json"

# v5 of the JSearch API: the old /search endpoint was replaced by /search-v2,
# which returns {"data": {"jobs": [...], "cursor": "..."}}.
JSEARCH_URL = "https://jsearch.p.rapidapi.com/search-v2"


def load_dotenv(path: Path = ROOT / ".env") -> None:
    """Load KEY=value lines from a local .env file (no external dependency).

    Real environment variables take precedence; the file never overrides them.
    """
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value

ROLES = [
    "devops engineer",
    "senior devops engineer",
    "gcp devops",
    "aws devops",
    "azure devops",
    "platform engineer",
    "sre",
    # DevOps-in-substance roles that often carry different titles.
    # Rotation math: len(ROLES) * len(LOCATIONS) combos / DAILY_BUDGET per
    # day must stay <= the 7-day search window for lossless coverage
    # (10 * 4 / 6 = ~6.7 days — checked by a unit test).
    "cloud engineer",
    "infrastructure engineer",
    "kubernetes engineer",
]

LOCATIONS = ["Pune", "Hyderabad", "Bangalore", "Remote India"]

# Seconds to sleep between JSearch calls (free-tier friendliness).
API_SLEEP_SECONDS = 1.5

# JSearch free tier allows ~200 requests/month. 6 calls/day = ~180/month.
# Each run works through the next DAILY_BUDGET combos of the ROLES x
# LOCATIONS matrix (28 total), so every combo is queried every ~5 days;
# the 7-day search window below means no posting is missed in between.
DAILY_BUDGET = 6
SEARCH_WINDOW = "week"
# Until every combo has been swept once, look a month back so still-open
# older postings are captured on the first pass through the rotation.
BOOTSTRAP_WINDOW = "month"

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("radar")

# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

_GCP_RE = re.compile(r"\b(gcp|gke|google cloud)\b", re.I)
_AWS_RE = re.compile(r"\b(aws|eks|ecs|amazon web services)\b", re.I)
_AZURE_RE = re.compile(r"\b(azure|aks)\b", re.I)
_TERRAFORM_RE = re.compile(r"\bterraform\b", re.I)
_K8S_DOCKER_RE = re.compile(r"\b(kubernetes|k8s|docker)\b", re.I)
_GITOPS_RE = re.compile(r"\b(argo\s?cd|gitops)\b", re.I)
_CICD_RE = re.compile(r"\b(github actions|gitlab)\b", re.I)
_PYTHON_RE = re.compile(r"\bpython\b", re.I)

_EXP_RANGE_RE = re.compile(
    r"(\d{1,2})\s*(?:-|–|to)\s*(\d{1,2})\s*\+?\s*(?:years?|yrs?)", re.I
)
_EXP_PLUS_RE = re.compile(r"(\d{1,2})\s*\+\s*(?:years?|yrs?)", re.I)
_EXP_MIN_RE = re.compile(
    r"(?:minimum|min\.?|at least)\s*(?:of\s*)?(\d{1,2})\s*(?:years?|yrs?)", re.I
)

TARGET_EXP_MIN = 4
TARGET_EXP_MAX = 8


def extract_experience(text: str) -> tuple[int, int | None] | None:
    """Return (min_years, max_years) parsed from text, or None if absent.

    max_years is None for open-ended requirements like "10+ years".
    """
    m = _EXP_RANGE_RE.search(text)
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
        if lo > hi:
            lo, hi = hi, lo
        return (lo, hi)
    m = _EXP_PLUS_RE.search(text)
    if m:
        return (int(m.group(1)), None)
    m = _EXP_MIN_RE.search(text)
    if m:
        return (int(m.group(1)), None)
    return None


def experience_label(exp: tuple[int, int | None] | None) -> str:
    if exp is None:
        return ""
    lo, hi = exp
    return f"{lo}-{hi} yrs" if hi is not None else f"{lo}+ yrs"


def score_job(title: str, description: str) -> float:
    """Score a job 0-10 against the profile weights defined in the spec."""
    text = f"{title} {description}"
    score = 0.0

    has_gcp = bool(_GCP_RE.search(text))
    has_aws = bool(_AWS_RE.search(text))
    has_azure = bool(_AZURE_RE.search(text))

    if has_gcp:
        score += 3
    if _TERRAFORM_RE.search(text):
        score += 2
    if _K8S_DOCKER_RE.search(text):
        score += 1.5
    if _GITOPS_RE.search(text):
        score += 1
    if _CICD_RE.search(text):
        score += 1
    if _PYTHON_RE.search(text):
        score += 0.5

    exp = extract_experience(text)
    if exp is not None:
        lo, hi = exp
        if lo >= 10:
            score -= 2
        elif lo <= TARGET_EXP_MAX and (hi is None or hi >= TARGET_EXP_MIN):
            score += 1

    if (has_aws or has_azure) and not has_gcp:
        score -= 1

    return round(max(0.0, min(10.0, score)), 1)


def tag_cloud(text: str) -> str:
    """Comma-separated cloud tags: e.g. 'gcp', 'gcp,aws' (multi), or 'none'."""
    clouds = []
    if _GCP_RE.search(text):
        clouds.append("gcp")
    if _AWS_RE.search(text):
        clouds.append("aws")
    if _AZURE_RE.search(text):
        clouds.append("azure")
    return ",".join(clouds) if clouds else "none"


_SKILL_PATTERNS = [
    ("GCP", _GCP_RE),
    ("AWS", _AWS_RE),
    ("Azure", _AZURE_RE),
    ("Terraform", _TERRAFORM_RE),
    ("Kubernetes", re.compile(r"\b(kubernetes|k8s)\b", re.I)),
    ("Docker", re.compile(r"\bdocker\b", re.I)),
    ("Helm", re.compile(r"\bhelm\b", re.I)),
    ("ArgoCD", re.compile(r"\bargo\s?cd\b", re.I)),
    ("GitHub Actions", re.compile(r"\bgithub actions\b", re.I)),
    ("GitLab CI", re.compile(r"\bgitlab\b", re.I)),
    ("Jenkins", re.compile(r"\bjenkins\b", re.I)),
    ("Ansible", re.compile(r"\bansible\b", re.I)),
    ("Python", _PYTHON_RE),
    ("Prometheus", re.compile(r"\bprometheus\b", re.I)),
    ("Grafana", re.compile(r"\bgrafana\b", re.I)),
    ("CI/CD", re.compile(r"\bci/?cd\b", re.I)),
]


def extract_skills(text: str, limit: int = 8) -> list[str]:
    return [name for name, rx in _SKILL_PATTERNS if rx.search(text)][:limit]


# ---------------------------------------------------------------------------
# Fetch (JSearch API)
# ---------------------------------------------------------------------------


def todays_combos(conn: sqlite3.Connection, budget: int) -> list[tuple[str, str]]:
    """Next `budget` (role, location) combos in the rotation.

    A cursor persisted in the meta table advances each run, so all 28
    combos are covered every ~5 days while staying inside the free tier.
    """
    combos = [(r, l) for r in ROLES for l in LOCATIONS]
    cursor = int(get_meta(conn, "fetch_cursor", "0")) % len(combos)
    picked = [combos[(cursor + i) % len(combos)] for i in range(min(budget, len(combos)))]
    return picked


def fetch_jobs(api_key: str, conn: sqlite3.Connection) -> list[dict]:
    """Query JSearch for today's slice of the role x location rotation."""
    headers = {
        "X-RapidAPI-Key": api_key,
        "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
    }
    budget = int(os.environ.get("MAX_API_CALLS") or DAILY_BUDGET)
    combos = todays_combos(conn, budget)
    total = len(ROLES) * len(LOCATIONS)
    cursor = int(get_meta(conn, "fetch_cursor", "0")) % total
    lifetime = int(get_meta(conn, "total_fetches", "0"))
    window = BOOTSTRAP_WINDOW if lifetime < total else SEARCH_WINDOW
    log.info("Rotation: combos %d-%d of %d (budget %d/day, window: %s)",
             cursor + 1, cursor + len(combos), total, budget, window)

    raw: list[dict] = []
    attempted = 0
    for role, location in combos:
        query = f"{role} in {location}"
        attempted += 1
        try:
            resp = requests.get(
                JSEARCH_URL,
                headers=headers,
                params={
                    "query": query,
                    "num_pages": "1",
                    "date_posted": window,
                    "country": "in",
                },
                timeout=30,
            )
            if resp.status_code == 429:
                log.warning("Rate limited on %r; stopping fetch", query)
                break
            resp.raise_for_status()
            data = resp.json().get("data") or {}
            # v5 wraps results as {"jobs": [...], "cursor": ...}; tolerate the
            # old flat-list shape too.
            results = data.get("jobs", []) if isinstance(data, dict) else data
            log.info("%-45s -> %d results", query, len(results))
            raw.extend(results)
        except requests.RequestException as exc:
            log.warning("Fetch failed for %r: %s", query, exc)
        time.sleep(API_SLEEP_SECONDS)

    # Advance past every combo we attempted (even failed ones) so a bad
    # query can't wedge the rotation.
    set_meta(conn, "fetch_cursor", str((cursor + max(attempted, 1)) % total))
    set_meta(conn, "total_fetches", str(lifetime + attempted))
    return raw


def normalize(item: dict) -> dict | None:
    """Map a raw JSearch item onto the jobs schema. Returns None if unusable."""
    title = (item.get("job_title") or "").strip()
    company = (item.get("employer_name") or "").strip()
    url = item.get("job_apply_link") or item.get("job_google_link") or ""
    if not title or not url:
        return None

    description = item.get("job_description") or ""
    text = f"{title} {description}"

    if item.get("job_is_remote"):
        location = "Remote"
    else:
        parts = [item.get("job_city"), item.get("job_state")]
        location = ", ".join(p for p in parts if p) or (item.get("job_country") or "India")

    posted = item.get("job_posted_at_datetime_utc") or datetime.now(timezone.utc).isoformat()
    job_id = item.get("job_id") or hashlib.sha1(url.encode()).hexdigest()[:16]
    exp = extract_experience(text)

    return {
        "id": job_id,
        "title": title,
        "company": company,
        "location": location,
        "url": url,
        "source": item.get("job_publisher") or "JSearch",
        "posted_at": posted,
        "score": score_job(title, description),
        "cloud_tags": tag_cloud(text),
        "skills": ",".join(extract_skills(text)),
        "experience": experience_label(exp),
        "status": "new",
    }


# ---------------------------------------------------------------------------
# Fetch (Naukri via Apify actor)
# ---------------------------------------------------------------------------

# Naukri doesn't feed Google's jobs index, so JSearch barely covers it.
# The blackfalcondata/naukri-jobs-feed Apify actor scrapes it directly:
# ~$0.0015/listing on Apify's free tier ($5 free credits/month), so the
# default 60 listings/day costs ~$2.70/month.
APIFY_RUN_URL = (
    "https://api.apify.com/v2/acts/"
    "blackfalcondata~naukri-jobs-feed/run-sync-get-dataset-items"
)

NAUKRI_QUERIES = [
    "devops engineer",
    "gcp devops",
    "platform engineer",
    "sre",
    "cloud engineer",
    "infrastructure engineer",
    "kubernetes engineer",
]
NAUKRI_MAX_RESULTS = 60

_TARGET_LOCATION_RE = re.compile(
    r"pune|hyderabad|bangalore|bengaluru|remote|work from home|hybrid", re.I
)


def fetch_naukri(apify_token: str) -> list[dict]:
    """Run the Naukri scraper actor and return its raw listings."""
    payload = {
        "searchQueries": NAUKRI_QUERIES,
        "experience": "0-8",
        "freshness": 7,
        "sortBy": "date",
        "maxResults": int(os.environ.get("MAX_NAUKRI_RESULTS") or NAUKRI_MAX_RESULTS),
        "compact": True,
    }
    try:
        resp = requests.post(
            APIFY_RUN_URL,
            params={"token": apify_token},
            json=payload,
            timeout=320,
        )
        resp.raise_for_status()
        items = resp.json()
        if not isinstance(items, list):
            log.warning("Unexpected Apify response shape: %s", type(items).__name__)
            return []
        log.info("Naukri: %d raw listings", len(items))
        return items
    except (requests.RequestException, ValueError) as exc:
        log.warning("Naukri fetch failed: %s", exc)
        return []


def _flat_text(value) -> str:
    """Best-effort flatten of a possibly nested API value into a string."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, dict):
        for key in ("name", "label", "title", "text", "value"):
            if value.get(key):
                return _flat_text(value[key])
        return " ".join(_flat_text(v) for v in value.values() if v)
    if isinstance(value, list):
        return ", ".join(_flat_text(v) for v in value if v)
    return str(value)


def _parse_naukri_date(value) -> str:
    """Epoch millis/seconds or ISO string -> UTC ISO; falls back to now."""
    if isinstance(value, (int, float)) and value > 0:
        ts = value / 1000 if value > 1e12 else value
        try:
            return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
        except (OverflowError, OSError, ValueError):
            pass
    if isinstance(value, str) and value:
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).isoformat()
        except ValueError:
            pass
    return datetime.now(timezone.utc).isoformat()


# Naukri job URLs embed the range as ".../...-0-to-3-years-<jobid>".
_NAUKRI_URL_EXP_RE = re.compile(r"(\d{1,2})-to-(\d{1,2})-years")


def _naukri_experience(item: dict, url: str) -> str:
    """Experience label from the structured field, text, or the URL slug."""
    value = item.get("experience")
    if isinstance(value, dict):
        lo, hi = value.get("min"), value.get("max")
        if lo is not None and hi is not None:
            return f"{lo}-{hi} yrs"
        if lo is not None:
            return f"{lo}+ yrs"
    exp = extract_experience(_flat_text(value))
    if exp:
        return experience_label(exp)
    m = _NAUKRI_URL_EXP_RE.search(url)
    if m:
        return f"{int(m.group(1))}-{int(m.group(2))} yrs"
    return ""


def normalize_naukri(item: dict) -> dict | None:
    """Map a raw Naukri listing onto the jobs schema.

    Returns None for unusable items and for jobs outside the target
    locations (Pune / Hyderabad / Bangalore / Remote).
    """
    title = _flat_text(item.get("title") or item.get("jobTitle")).strip()
    url = _flat_text(
        item.get("portalUrl") or item.get("jdURL") or item.get("url")
    ).strip()
    if not title or not url:
        return None

    location = _flat_text(item.get("location") or item.get("placeholders")).strip()
    if not _TARGET_LOCATION_RE.search(location):
        return None

    company = _flat_text(item.get("company") or item.get("companyName")).strip()
    description = _flat_text(item.get("description"))
    skills_raw = _flat_text(item.get("skills") or item.get("tags"))
    experience = _naukri_experience(item, url)
    # Include the experience label so the experience scoring rules apply.
    score_text = f"{description} {skills_raw} {experience}"
    text = f"{title} {score_text}"

    job_id = _flat_text(item.get("jobId") or item.get("id")).strip()
    if not job_id:
        job_id = hashlib.sha1(url.encode()).hexdigest()[:16]

    return {
        "id": f"nk-{job_id}",
        "title": title,
        "company": company,
        "location": location,
        "url": url,
        "source": "Naukri",
        "posted_at": _parse_naukri_date(item.get("createdDate")),
        "score": score_job(title, score_text),
        "cloud_tags": tag_cloud(text),
        "skills": ",".join(extract_skills(text)),
        "experience": experience,
        "status": "new",
    }


def backfill_naukri_experience(conn: sqlite3.Connection) -> None:
    """One-off repair: fill empty experience on stored Naukri rows from
    the URL slug (rows inserted before _naukri_experience existed)."""
    rows = conn.execute(
        "SELECT id, url FROM jobs WHERE source = 'Naukri' "
        "AND (experience IS NULL OR experience = '')"
    ).fetchall()
    fixed = 0
    for row in rows:
        m = _NAUKRI_URL_EXP_RE.search(row["url"] or "")
        if m:
            conn.execute(
                "UPDATE jobs SET experience = ? WHERE id = ?",
                (f"{int(m.group(1))}-{int(m.group(2))} yrs", row["id"]),
            )
            fixed += 1
    if fixed:
        conn.commit()
        log.info("Backfilled experience for %d Naukri jobs", fixed)


# ---------------------------------------------------------------------------
# Dedupe / store (SQLite)
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    company     TEXT,
    location    TEXT,
    url         TEXT,
    source      TEXT,
    posted_at   TEXT,
    score       REAL,
    cloud_tags  TEXT,
    skills      TEXT,
    experience  TEXT,
    status      TEXT DEFAULT 'new',
    created_at  TEXT
);
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


def get_meta(conn: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()


def open_db() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def _norm_key(title: str, company: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", f"{title} {company}".lower()).strip()


def is_duplicate(conn: sqlite3.Connection, job: dict, seen_keys: list[str]) -> bool:
    """Duplicate if the URL exists in history or (title+company) fuzzy-matches."""
    row = conn.execute("SELECT 1 FROM jobs WHERE url = ? OR id = ?", (job["url"], job["id"])).fetchone()
    if row:
        return True
    key = _norm_key(job["title"], job["company"])
    for existing in seen_keys:
        if SequenceMatcher(None, key, existing).ratio() >= 0.92:
            return True
    return False


def insert_new_jobs(conn: sqlite3.Connection, jobs: list[dict]) -> list[dict]:
    """Insert non-duplicate jobs; return the ones actually inserted."""
    seen_keys = [
        _norm_key(r["title"], r["company"] or "")
        for r in conn.execute("SELECT title, company FROM jobs")
    ]
    inserted = []
    now = datetime.now(timezone.utc).isoformat()
    for job in jobs:
        if is_duplicate(conn, job, seen_keys):
            continue
        conn.execute(
            """INSERT INTO jobs (id, title, company, location, url, source,
                                 posted_at, score, cloud_tags, skills,
                                 experience, status, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                job["id"], job["title"], job["company"], job["location"],
                job["url"], job["source"], job["posted_at"], job["score"],
                job["cloud_tags"], job["skills"], job["experience"],
                job["status"], now,
            ),
        )
        seen_keys.append(_norm_key(job["title"], job["company"]))
        inserted.append(job)
    conn.commit()
    return inserted


# ---------------------------------------------------------------------------
# Export (dashboard JSON)
# ---------------------------------------------------------------------------


def export_json(conn: sqlite3.Connection) -> int:
    rows = conn.execute("SELECT * FROM jobs ORDER BY created_at DESC, score DESC").fetchall()
    jobs = []
    for r in rows:
        job = dict(r)
        job["skills"] = [s for s in (job.get("skills") or "").split(",") if s]
        jobs.append(job)
    payload = {
        "last_run": datetime.now(timezone.utc).isoformat(),
        "total": len(jobs),
        "jobs": jobs,
    }
    JSON_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return len(jobs)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    load_dotenv()
    api_key = os.environ.get("RAPIDAPI_KEY")
    apify_token = os.environ.get("APIFY_TOKEN")
    conn = open_db()

    normalized: list[dict] = []
    seen_urls: set[str] = set()

    def collect(job: dict | None) -> None:
        if job and job["url"] not in seen_urls:
            seen_urls.add(job["url"])
            normalized.append(job)

    if api_key:
        raw = fetch_jobs(api_key, conn)
        log.info("JSearch: fetched %d raw results", len(raw))
        for item in raw:
            collect(normalize(item))
    else:
        log.warning("RAPIDAPI_KEY not set; skipping JSearch fetch")

    if apify_token:
        for item in fetch_naukri(apify_token):
            collect(normalize_naukri(item))
    else:
        log.info("APIFY_TOKEN not set; skipping Naukri fetch")

    if normalized:
        inserted = insert_new_jobs(conn, normalized)
        log.info("Inserted %d new jobs (deduped from %d)", len(inserted), len(normalized))

    backfill_naukri_experience(conn)
    total = export_json(conn)
    log.info("Exported %d jobs to %s", total, JSON_PATH)
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
