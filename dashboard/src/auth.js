// Client-side access gate for the dashboard.
//
// Users live in public/users.json as salted SHA-256 entries. This keeps
// casual visitors out and gives the admin a real login/user-management
// flow, but it is NOT vault-grade security: the site is static and the
// repo is public, so a determined person can read the data directly.
// The job data is public listings, so that trade-off is acceptable.

const SESSION_KEY = "radar-session";

export async function sha256Hex(text) {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export function randomSalt() {
  const bytes = crypto.getRandomValues(new Uint8Array(8));
  return [...bytes].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export async function loadUsers() {
  const resp = await fetch(`${import.meta.env.BASE_URL}users.json?t=${Date.now()}`);
  if (!resp.ok) throw new Error(`users.json: HTTP ${resp.status}`);
  const data = await resp.json();
  return data.users || [];
}

export async function verifyLogin(users, username, password) {
  const user = users.find(
    (u) => u.username.toLowerCase() === username.trim().toLowerCase()
  );
  if (!user) return null;
  const hash = await sha256Hex(`${user.salt}:${password}`);
  return hash === user.hash ? { username: user.username, role: user.role } : null;
}

export function loadSession() {
  try {
    const s = JSON.parse(localStorage.getItem(SESSION_KEY));
    return s && s.username ? s : null;
  } catch {
    return null;
  }
}

export function saveSession(session) {
  localStorage.setItem(SESSION_KEY, JSON.stringify(session));
}

export function clearSession() {
  localStorage.removeItem(SESSION_KEY);
}

export async function makeUserEntry(username, password, role) {
  const salt = randomSalt();
  const hash = await sha256Hex(`${salt}:${password}`);
  return { username: username.trim(), role, salt, hash };
}
