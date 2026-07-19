import { useEffect, useMemo, useState } from "react";

const TABS = [
  { id: "all", label: "All DevOps" },
  { id: "gcp", label: "GCP" },
  { id: "aws", label: "AWS" },
  { id: "azure", label: "Azure" },
  { id: "noexp", label: "No Exp Listed" },
];

// Main tabs only show jobs whose stated experience overlaps 0-8 yrs;
// postings that don't state experience live in the "No Exp Listed" tab.
const MAX_EXP_MIN_YEARS = 8;

const EXP_FILTERS = [
  { id: "0-2", label: "0-2 yrs", lo: 0, hi: 2 },
  { id: "2-4", label: "2-4 yrs", lo: 2, hi: 4 },
  { id: "4-6", label: "4-6 yrs", lo: 4, hi: 6 },
  { id: "6-8", label: "6-8 yrs", lo: 6, hi: 8 },
];

// Parse "4-8 yrs" -> {min:4, max:8}, "7+ yrs" -> {min:7, max:null}.
function expRange(job) {
  const range = /^(\d+)\s*-\s*(\d+)/.exec(job.experience || "");
  if (range) return { min: +range[1], max: +range[2] };
  const plus = /^(\d+)\+/.exec(job.experience || "");
  if (plus) return { min: +plus[1], max: null };
  return null;
}

function minExpYears(job) {
  const r = expRange(job);
  return r ? r.min : null;
}

function matchesExpFilter(job, filter) {
  if (!filter) return true;
  const r = expRange(job);
  if (!r) return false;
  return r.min <= filter.hi && (r.max === null || r.max >= filter.lo);
}

const AGE_OPTIONS = [
  { value: 7, label: "Last 7 days" },
  { value: 15, label: "Last 15 days" },
  { value: 30, label: "Last 30 days" },
];

function postedDaysAgo(job) {
  const t = new Date(job.posted_at || "").getTime();
  if (Number.isNaN(t)) return null;
  return (Date.now() - t) / 86_400_000;
}

function matchesAge(job, maxDays) {
  if (!maxDays) return true;
  const days = postedDaysAgo(job);
  return days !== null && days <= maxDays;
}

function matchesTab(job, tab) {
  const min = minExpYears(job);
  if (tab === "noexp") return min === null;
  if (min === null || min > MAX_EXP_MIN_YEARS) return false;
  return matchesCloud(job, tab);
}

const LOCATION_PILLS = ["Pune", "Hyderabad", "Bangalore", "Remote"];

const STATUS_KEY = "radar-status-overrides";
const THEME_KEY = "radar-theme";
const OWNER_KEY = "radar-owner";

// GitHub Actions page where the radar workflow can be triggered manually.
const RUN_WORKFLOW_URL =
  "https://github.com/codevibe007/devops-tracker/actions/workflows/radar.yml";

// Owner mode: visiting the site once with #owner marks this browser as the
// owner and reveals the run-workflow shortcut (#guest clears it). Cosmetic
// only — actually running the workflow requires GitHub write access.
function resolveOwner() {
  if (window.location.hash === "#owner") {
    localStorage.setItem(OWNER_KEY, "1");
    return true;
  }
  if (window.location.hash === "#guest") {
    localStorage.removeItem(OWNER_KEY);
    return false;
  }
  return localStorage.getItem(OWNER_KEY) === "1";
}

function loadOverrides() {
  try {
    return JSON.parse(localStorage.getItem(STATUS_KEY)) || {};
  } catch {
    return {};
  }
}

function matchesCloud(job, tab) {
  if (tab === "all") return true;
  return (job.cloud_tags || "").split(",").includes(tab);
}

function matchesLocation(job, pill) {
  if (!pill) return true;
  const loc = (job.location || "").toLowerCase();
  if (pill === "Bangalore") return loc.includes("bangalore") || loc.includes("bengaluru");
  return loc.includes(pill.toLowerCase());
}

function timeAgo(iso) {
  if (!iso) return "";
  const diff = Date.now() - new Date(iso).getTime();
  if (Number.isNaN(diff)) return "";
  const hours = Math.floor(diff / 3_600_000);
  if (hours < 1) return "just now";
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return days === 1 ? "1 day ago" : `${days} days ago`;
}

function isToday(iso) {
  if (!iso) return false;
  const d = new Date(iso);
  const now = new Date();
  return d.toDateString() === now.toDateString();
}

function scoreBadgeClass(score) {
  if (score >= 8)
    return "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/60 dark:text-emerald-300";
  if (score >= 6)
    return "bg-amber-100 text-amber-700 dark:bg-amber-900/60 dark:text-amber-300";
  return "bg-slate-100 text-slate-400 dark:bg-slate-800 dark:text-slate-500";
}

function StatCard({ label, value }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
      <div className="text-2xl font-semibold text-slate-900 dark:text-slate-100">{value}</div>
      <div className="mt-1 text-sm text-slate-500 dark:text-slate-400">{label}</div>
    </div>
  );
}

function JobCard({ job, status, onSetStatus }) {
  const ignored = status === "ignored";
  const applied = status === "applied";
  return (
    <div
      className={`rounded-xl border border-slate-200 bg-white p-4 transition dark:border-slate-800 dark:bg-slate-900 ${
        ignored ? "opacity-40" : ""
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="truncate font-semibold text-slate-900 dark:text-slate-100">
            {job.title}
          </h3>
          <div className="mt-1.5 flex items-center gap-2">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-blue-100 text-xs font-bold uppercase text-blue-700 dark:bg-blue-900/60 dark:text-blue-300">
              {(job.company || "?").trim().charAt(0)}
            </span>
            <span className="truncate text-sm font-semibold text-slate-700 dark:text-slate-200">
              {job.company || "Company not listed"}
            </span>
          </div>
          <p className="mt-1 truncate text-sm text-slate-600 dark:text-slate-400">
            {job.location}
            {job.experience ? ` · ${job.experience}` : " · exp not stated"}
          </p>
          <p className="mt-0.5 text-xs text-slate-400 dark:text-slate-500">
            {job.source} · {timeAgo(job.posted_at)}
          </p>
        </div>
        <span
          className={`shrink-0 rounded-full px-2.5 py-1 text-sm font-semibold ${scoreBadgeClass(job.score)}`}
          title="Match score"
        >
          {Number(job.score).toFixed(1)}
        </span>
      </div>

      {job.skills?.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {job.skills.map((s) => (
            <span
              key={s}
              className="rounded-md bg-slate-100 px-2 py-0.5 text-xs text-slate-600 dark:bg-slate-800 dark:text-slate-300"
            >
              {s}
            </span>
          ))}
        </div>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <a
          href={job.url}
          target="_blank"
          rel="noreferrer"
          className="rounded-lg bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700"
        >
          Apply
        </a>
        {applied ? (
          <button
            onClick={() => onSetStatus(job.id, null)}
            className="rounded-lg bg-emerald-100 px-3 py-1.5 text-sm font-medium text-emerald-700 dark:bg-emerald-900/60 dark:text-emerald-300"
          >
            ✓ Applied — undo
          </button>
        ) : (
          <button
            onClick={() => onSetStatus(job.id, "applied")}
            className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
          >
            Mark applied
          </button>
        )}
        {ignored ? (
          <button
            onClick={() => onSetStatus(job.id, null)}
            className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-500 dark:border-slate-700 dark:text-slate-400"
          >
            Ignored — undo
          </button>
        ) : (
          <button
            onClick={() => onSetStatus(job.id, "ignored")}
            className="rounded-lg px-3 py-1.5 text-sm text-slate-400 hover:text-slate-600 dark:hover:text-slate-300"
          >
            Ignore
          </button>
        )}
      </div>
    </div>
  );
}

export default function App() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [tab, setTab] = useState("all");
  const [locationPill, setLocationPill] = useState(null);
  const [expFilter, setExpFilter] = useState(null);
  const [maxAge, setMaxAge] = useState(null);
  const [companyFilter, setCompanyFilter] = useState("");
  const [overrides, setOverrides] = useState(loadOverrides);
  const [dark, setDark] = useState(() =>
    document.documentElement.classList.contains("dark")
  );
  const [refreshing, setRefreshing] = useState(false);
  const [isOwner, setIsOwner] = useState(resolveOwner);

  useEffect(() => {
    const onHash = () => setIsOwner(resolveOwner());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const loadData = () => {
    setRefreshing(true);
    fetch(`${import.meta.env.BASE_URL}jobs.json?t=${Date.now()}`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((e) => setError(e.message))
      .finally(() => setRefreshing(false));
  };

  useEffect(loadData, []);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    localStorage.setItem(THEME_KEY, dark ? "dark" : "light");
  }, [dark]);

  const setStatus = (id, status) => {
    setOverrides((prev) => {
      const next = { ...prev };
      if (status) next[id] = status;
      else delete next[id];
      localStorage.setItem(STATUS_KEY, JSON.stringify(next));
      return next;
    });
  };

  const jobs = useMemo(() => {
    const list = (data?.jobs || []).map((j) => ({
      ...j,
      effectiveStatus: overrides[j.id] || j.status,
    }));
    return list.sort((a, b) => b.score - a.score);
  }, [data, overrides]);

  const tabJobs = useMemo(() => jobs.filter((j) => matchesTab(j, tab)), [jobs, tab]);
  const visibleJobs = useMemo(
    () =>
      tabJobs
        .filter((j) => matchesLocation(j, locationPill))
        .filter((j) => matchesExpFilter(j, expFilter))
        .filter((j) => matchesAge(j, maxAge))
        .filter(
          (j) =>
            !companyFilter ||
            (j.company || "").trim().toLowerCase() === companyFilter
        ),
    [tabJobs, locationPill, expFilter, maxAge, companyFilter]
  );

  // Alphabetical company list (with per-company counts) for the dropdown,
  // derived from the current tab so the options stay relevant. Case
  // variants from different job boards ("Deloitte"/"deloitte") merge into
  // one entry keyed by the lowercased name.
  const companies = useMemo(() => {
    const groups = new Map();
    for (const j of tabJobs) {
      const name = (j.company || "").trim();
      if (!name) continue;
      const key = name.toLowerCase();
      const g = groups.get(key);
      if (g) g.count += 1;
      else groups.set(key, { key, name, count: 1 });
    }
    return [...groups.values()].sort((a, b) =>
      a.name.localeCompare(b.name, undefined, { sensitivity: "base" })
    );
  }, [tabJobs]);

  const stats = useMemo(() => {
    const newToday = tabJobs.filter((j) => isToday(j.created_at)).length;
    const applied = tabJobs.filter((j) => j.effectiveStatus === "applied").length;
    const avg =
      tabJobs.length > 0
        ? (tabJobs.reduce((s, j) => s + (j.score || 0), 0) / tabJobs.length).toFixed(1)
        : "—";
    return { newToday, total: tabJobs.length, applied, avg };
  }, [tabJobs]);

  return (
    <div className="mx-auto max-w-5xl px-4 py-8 text-slate-900 dark:text-slate-100">
      {/* Header */}
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">🛰 DevOps job radar</h1>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            {data?.last_run
              ? `Last run: ${new Date(data.last_run).toLocaleString()}`
              : "No runs yet"}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={loadData}
            disabled={refreshing}
            className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm disabled:opacity-50 dark:border-slate-700"
            title="Reload the latest data"
          >
            {refreshing ? "⏳ Refreshing…" : "🔄 Refresh"}
          </button>
          {isOwner && (
            <a
              href={RUN_WORKFLOW_URL}
              target="_blank"
              rel="noreferrer"
              className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm dark:border-slate-700"
              title="Open GitHub Actions to trigger a fresh fetch"
            >
              ▶ Run radar now ↗
            </a>
          )}
          <button
            onClick={() => setDark((d) => !d)}
            className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm dark:border-slate-700"
            title="Toggle light/dark mode"
          >
            {dark ? "☀️ Light" : "🌙 Dark"}
          </button>
        </div>
      </header>

      {error && (
        <div className="mt-6 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
          Could not load jobs.json ({error}). Run the radar workflow first.
        </div>
      )}

      {/* Cloud tabs */}
      <nav className="mt-6 flex flex-wrap gap-1 rounded-xl bg-slate-100 p-1 dark:bg-slate-900">
        {TABS.map((t) => {
          const count = jobs.filter((j) => matchesTab(j, t.id)).length;
          const active = tab === t.id;
          return (
            <button
              key={t.id}
              onClick={() => {
                setTab(t.id);
                // The exp filter is meaningless for jobs without a stated
                // experience, so clear it when entering that tab.
                if (t.id === "noexp") setExpFilter(null);
                // Company options are derived per tab; keep the selection
                // from pointing at a company the new tab doesn't contain.
                setCompanyFilter("");
              }}
              className={`rounded-lg px-4 py-2 text-sm font-medium transition ${
                active
                  ? "bg-white text-slate-900 shadow-sm dark:bg-slate-700 dark:text-white"
                  : "text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200"
              }`}
            >
              {t.label}
              <span className="ml-1.5 text-xs opacity-60">{count}</span>
            </button>
          );
        })}
      </nav>

      {/* Stat cards */}
      <section className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard label="New today" value={stats.newToday} />
        <StatCard label="Total tracked" value={stats.total} />
        <StatCard label="Applied" value={stats.applied} />
        <StatCard label="Avg match score" value={stats.avg} />
      </section>

      {/* Location pills */}
      <div className="mt-6 flex flex-wrap gap-2">
        {LOCATION_PILLS.map((pill) => {
          const count = tabJobs.filter((j) => matchesLocation(j, pill)).length;
          const active = locationPill === pill;
          return (
            <button
              key={pill}
              onClick={() => setLocationPill(active ? null : pill)}
              className={`rounded-full border px-3 py-1 text-sm transition ${
                active
                  ? "border-blue-600 bg-blue-600 text-white"
                  : "border-slate-300 text-slate-600 hover:border-slate-400 dark:border-slate-700 dark:text-slate-300"
              }`}
            >
              {pill} <span className="opacity-60">{count}</span>
            </button>
          );
        })}
      </div>

      {/* Experience pills (not shown on the No Exp Listed tab) */}
      {tab !== "noexp" && (
        <div className="mt-2 flex flex-wrap gap-2">
          {EXP_FILTERS.map((f) => {
            const count = tabJobs.filter((j) => matchesExpFilter(j, f)).length;
            const active = expFilter?.id === f.id;
            return (
              <button
                key={f.id}
                onClick={() => setExpFilter(active ? null : f)}
                className={`rounded-full border px-3 py-1 text-sm transition ${
                  active
                    ? "border-emerald-600 bg-emerald-600 text-white"
                    : "border-slate-300 text-slate-600 hover:border-slate-400 dark:border-slate-700 dark:text-slate-300"
                }`}
              >
                {f.label} <span className="opacity-60">{count}</span>
              </button>
            );
          })}
        </div>
      )}

      {/* Posted-age and company dropdowns */}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <select
          value={maxAge ?? ""}
          onChange={(e) => setMaxAge(e.target.value ? Number(e.target.value) : null)}
          className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm text-slate-600 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300"
          title="Filter by how recently the job was posted"
        >
          <option value="">Posted: any time</option>
          {AGE_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <select
          value={companyFilter}
          onChange={(e) => setCompanyFilter(e.target.value)}
          className="max-w-[16rem] rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm text-slate-600 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300"
          title="Filter by company"
        >
          <option value="">All companies ({companies.length})</option>
          {companies.map((c) => (
            <option key={c.key} value={c.key}>
              {c.name} ({c.count})
            </option>
          ))}
        </select>
      </div>

      {/* Job list */}
      <main className="mt-6 grid gap-3">
        {visibleJobs.map((job) => (
          <JobCard
            key={job.id}
            job={job}
            status={job.effectiveStatus === "applied" || job.effectiveStatus === "ignored" ? job.effectiveStatus : null}
            onSetStatus={setStatus}
          />
        ))}
        {!error && visibleJobs.length === 0 && (
          <div className="rounded-xl border border-dashed border-slate-300 p-10 text-center text-sm text-slate-500 dark:border-slate-700 dark:text-slate-400">
            No jobs match the current filters.
          </div>
        )}
      </main>

      <footer className="mt-10 text-center text-xs text-slate-400 dark:text-slate-600">
        Data refreshes daily at 8:00 AM IST via GitHub Actions · Apply/Ignore state is stored in your browser
      </footer>
    </div>
  );
}
