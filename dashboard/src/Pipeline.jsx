import { STAGES, daysLabel } from "./stages.js";

// Kanban board of every job the user is tracking, one column per stage.
export default function Pipeline({ jobs, overrides, onSetStatus }) {
  const tracked = jobs.filter((j) => {
    const s = overrides[j.id]?.status;
    return s && s !== "ignored";
  });

  if (tracked.length === 0) {
    return (
      <div className="mt-6 rounded-xl border border-dashed border-slate-300 p-10 text-center text-sm text-slate-500 dark:border-slate-700 dark:text-slate-400">
        Nothing tracked yet — open any job card and click a stage
        (Applied, Email Sent, …) to start tracking it here.
      </div>
    );
  }

  return (
    <div className="mt-6 grid gap-3 md:grid-cols-2 lg:grid-cols-5">
      {STAGES.map((stage) => {
        const inStage = tracked.filter((j) => overrides[j.id].status === stage.id);
        return (
          <div
            key={stage.id}
            className="rounded-xl border border-slate-200 bg-slate-50 p-3 dark:border-slate-800 dark:bg-slate-900/60"
          >
            <div className="flex items-center justify-between">
              <span className={`rounded-md px-2 py-0.5 text-xs font-semibold ${stage.chip}`}>
                {stage.emoji} {stage.label}
              </span>
              <span className="text-xs text-slate-400">{inStage.length}</span>
            </div>
            <div className="mt-3 grid gap-2">
              {inStage.map((job) => (
                <div
                  key={job.id}
                  className="rounded-lg border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-900"
                >
                  <a
                    href={job.url}
                    target="_blank"
                    rel="noreferrer"
                    className="block truncate text-sm font-semibold text-slate-900 hover:text-blue-600 dark:text-slate-100 dark:hover:text-blue-400"
                    title={job.title}
                  >
                    {job.title}
                  </a>
                  <p className="mt-0.5 truncate text-xs text-slate-500 dark:text-slate-400">
                    {job.company} · {job.location}
                  </p>
                  <p className="mt-1 text-xs text-slate-400 dark:text-slate-500">
                    {stage.emoji} {daysLabel(overrides[job.id].at)} in this stage
                  </p>
                  <div className="mt-2 flex flex-wrap gap-1">
                    {STAGES.filter((s) => s.id !== stage.id).map((s) => (
                      <button
                        key={s.id}
                        onClick={() => onSetStatus(job.id, s.id)}
                        title={`Move to ${s.label}`}
                        className="rounded border border-slate-200 px-1.5 py-0.5 text-xs text-slate-500 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-400 dark:hover:bg-slate-800"
                      >
                        {s.emoji}
                      </button>
                    ))}
                    <button
                      onClick={() => onSetStatus(job.id, null)}
                      title="Remove from pipeline"
                      className="rounded border border-slate-200 px-1.5 py-0.5 text-xs text-slate-400 hover:text-rose-500 dark:border-slate-700"
                    >
                      ✕
                    </button>
                  </div>
                </div>
              ))}
              {inStage.length === 0 && (
                <p className="py-4 text-center text-xs text-slate-300 dark:text-slate-600">
                  empty
                </p>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
