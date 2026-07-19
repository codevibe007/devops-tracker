"""Unit tests for the scoring, experience-parsing, cloud-tagging, and rotation logic."""

import sqlite3

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
