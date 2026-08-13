"""Unit tests for the scoring, experience-parsing, cloud-tagging, and rotation logic."""

import json
import sqlite3
import time
from datetime import datetime, timedelta, timezone

import pytest

import radar
from radar import extract_experience, score_job, tag_cloud


class TestScoreJob:
    def test_gcp_only(self):
        assert score_job("DevOps Engineer", "Experience with GCP required") == 3.0

    def test_gke_counts_as_gcp(self):
        assert score_job("Engineer", "Deploy workloads on GKE") == 3.0

    def test_terraform(self):
        assert score_job("Engineer", "Terraform IaC") == 2.0

    def test_kubernetes_and_docker_score_once(self):
        # Kubernetes/Docker is a single +1.5 bucket, not additive.
        assert score_job("Engineer", "Kubernetes and Docker daily") == 1.5

    def test_argocd_gitops(self):
        assert score_job("Engineer", "GitOps with ArgoCD") == 1.0

    def test_cicd(self):
        assert score_job("Engineer", "Pipelines in GitHub Actions") == 1.0

    def test_python(self):
        assert score_job("Engineer", "Scripting in Python") == 0.5

    def test_experience_overlap_bonus(self):
        assert score_job("Engineer", "5-7 years of experience") == 1.0

    def test_experience_10_plus_penalty(self):
        # -2 clamps to 0.
        assert score_job("Engineer", "Requires 10+ years experience") == 0.0

    def test_aws_only_penalty(self):
        # AWS with no GCP: -1, clamped to 0.
        assert score_job("Engineer", "AWS EKS experience") == 0.0

    def test_azure_only_penalty_offsets_terraform(self):
        assert score_job("Engineer", "Azure AKS with Terraform") == 1.0

    def test_no_penalty_when_gcp_present(self):
        # GCP + AWS: no -1 penalty.
        assert score_job("Engineer", "GCP and AWS multi-cloud") == 3.0

    def test_full_stack_caps_at_10(self):
        desc = (
            "GCP GKE Terraform Kubernetes Docker ArgoCD GitOps "
            "GitHub Actions Python 4-8 years experience"
        )
        assert score_job("Senior DevOps Engineer", desc) == 10.0

    def test_score_is_rounded_to_one_decimal(self):
        score = score_job("Engineer", "Kubernetes and Python")
        assert score == 2.0
        assert round(score, 1) == score

    def test_empty_description(self):
        assert score_job("DevOps Engineer", "") == 0.0

    def test_case_insensitive(self):
        assert score_job("engineer", "gcp terraform KUBERNETES") == 6.5


class TestExtractExperience:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("4-8 years of experience", (4, 8)),
            ("4 to 8 years", (4, 8)),
            ("8-4 yrs", (4, 8)),  # swapped bounds are normalized
            ("10+ years", (10, None)),
            ("minimum 6 years", (6, None)),
            ("at least 3 years", (3, None)),
            ("no experience mentioned", None),
        ],
    )
    def test_patterns(self, text, expected):
        assert extract_experience(text) == expected

    def test_overlap_bonus_at_boundaries(self):
        # 1-4 yrs touches the low boundary of the 4-8 target range.
        assert score_job("Engineer", "1-4 years experience") == 1.0
        # 8-12 yrs: min <= 8, so it still overlaps.
        assert score_job("Engineer", "8-12 years experience") == 1.0
        # 1-3 yrs: no overlap, no bonus.
        assert score_job("Engineer", "1-3 years experience") == 0.0


class TestTagCloud:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("Google Cloud Platform GKE", "gcp"),
            ("AWS EKS", "aws"),
            ("Azure AKS", "azure"),
            ("GCP and AWS", "gcp,aws"),
            ("GCP AWS Azure", "gcp,aws,azure"),
            ("On-prem Linux admin", "none"),
        ],
    )
    def test_tags(self, text, expected):
        assert tag_cloud(text) == expected


class TestQueryRotation:
    """The daily budget rotation must cover all combos and stay in quota."""

    def _conn(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript(radar.SCHEMA)
        return conn

    def test_budget_limits_daily_combos(self):
        conn = self._conn()
        assert len(radar.todays_combos(conn, 6)) == 6

    def test_rotation_covers_all_combos(self):
        conn = self._conn()
        total = len(radar.ROLES) * len(radar.LOCATIONS)
        seen = set()
        for _ in range(0, total, 6):
            cursor = int(radar.get_meta(conn, "fetch_cursor", "0"))
            combos = radar.todays_combos(conn, 6)
            seen.update(combos)
            radar.set_meta(conn, "fetch_cursor", str((cursor + len(combos)) % total))
        assert len(seen) == total

    def test_cursor_wraps_around(self):
        conn = self._conn()
        radar.set_meta(conn, "fetch_cursor", "26")  # near the end of 28
        combos = radar.todays_combos(conn, 6)
        assert len(combos) == 6
        assert combos[0] == [(r, l) for r in radar.ROLES for l in radar.LOCATIONS][26]

    def test_monthly_quota_within_free_tier(self):
        assert radar.DAILY_BUDGET * 31 <= 200

    def test_full_sweep_fits_inside_search_window(self):
        # Every combo must be re-queried at least once per 7-day search
        # window, or postings could fall through between visits.
        import math

        total = len(radar.ROLES) * len(radar.LOCATIONS)
        sweep_days = math.ceil(total / radar.DAILY_BUDGET)
        assert sweep_days <= 7, (
            f"{total} combos at {radar.DAILY_BUDGET}/day = {sweep_days}-day "
            "sweep, exceeding the 7-day search window"
        )


class TestDedupeWindow:
    """Exact repeats are always blocked; reposts after the window are not."""

    def _conn(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript(radar.SCHEMA)
        return conn

    def _job(self, **kw):
        base = {
            "id": "j1", "title": "DevOps Engineer", "company": "Infosys",
            "location": "Pune", "url": "https://x.com/1", "source": "LinkedIn",
            "posted_at": "2026-08-01T00:00:00+00:00", "score": 5.0,
            "cloud_tags": "gcp", "skills": "GCP", "experience": "4-8 yrs",
            "status": "new",
        }
        base.update(kw)
        return base

    def _store(self, conn, job, days_ago):
        created = (
            datetime.now(timezone.utc) - timedelta(days=days_ago)
        ).isoformat()
        conn.execute(
            "INSERT INTO jobs (id, title, company, url, source, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (job["id"], job["title"], job["company"], job["url"],
             job["source"], created),
        )
        conn.commit()

    def test_same_url_always_blocked_even_when_ancient(self):
        conn = self._conn()
        self._store(conn, self._job(), days_ago=500)
        assert radar.insert_new_jobs(conn, [self._job()]) == []

    def test_recent_repost_is_blocked(self):
        conn = self._conn()
        self._store(conn, self._job(), days_ago=5)
        repost = self._job(id="j2", url="https://x.com/2")
        assert radar.insert_new_jobs(conn, [repost]) == []

    def test_repost_after_window_is_accepted(self):
        # The whole point: an identical title+company posted months later
        # is a real new opening and must reach the dashboard.
        conn = self._conn()
        self._store(conn, self._job(), days_ago=radar.FUZZY_DUPE_WINDOW_DAYS + 10)
        repost = self._job(id="j2", url="https://x.com/2")
        assert len(radar.insert_new_jobs(conn, [repost])) == 1

    def test_different_company_never_deduped(self):
        conn = self._conn()
        self._store(conn, self._job(), days_ago=1)
        other = self._job(id="j3", url="https://x.com/3", company="Wipro")
        assert len(radar.insert_new_jobs(conn, [other])) == 1


class TestNaukriUnstatedExperience:
    """Naukri says "0 to 0 years" when a posting states no requirement."""

    def test_zero_to_zero_url_slug_is_unstated(self):
        job = radar.normalize_naukri({
            "jobId": "1", "title": "Senior DevOps Engineer", "company": "HighRadius",
            "location": "Hyderabad", "description": "GCP",
            "portalUrl": "https://www.naukri.com/job-listings-x-hyderabad-0-to-0-years-1",
        })
        assert job["experience"] == ""

    def test_zero_to_zero_dict_is_unstated(self):
        job = radar.normalize_naukri({
            "jobId": "2", "title": "DevOps Engineer", "company": "Acme",
            "location": "Pune", "experience": {"min": 0, "max": 0},
            "portalUrl": "https://www.naukri.com/job-listings-y-2",
        })
        assert job["experience"] == ""

    def test_real_range_still_kept(self):
        job = radar.normalize_naukri({
            "jobId": "3", "title": "DevOps Engineer", "company": "Acme",
            "location": "Pune", "experience": {"min": 0, "max": 5},
            "portalUrl": "https://www.naukri.com/job-listings-z-3",
        })
        assert job["experience"] == "0-5 yrs"

    def test_backfill_clears_stored_zero_zero(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript(radar.SCHEMA)
        conn.execute(
            "INSERT INTO jobs (id, title, url, source, experience) VALUES "
            "('nk-1','Senior DevOps','https://naukri.com/a-0-to-0-years-1',"
            "'Naukri','0-0 yrs')"
        )
        radar.backfill_naukri_experience(conn)
        row = conn.execute("SELECT experience FROM jobs WHERE id='nk-1'").fetchone()
        assert row["experience"] == ""


class TestExportWindow:
    """The feed must not grow without bound, but must not lose history."""

    def test_old_jobs_leave_the_feed_but_stay_in_the_db(self, tmp_path, monkeypatch):
        monkeypatch.setattr(radar, "JSON_PATH", tmp_path / "jobs.json")
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript(radar.SCHEMA)
        fresh = datetime.now(timezone.utc).isoformat()
        old = (
            datetime.now(timezone.utc)
            - timedelta(days=radar.EXPORT_WINDOW_DAYS + 5)
        ).isoformat()
        conn.execute(
            "INSERT INTO jobs (id, title, created_at) VALUES ('a','New',?)", (fresh,)
        )
        conn.execute(
            "INSERT INTO jobs (id, title, created_at) VALUES ('b','Old',?)", (old,)
        )
        conn.commit()

        exported = radar.export_json(conn)
        assert exported == 1, "only the recent job belongs in the feed"
        assert conn.execute("SELECT COUNT(*) c FROM jobs").fetchone()["c"] == 2, (
            "history must stay in SQLite so dedupe keeps working"
        )
        payload = json.loads((tmp_path / "jobs.json").read_text())
        assert [j["id"] for j in payload["jobs"]] == ["a"]


class TestQuotaBudget:
    """The free tier is 200 calls per cycle — never overspend it."""

    def test_unknown_quota_uses_default(self):
        assert radar.affordable_calls(None, None) == radar.DAILY_BUDGET

    def test_healthy_quota_gets_full_budget(self):
        assert radar.affordable_calls(200, 30 * 86400) == radar.DAILY_BUDGET

    def test_low_quota_rations_calls(self):
        # 60 left over 20 days, minus reserve -> 2/day, not the full 6.
        assert radar.affordable_calls(60, 20 * 86400) == 2

    def test_exhausted_quota_spends_nothing(self):
        assert radar.affordable_calls(0, 4 * 86400) == 0
        assert radar.affordable_calls(-1, 4 * 86400) == 0
        assert radar.affordable_calls(radar.QUOTA_RESERVE, 86400) == 0

    def test_never_exceeds_quota_over_a_full_cycle(self):
        # Simulate a 30-day cycle spending the planned budget each day and
        # confirm the plan never runs the balance negative.
        remaining = 200
        for day in range(30, 0, -1):
            spend = radar.affordable_calls(remaining, day * 86400)
            remaining -= spend
            assert remaining >= 0, f"overspent with {day} days left"
        assert remaining >= 0

    def test_topup_only_from_surplus(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript(radar.SCHEMA)
        # Plenty of quota, thin run -> top-up allowed.
        radar.set_meta(conn, "quota_remaining", "190")
        radar.set_meta(conn, "quota_reset_at", str(time.time() + 5 * 86400))
        assert radar.topup_budget(0, conn) > 0
        # Same thin run but scarce quota -> no top-up.
        radar.set_meta(conn, "quota_remaining", "20")
        radar.set_meta(conn, "quota_reset_at", str(time.time() + 20 * 86400))
        assert radar.topup_budget(0, conn) == 0
        # Healthy run -> never tops up regardless of quota.
        radar.set_meta(conn, "quota_remaining", "190")
        assert radar.topup_budget(radar.MIN_NEW_PER_RUN, conn) == 0

    def test_expired_cycle_resets_quota_view(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript(radar.SCHEMA)
        radar.set_meta(conn, "quota_remaining", "0")
        radar.set_meta(conn, "quota_reset_at", str(time.time() - 10))
        assert radar.load_quota(conn) == (None, None)


class TestRotationResilience:
    """A failed query must not cost its combo a turn in the rotation."""

    def _conn(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript(radar.SCHEMA)
        return conn

    def test_cursor_holds_when_nothing_answers(self, monkeypatch):
        conn = self._conn()
        monkeypatch.setattr(radar, "_jsearch_query", lambda *a, **k: ([], False))
        radar.fetch_jobs("key", conn, budget=6)
        assert radar.get_meta(conn, "fetch_cursor", "0") == "0"
        assert radar.get_meta(conn, "stuck_runs") == "1"

    def test_cursor_advances_only_past_answered_combos(self, monkeypatch):
        conn = self._conn()
        calls = {"n": 0}

        def fake(headers, query, window):
            calls["n"] += 1
            return ([], calls["n"] <= 2)  # first two answer, third fails

        monkeypatch.setattr(radar, "_jsearch_query", fake)
        monkeypatch.setattr(radar, "API_SLEEP_SECONDS", 0)
        radar.fetch_jobs("key", conn, budget=6)
        assert radar.get_meta(conn, "fetch_cursor") == "2"

    def test_forces_progress_after_repeated_total_failure(self, monkeypatch):
        conn = self._conn()
        monkeypatch.setattr(radar, "_jsearch_query", lambda *a, **k: ([], False))
        for _ in range(radar.STUCK_RUNS_BEFORE_SKIP):
            radar.fetch_jobs("key", conn, budget=6)
        assert radar.get_meta(conn, "fetch_cursor") == "1"
        assert radar.get_meta(conn, "stuck_runs") == "0"

    def test_zero_budget_makes_no_calls(self, monkeypatch):
        conn = self._conn()
        called = {"n": 0}

        def fake(*a, **k):
            called["n"] += 1
            return ([], True)

        monkeypatch.setattr(radar, "_jsearch_query", fake)
        assert radar.fetch_jobs("key", conn, budget=0) == []
        assert called["n"] == 0


class TestNormalizeNaukri:
    def _item(self, **overrides):
        base = {
            "jobId": "250718900001",
            "title": "Senior DevOps Engineer",
            "company": "Acme Tech",
            "location": "Pune, Maharashtra",
            "experience": "4-8 Yrs",
            "skills": ["GCP", "Terraform", "Kubernetes"],
            "createdDate": 1784448000000,
            "portalUrl": "https://www.naukri.com/job-listings-x-250718900001",
            "description": "GCP GKE Terraform Kubernetes ArgoCD pipelines",
        }
        base.update(overrides)
        return base

    def test_happy_path(self):
        job = radar.normalize_naukri(self._item())
        assert job["id"] == "nk-250718900001"
        assert job["source"] == "Naukri"
        assert job["company"] == "Acme Tech"
        assert job["cloud_tags"] == "gcp"
        assert job["experience"] == "4-8 yrs"
        assert job["score"] > 6

    def test_filters_out_non_target_locations(self):
        assert radar.normalize_naukri(self._item(location="Chennai, Tamil Nadu")) is None

    def test_remote_and_hybrid_locations_kept(self):
        assert radar.normalize_naukri(self._item(location="Remote")) is not None
        assert radar.normalize_naukri(self._item(location="Hybrid - Bengaluru")) is not None

    def test_missing_title_or_url_dropped(self):
        assert radar.normalize_naukri(self._item(title="")) is None
        assert radar.normalize_naukri(self._item(portalUrl="", url="", jdURL="")) is None

    def test_nested_company_dict_and_list_location(self):
        job = radar.normalize_naukri(
            self._item(company={"name": "Nested Corp"}, location=["Pune", "Hyderabad"])
        )
        assert job["company"] == "Nested Corp"
        assert "Pune" in job["location"]

    def test_epoch_millis_date_parsed(self):
        job = radar.normalize_naukri(self._item())
        assert job["posted_at"].startswith("2026-")

    def test_id_falls_back_to_url_hash(self):
        job = radar.normalize_naukri(self._item(jobId="", id=""))
        assert job["id"].startswith("nk-")
        assert len(job["id"]) > 3

    def test_experience_dict_shape(self):
        job = radar.normalize_naukri(self._item(experience={"min": 3, "max": 6}))
        assert job["experience"] == "3-6 yrs"

    def test_experience_dict_open_ended(self):
        job = radar.normalize_naukri(self._item(experience={"min": 5, "max": None}))
        assert job["experience"] == "5+ yrs"

    def test_experience_from_url_slug_fallback(self):
        job = radar.normalize_naukri(
            self._item(
                experience=None,
                portalUrl="https://www.naukri.com/job-listings-devops-acme-pune-0-to-3-years-220626503633",
            )
        )
        assert job["experience"] == "0-3 yrs"

    def test_backfill_from_url_slug(self):
        import sqlite3 as sq

        conn = sq.connect(":memory:")
        conn.row_factory = sq.Row
        conn.executescript(radar.SCHEMA)
        conn.execute(
            "INSERT INTO jobs (id, title, url, source, experience) VALUES "
            "('nk-1', 'DevOps', "
            "'https://www.naukri.com/job-listings-x-2-to-7-years-1', 'Naukri', '')"
        )
        radar.backfill_naukri_experience(conn)
        row = conn.execute("SELECT experience FROM jobs WHERE id='nk-1'").fetchone()
        assert row["experience"] == "2-7 yrs"
