// Copies ../data/jobs.json into public/ so the static site can fetch it.
// Runs automatically before `dev` and `build` (see package.json pre-scripts).
import { copyFileSync, existsSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const src = join(here, "..", "..", "data", "jobs.json");
const dest = join(here, "..", "public", "jobs.json");

if (existsSync(src)) {
  mkdirSync(dirname(dest), { recursive: true });
  copyFileSync(src, dest);
  console.log(`Synced ${src} -> ${dest}`);
} else {
  console.warn(`No jobs.json found at ${src}; dashboard will show empty state`);
}
