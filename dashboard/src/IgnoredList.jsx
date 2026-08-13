import { useState } from "react";

// Jobs the user ignored: hidden from every other view, listed here so they
// can be restored individually or cleared out in one go. "Delete" keeps a
// tombstone in localStorage so the job stays gone even though the daily
// export still contains it.
export default function IgnoredList({ jobs, onSetStatus, onDeleteAll }) {
  const [confirming, setConfirming] = useState(false);

  if (jobs.length === 0) {
    return (
      <div className="mt-6 rounded-xl border border-dashed border-slate-300 p-10 text-center text-sm text-slate-500 dark:border-slate-700 dark:text-slate-400">
        Nothing ignored. Jobs you ignore are moved out of the listings and
        collected here.
      </div>
    );
  }

  return (
    <div className="mt-6">
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 dark:border-slate-800 dark:bg-slate-900/60">
        <span className="text-sm text-slate-600 dark:text-slate-300">
          <b>{jobs.length}</b> ignored {jobs.length === 1 ? "job" : "jobs"} —
          hidden from all other tabs
        </span>
        {confirming ? (
          <span className="flex items-center gap-2">
            <span className="text-sm text-slate-600 dark:text-slate-300">
              Delete all {jobs.length}?
            </span>
            <button
              onClick={() => {
                onDeleteAll();
                setConfirming(false);
              }}
              className="rounded-lg bg-rose-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-rose-700"
            >
              Yes, delete
            </button>
            <button
              onClick={() => setConfirming(false)}
              className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-600 dark:border-slate-700 dark:text-slate-300"
            >
              Cancel
            </button>
          </span>
        ) : (
          <button
            onClick={() => setConfirming(true)}
            className="rounded-lg border border-rose-300 px-3 py-1.5 text-sm font-medium text-rose-600 hover:bg-rose-50 dark:border-rose-900 dark:text-rose-400 dark:hover:bg-rose-950"
          >
            🗑 Delete all ignored
          </button>
        )}
      </div>

      <div className="mt-3 grid gap-2">
        {jobs.map((job) => (
          <div
            key={job.id}
            className="flex items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-900"
          >
            <div className="min-w-0">
              <a
                href={job.url}
                target="_blank"
                rel="noreferrer"
                className="block truncate text-sm font-semibold text-slate-700 hover:text-blue-600 dark:text-slate-200 dark:hover:text-blue-400"
              >
                {job.title}
              </a>
              <p className="mt-0.5 truncate text-xs text-slate-500 dark:text-slate-400">
                {job.company || "Company not listed"} · {job.location}
              </p>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <button
                onClick={() => onSetStatus(job.id, null)}
                className="rounded-lg border border-slate-300 px-2.5 py-1 text-xs text-slate-600 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
                title="Put this job back in the listings"
              >
                ↩ Restore
              </button>
              <button
                onClick={() => onSetStatus(job.id, "deleted")}
                className="rounded-lg px-2 py-1 text-xs text-slate-400 hover:text-rose-500"
                title="Delete this job for good"
              >
                🗑
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
