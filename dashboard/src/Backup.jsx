import { useRef, useState } from "react";

const STATUS_KEY = "radar-status-overrides";
const FILE_TYPE = "devops-job-radar-tracking";

// Your application tracking lives in this browser only. Backup downloads it
// as a small file; Restore merges a backup back in — on any browser, device,
// or site URL. This is what protects tracking from a cleared browser, a new
// phone, or a hosting change.
export default function Backup({ onClose, onRestored }) {
  const [msg, setMsg] = useState(null);
  const [err, setErr] = useState(null);
  const fileRef = useRef(null);

  const countTracked = () => {
    try {
      return Object.keys(JSON.parse(localStorage.getItem(STATUS_KEY) || "{}")).length;
    } catch {
      return 0;
    }
  };

  const download = () => {
    setErr(null);
    const overrides = localStorage.getItem(STATUS_KEY) || "{}";
    const payload = {
      type: FILE_TYPE,
      version: 1,
      exported_at: new Date().toISOString(),
      overrides: JSON.parse(overrides),
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `job-radar-tracking-${new Date().toISOString().slice(0, 10)}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    setMsg(`Backup downloaded (${countTracked()} tracked jobs).`);
  };

  const restore = (file) => {
    setErr(null);
    setMsg(null);
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const parsed = JSON.parse(reader.result);
        // Accept either the enveloped file or a raw overrides object.
        const incoming =
          parsed && parsed.type === FILE_TYPE ? parsed.overrides : parsed;
        if (!incoming || typeof incoming !== "object" || Array.isArray(incoming)) {
          throw new Error("not a tracking backup file");
        }
        const valid = Object.entries(incoming).filter(
          ([, v]) => v && typeof v === "object" && typeof v.status === "string"
        );
        if (valid.length === 0) throw new Error("no tracked jobs found in file");

        const current = JSON.parse(localStorage.getItem(STATUS_KEY) || "{}");
        // Merge: keep whichever mark is newer per job so a restore never
        // overwrites more-recent local changes.
        const merged = { ...current };
        for (const [id, entry] of valid) {
          const existing = merged[id];
          if (!existing || (entry.at || "") >= (existing.at || "")) {
            merged[id] = entry;
          }
        }
        localStorage.setItem(STATUS_KEY, JSON.stringify(merged));
        setMsg(
          `Restored ${valid.length} tracked jobs. Reloading…`
        );
        setTimeout(() => {
          onRestored?.();
          window.location.reload();
        }, 900);
      } catch (e) {
        setErr(`Could not restore: ${e.message}`);
      }
    };
    reader.onerror = () => setErr("Could not read the file.");
    reader.readAsText(file);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-6 dark:border-slate-800 dark:bg-slate-900">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-bold text-slate-900 dark:text-slate-100">
            💾 Backup &amp; restore tracking
          </h2>
          <button
            onClick={onClose}
            className="rounded-lg px-2 py-1 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
          >
            ✕
          </button>
        </div>

        <p className="mt-3 text-sm text-slate-600 dark:text-slate-300">
          Your applied / interview / ignored marks are saved in this browser
          only. Download a backup to keep them safe, and restore it on any
          device or browser. You currently have <b>{countTracked()}</b> tracked
          {countTracked() === 1 ? " job" : " jobs"}.
        </p>

        <div className="mt-5 grid gap-3">
          <button
            onClick={download}
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
          >
            ⬇ Download backup
          </button>
          <button
            onClick={() => fileRef.current?.click()}
            className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
          >
            ⬆ Restore from backup file
          </button>
          <input
            ref={fileRef}
            type="file"
            accept="application/json,.json"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) restore(f);
              e.target.value = "";
            }}
          />
        </div>

        {msg && (
          <p className="mt-4 text-sm text-emerald-600 dark:text-emerald-400">{msg}</p>
        )}
        {err && (
          <p className="mt-4 text-sm text-rose-600 dark:text-rose-400">{err}</p>
        )}

        <p className="mt-4 text-xs text-slate-400 dark:text-slate-500">
          Restore merges into what you already have and keeps the newer mark
          for any job — it never wipes your current tracking.
        </p>
      </div>
    </div>
  );
}
