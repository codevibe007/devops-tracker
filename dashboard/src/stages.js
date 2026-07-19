// Application-tracking stages for a job, in pipeline order.
export const STAGES = [
  {
    id: "applied",
    label: "Applied",
    emoji: "📮",
    chip: "bg-blue-100 text-blue-700 dark:bg-blue-900/60 dark:text-blue-300",
    active: "border-blue-600 bg-blue-600 text-white",
  },
  {
    id: "emailed",
    label: "Email Sent",
    emoji: "✉️",
    chip: "bg-violet-100 text-violet-700 dark:bg-violet-900/60 dark:text-violet-300",
    active: "border-violet-600 bg-violet-600 text-white",
  },
  {
    id: "interview",
    label: "Interview",
    emoji: "🎤",
    chip: "bg-amber-100 text-amber-700 dark:bg-amber-900/60 dark:text-amber-300",
    active: "border-amber-500 bg-amber-500 text-white",
  },
  {
    id: "selected",
    label: "Selected",
    emoji: "🏆",
    chip: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/60 dark:text-emerald-300",
    active: "border-emerald-600 bg-emerald-600 text-white",
  },
  {
    id: "rejected",
    label: "Rejected",
    emoji: "🚫",
    chip: "bg-rose-100 text-rose-700 dark:bg-rose-900/60 dark:text-rose-300",
    active: "border-rose-600 bg-rose-600 text-white",
  },
];

export const stageById = (id) => STAGES.find((s) => s.id === id) || null;

export function daysIn(sinceIso) {
  if (!sinceIso) return null;
  const days = Math.floor((Date.now() - new Date(sinceIso).getTime()) / 86_400_000);
  return Number.isNaN(days) ? null : days;
}

export function daysLabel(sinceIso) {
  const d = daysIn(sinceIso);
  if (d === null) return "";
  if (d < 1) return "today";
  return d === 1 ? "1 day" : `${d} days`;
}
