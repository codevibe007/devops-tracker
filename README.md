# 🛰 DevOps Job Radar

Personal job-alert system: runs daily on GitHub Actions, finds DevOps jobs
matching your profile via the JSearch API, scores them 0–10, and publishes
a dashboard to Netlify (works with a private repo on the free plan).
Refresh on demand with one click from the dashboard's "Run radar now" link
(GitHub Actions manual trigger).

```
├── src/radar.py              # fetch → score → dedupe → export
├── data/jobs.db              # SQLite history (committed by the workflow)
├── data/jobs.json            # dashboard data (committed by the workflow)
├── dashboard/                # React + Vite + Tailwind static dashboard
├── tests/test_scoring.py     # pytest unit tests for scoring
├── netlify.toml              # Netlify build config for the dashboard
└── .github/workflows/
    └── radar.yml             # daily 8:00 AM IST run + manual trigger
```

## How it works

1. **Fetch** — two sources:
   - **JSearch API** (aggregates LinkedIn, Indeed, Glassdoor, Shine, company
     career pages, and 30+ other portals): 10 role keywords × 4 locations
     (Pune, Hyderabad, Bangalore, Remote India), 6 queries per day on a
     rotating schedule, jobs posted in the last 7 days (see quota note).
     Keywords include DevOps-adjacent titles (cloud engineer,
     infrastructure engineer, kubernetes engineer) so DevOps roles under
     different names are caught too — and both engines also match
     keywords inside descriptions, not just titles.
   - **Naukri** (via an Apify scraper actor, since Naukri isn't covered by
     the aggregator): the same role keywords, 0–8 yrs experience, last
     7 days, up to 60 listings per daily run, filtered to the target
     locations.
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

### 2. Get the Apify token (for the Naukri source)

1. Create a free account at <https://console.apify.com> (no card needed —
   the free plan includes **$5 of platform credits every month**).
2. In the console: **Settings → API & Integrations** → copy your
   **Personal API token** — that is your `APIFY_TOKEN`.

> 💰 **Naukri cost:** the scraper charges ~$0.0015 per listing on the free
> tier. The default 60 listings/day ≈ **$2.70/month**, well inside the $5
> free credits. Tune with a repository variable `MAX_NAUKRI_RESULTS`.
> Skipping this step is fine — without the token the radar simply runs
> with JSearch only.

### 3. Add the GitHub repository secrets

1. Push this repo to GitHub.
2. On GitHub: **Settings → Secrets and variables → Actions → New repository secret**.
3. Add `RAPIDAPI_KEY` (your JSearch key) and `APIFY_TOKEN` (from step 2).

### 4. Deploy the dashboard to Netlify

GitHub Pages requires a public repo on the free plan; Netlify's free tier
deploys private repos, so the dashboard is hosted there instead.

1. Go to <https://app.netlify.com> → **Sign up** → **Continue with GitHub**
   (authorize Netlify to access your repos).
2. **Add new site → Import an existing project → GitHub** → pick this repo.
3. Netlify reads `netlify.toml` automatically — the build settings
   (base `dashboard`, command `npm run build`, publish `dist`) are already
   filled in. Click **Deploy**.
4. Your dashboard URL is `https://<site-name>.netlify.app` (you can rename
   the site under **Site configuration → Site details → Change site name**).

Every time the daily radar workflow commits fresh data to `main`, Netlify
rebuilds and redeploys the dashboard automatically.

### 5. Test with a manual run

1. On GitHub: **Actions → Job Radar (daily) → Run workflow → Run workflow**.
2. Watch the run: it fetches jobs, updates `data/jobs.db` + `data/jobs.json`,
   and commits them — the commit triggers a Netlify rebuild with the fresh
   data (~1 minute).
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
  multi-cloud jobs appear in every matching tab. These tabs only show jobs
  whose stated experience overlaps **0–8 yrs**; postings that don't state
  experience are collected in a separate **No Exp Listed** tab, and jobs
  demanding more than 8 yrs minimum are hidden.
- Stat cards (New today / Total tracked / Applied / Avg match score) that
  recalculate per selected tab.
- Location filter pills (Pune / Hyderabad / Bangalore / Remote) with counts,
  combined with the active cloud tab.
- Job cards with skill tags and a match-score badge (green ≥ 8, amber 6–8,
  dimmed < 6), plus **Apply / Mark applied / Ignore** buttons.
- **Application pipeline tracking** — every job card has stage chips
  (📮 Applied → ✉️ Email Sent → 🎤 Interview → 🏆 Selected / 🚫 Rejected),
  each showing how long the job has been in that stage. The **🎯 My
  Pipeline** tab shows all tracked jobs as a kanban board with per-stage
  columns and quick-move controls. State persists in `localStorage`.
- Light/dark mode with a toggle (defaults to your system preference).
- **Refresh** button (re-reads the latest data) and **Run radar now ↗**
  link (admins only) that opens the GitHub Actions page.

## Access control (login)

The dashboard sits behind a login screen. Users live in
`dashboard/public/users.json` as salted SHA-256 entries — no plaintext
passwords in the repo.

- **Admins** see the Run radar button and the 🔐 **Admin panel**, where
  they can create users (member or admin) and change their own password.
  The panel generates the updated `users.json`; paste it into the GitHub
  edit page it links to, commit, and Netlify deploys the change in ~1 min.
- **Members** can view, filter, and track jobs.

> ⚠️ Honest scope: this is a static site, so the login is an access gate,
> not vault-grade security — the repo and job data are public. Triggering
> the radar workflow always requires GitHub write access regardless.
