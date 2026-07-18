# 🛰 DevOps Job Radar

Personal job-alert system: runs daily on GitHub Actions, finds DevOps jobs
matching your profile via the JSearch API, scores them 0–10, and publishes
a dashboard to GitHub Pages. Refresh on demand with one click from the
dashboard's "Run radar now" link (GitHub Actions manual trigger).

```
├── src/radar.py              # fetch → score → dedupe → notify → export
├── data/jobs.db              # SQLite history (committed by the workflow)
├── data/jobs.json            # dashboard data (committed by the workflow)
├── dashboard/                # React + Vite + Tailwind static dashboard
├── tests/test_scoring.py     # pytest unit tests for scoring
└── .github/workflows/
    ├── radar.yml             # daily 8:00 AM IST run + manual trigger
    └── deploy.yml            # GitHub Pages deploy
```

## How it works

1. **Fetch** — queries JSearch across 7 role keywords × 4 locations (Pune,
   Hyderabad, Bangalore, Remote India), 6 queries per day on a rotating
   schedule, jobs posted in the last 7 days (see quota note below).
2. **Score** — 0–10 against the profile: +3 GCP/GKE, +2 Terraform,
   +1.5 Kubernetes/Docker, +1 ArgoCD/GitOps, +1 CI/CD, +0.5 Python,
   +1 experience overlaps 4–8 yrs, −2 requires 10+ yrs, −1 AWS/Azure-only.
3. **Dedupe** — by URL and fuzzy (title + company) match against SQLite history.
4. **Export** — all tracked jobs to `data/jobs.json` for the dashboard.

## Setup (one time, ~15 minutes)

### 1. Get the RapidAPI JSearch key

1. Create a free account at <https://rapidapi.com>.
2. Open the JSearch API page: <https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch>.
3. Click **Subscribe to Test** → choose the **Basic (free)** plan.
4. On the API page, copy the value shown as **X-RapidAPI-Key** — that is your
   `RAPIDAPI_KEY`.

> ✅ **Free-tier quota — handled automatically.** The free JSearch plan allows
> ~200 requests/month, so the radar makes only **6 API calls per day**
> (~180/month) and **rotates** through all 28 role × location combos — each
> combo is queried every ~5 days with a **7-day search window**, so no posting
> is missed and the dedupe layer drops anything seen before. To change the
> daily budget, set a repository **variable** (not secret) named
> `MAX_API_CALLS` (Settings → Secrets and variables → Actions → Variables).

### 2. Add the GitHub repository secret

1. Push this repo to GitHub.
2. On GitHub: **Settings → Secrets and variables → Actions → New repository secret**.
3. Name: `RAPIDAPI_KEY`, Value: your key.

### 3. Enable GitHub Pages

1. On GitHub: **Settings → Pages**.
2. Under **Build and deployment → Source**, select **GitHub Actions**.
3. The `Deploy dashboard` workflow will publish the dashboard on the next
   push (or run it manually — see below). Your dashboard URL will be
   `https://<your-username>.github.io/<repo-name>/`.

### 4. Test with a manual run

1. On GitHub: **Actions → Job Radar (daily) → Run workflow → Run workflow**.
2. Watch the run: it fetches jobs, updates `data/jobs.db` + `data/jobs.json`,
   and commits them — which automatically triggers the Pages deploy with
   the fresh data.
3. From then on it runs automatically every day at **8:00 AM IST**
   (cron `30 2 * * *` UTC), and you can also trigger it any time from the
   dashboard's **Run radar now ↗** button (opens the same workflow page).

## Local development

```bash
# Backend
pip install -r requirements.txt
cp .env.example .env            # put your RAPIDAPI_KEY in it
python src/radar.py             # runs the full pipeline locally
pytest                          # run scoring unit tests

# Dashboard
cd dashboard
npm install
npm run dev                     # auto-copies ../data/jobs.json into public/
```

## Dashboard features

- Cloud tabs (**All DevOps / GCP / AWS / Azure**) with per-tab job counts —
  multi-cloud jobs appear in every matching tab.
- Stat cards (New today / Total tracked / Applied / Avg match score) that
  recalculate per selected tab.
- Location filter pills (Pune / Hyderabad / Bangalore / Remote) with counts,
  combined with the active cloud tab.
- Job cards with skill tags and a match-score badge (green ≥ 8, amber 6–8,
  dimmed < 6), plus **Apply / Mark applied / Ignore** buttons.
- Applied/Ignored state persists in `localStorage` (static site, no backend).
- Light/dark mode with a toggle (defaults to your system preference).
- **Refresh** button (re-reads the latest data) and **Run radar now ↗**
  link that opens the GitHub Actions page to trigger a fresh fetch.
