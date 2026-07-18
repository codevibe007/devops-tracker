# Claude Code prompt — DevOps Job Radar

Copy everything below the line into Claude Code:

---

Build a complete "DevOps Job Radar" application for me. Personal job-alert
system that runs daily, finds DevOps jobs matching my profile, sends a
Telegram digest, and shows everything on a web dashboard.

## MY PROFILE (use for match scoring)
- Senior DevOps Engineer, 5 years experience, based in Pune, India
- Core: GCP (GKE, Cloud Deploy, Cloud SQL, Artifact Registry, Compute
  Engine, Secret Manager), Terraform, Kubernetes, Docker, Helm
- CI/CD: GitHub Actions, GitLab CI, ArgoCD (GitOps)
- DevSecOps: Trivy, Cosign, SonarQube, GitLab SAST, OIDC
- Programming: Python, Flask, PostgreSQL, Bash, Apache Airflow
- Certified: Google Cloud Associate Cloud Engineer
- Target roles: DevOps Engineer, Senior DevOps Engineer, GCP DevOps,
  Platform Engineer, SRE — 4 to 8 years experience range
- Locations: Pune (priority 1), Hyderabad, Bangalore, Remote (India)

## TECH STACK (all free tier — do not use paid services)
- Backend: Python 3.12 single script (src/radar.py) with modules for
  fetch, score, dedupe, notify
- Job source: JSearch API on RapidAPI (aggregates LinkedIn, Indeed,
  Naukri, Glassdoor). Read API key from env var RAPIDAPI_KEY.
- Storage: SQLite database (data/jobs.db) committed back to the repo by
  the workflow. Single table: jobs (id, title, company, location, url,
  source, posted_at, score, cloud_tags, status
  [new/notified/applied/ignored], created_at). Do NOT create separate
  tables per cloud — cloud_tags column handles categorization.
- cloud_tags: auto-tag each job by scanning title + description:
  "gcp" (GCP/GKE/Google Cloud), "aws" (AWS/EKS/ECS), "azure"
  (Azure/AKS), "multi" if 2+ clouds mentioned, "none" if no cloud named.
- Scheduler: GitHub Actions workflow (.github/workflows/radar.yml),
  cron "30 2 * * *" (= 8:00 AM IST). Also allow manual workflow_dispatch.
  Workflow: checkout -> run script -> commit updated jobs.db + jobs.json.
- Notifications: Telegram Bot API via plain HTTPS requests (no heavy
  libs). Env vars: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID.
- Frontend: React + Vite + Tailwind static dashboard in /dashboard,
  reads data/jobs.json (exported by the script each run). Deployable to
  GitHub Pages via a second workflow.

## BACKEND LOGIC
1. Query JSearch for each combination of: ["devops engineer",
   "senior devops engineer", "gcp devops", "aws devops", "azure devops",
   "platform engineer", "sre"]
   x ["Pune", "Hyderabad", "Bangalore", "Remote India"], jobs posted in
   last 24h. Respect free-tier rate limits (add small sleep between calls).
2. Normalize results into the jobs schema. Dedupe by URL and by
   (title + company) fuzzy match against SQLite history.
3. Score each job 0-10:
   +3 GCP/GKE mentioned, +2 Terraform, +1.5 Kubernetes/Docker,
   +1 ArgoCD/GitOps, +1 CI/CD (GitHub Actions/GitLab), +0.5 Python,
   +1 experience range overlaps 4-8 yrs, -2 requires 10+ yrs,
   -1 Azure/AWS-only with no GCP. Cap at 10, round to 1 decimal.
4. Jobs scoring >= 6 go into the Telegram digest, sorted Pune first,
   then Hyderabad, Bangalore, Remote, by score desc. Message format:
   score emoji + title + company + location + experience + link.
   Max 15 jobs per digest; if none found, send "no new matches today".
5. Export ALL tracked jobs to data/jobs.json for the dashboard.

## DASHBOARD (match this design)
- Header "DevOps job radar" + last-run timestamp
- 4 main tabs at the top: All DevOps / GCP / AWS / Azure — each tab
  filters the same job list by cloud_tags (multi-cloud jobs appear in
  every matching tab; All shows everything). Show job count per tab.
- 4 stat cards: New today, Total tracked, Applied, Avg match score
  (stats recalculate per selected tab)
- Filter pills: Pune / Hyderabad / Bangalore / Remote with counts
  (combines with the active cloud tab)
- Job cards: title, company, location, exp range, source portal,
  posted time, skill tags, match score badge (green >=8, amber 6-8,
  dimmed <6), buttons: Apply (opens URL), Mark applied, Ignore
- Mark applied / Ignore persist to localStorage (static site, no backend)
- Clean flat design, light/dark mode support

## DELIVERABLES
1. Full repo structure with all code files
2. .github/workflows/radar.yml (daily run) and deploy.yml (Pages deploy)
3. requirements.txt, dashboard package.json — pinned versions
4. .env.example listing RAPIDAPI_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
5. README.md with exact step-by-step setup: how to get the RapidAPI
   JSearch key, how to create the Telegram bot via @BotFather and get my
   chat_id, how to add the three GitHub repo secrets, how to enable
   GitHub Pages, and how to test with workflow_dispatch
6. Unit tests for the scoring function (pytest)

Build everything now, file by file. Ask me nothing — use sensible
defaults. When done, print the README setup steps so I can follow them.
