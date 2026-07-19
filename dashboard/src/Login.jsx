import { useEffect, useState } from "react";
import { loadUsers, verifyLogin, saveSession } from "./auth.js";

export default function Login({ onLogin }) {
  const [users, setUsers] = useState(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    loadUsers()
      .then(setUsers)
      .catch((e) => setError(`Could not load user list (${e.message})`));
  }, []);

  const submit = async (e) => {
    e.preventDefault();
    if (!users) return;
    setBusy(true);
    setError(null);
    const session = await verifyLogin(users, username, password);
    setBusy(false);
    if (session) {
      saveSession(session);
      onLogin(session);
    } else {
      setError("Invalid username or password");
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-8 shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <div className="text-center">
          <div className="text-3xl">🛰</div>
          <h1 className="mt-2 text-xl font-bold text-slate-900 dark:text-slate-100">
            DevOps Job Radar
          </h1>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            Sign in to access the dashboard
          </p>
        </div>
        <form onSubmit={submit} className="mt-6 grid gap-3">
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="Username"
            autoComplete="username"
            className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none focus:border-blue-500 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
          />
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Password"
            autoComplete="current-password"
            className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none focus:border-blue-500 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
          />
          {error && (
            <p className="text-sm text-rose-600 dark:text-rose-400">{error}</p>
          )}
          <button
            type="submit"
            disabled={busy || !users}
            className="mt-1 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {busy ? "Checking…" : "Sign in"}
          </button>
        </form>
        <p className="mt-4 text-center text-xs text-slate-400 dark:text-slate-500">
          Access is by invitation — ask the owner for an account.
        </p>
      </div>
    </div>
  );
}
