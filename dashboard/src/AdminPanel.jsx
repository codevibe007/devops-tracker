import { useEffect, useState } from "react";
import { loadUsers, makeUserEntry } from "./auth.js";

const USERS_EDIT_URL =
  "https://github.com/codevibe007/devops-tracker/edit/main/dashboard/public/users.json";

// The site is static, so the panel can't write to the repo directly.
// Instead it generates the complete updated users.json and hands the admin
// a one-click GitHub edit link — paste, commit, and Netlify redeploys the
// new user list in about a minute.
export default function AdminPanel({ session, onClose }) {
  const [users, setUsers] = useState(null);
  const [mode, setMode] = useState("create"); // create | password
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("member");
  const [output, setOutput] = useState(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    loadUsers().then(setUsers).catch((e) => setError(e.message));
  }, []);

  const generate = async (e) => {
    e.preventDefault();
    setError(null);
    setCopied(false);
    if (!users) return;
    const name = mode === "password" ? session.username : username.trim();
    if (!name || password.length < 6) {
      setError("Username required and password must be at least 6 characters");
      return;
    }
    if (
      mode === "create" &&
      users.some((u) => u.username.toLowerCase() === name.toLowerCase())
    ) {
      setError(`User "${name}" already exists — use a different username`);
      return;
    }
    const entryRole =
      mode === "password"
        ? users.find((u) => u.username === session.username)?.role || "admin"
        : role;
    const entry = await makeUserEntry(name, password, entryRole);
    const next =
      mode === "password"
        ? users.map((u) =>
            u.username === session.username
              ? // Keep the permanent recovery credentials (if any) when
                // rotating the main password.
                {
                  ...entry,
                  ...(u.recoverySalt && {
                    recoverySalt: u.recoverySalt,
                    recoveryHash: u.recoveryHash,
                  }),
                }
              : u
          )
        : [...users, entry];
    setOutput(JSON.stringify({ users: next }, null, 2));
  };

  const copy = () => {
    navigator.clipboard.writeText(output).then(() => setCopied(true));
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-2xl border border-slate-200 bg-white p-6 dark:border-slate-800 dark:bg-slate-900">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-bold text-slate-900 dark:text-slate-100">
            🔐 Admin panel
          </h2>
          <button
            onClick={onClose}
            className="rounded-lg px-2 py-1 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
          >
            ✕
          </button>
        </div>

        <div className="mt-4 flex gap-1 rounded-xl bg-slate-100 p-1 dark:bg-slate-800">
          {[
            ["create", "Create user"],
            ["password", "Change my password"],
          ].map(([id, label]) => (
            <button
              key={id}
              onClick={() => {
                setMode(id);
                setOutput(null);
                setError(null);
              }}
              className={`flex-1 rounded-lg px-3 py-1.5 text-sm font-medium ${
                mode === id
                  ? "bg-white text-slate-900 shadow-sm dark:bg-slate-700 dark:text-white"
                  : "text-slate-500 dark:text-slate-400"
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        {users && mode === "create" && (
          <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">
            Existing users: {users.map((u) => `${u.username} (${u.role})`).join(", ")}
          </p>
        )}

        <form onSubmit={generate} className="mt-4 grid gap-3">
          {mode === "create" ? (
            <>
              <input
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="New username"
                className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
              />
              <select
                value={role}
                onChange={(e) => setRole(e.target.value)}
                className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
              >
                <option value="member">member — can view and track jobs</option>
                <option value="admin">admin — can also run the radar and manage users</option>
              </select>
            </>
          ) : (
            <p className="text-sm text-slate-600 dark:text-slate-300">
              Set a new password for <b>{session.username}</b>:
            </p>
          )}
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder={mode === "create" ? "Password for this user" : "New password"}
            className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
          />
          {error && <p className="text-sm text-rose-600 dark:text-rose-400">{error}</p>}
          <button
            type="submit"
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
          >
            Generate updated user file
          </button>
        </form>

        {output && (
          <div className="mt-4">
            <p className="text-sm font-medium text-slate-700 dark:text-slate-300">
              Now publish it (takes ~1 minute):
            </p>
            <ol className="mt-1 list-decimal pl-5 text-xs text-slate-500 dark:text-slate-400">
              <li>Copy the file content below</li>
              <li>Open users.json on GitHub and replace everything with it</li>
              <li>Commit — Netlify redeploys and the change is live</li>
            </ol>
            <pre className="mt-2 max-h-40 overflow-auto rounded-lg bg-slate-100 p-3 text-xs dark:bg-slate-950 dark:text-slate-300">
              {output}
            </pre>
            <div className="mt-2 flex gap-2">
              <button
                onClick={copy}
                className="rounded-lg bg-blue-600 px-3 py-1.5 text-sm text-white hover:bg-blue-700"
              >
                {copied ? "✓ Copied" : "Copy content"}
              </button>
              <a
                href={USERS_EDIT_URL}
                target="_blank"
                rel="noreferrer"
                className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-600 dark:border-slate-700 dark:text-slate-300"
              >
                Open users.json on GitHub ↗
              </a>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
