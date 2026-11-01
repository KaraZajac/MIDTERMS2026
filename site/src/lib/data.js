// Read-only access to the export in <repo>/data/site/*.json, written by
// `midterms export`. Resolved from process.cwd(), never import.meta.url:
// Astro emits prerender chunks a directory deeper than their source, which
// silently moves any module-relative path (the JUDGMENT gotcha).
import fs from "node:fs";
import path from "node:path";
import { execSync } from "node:child_process";

function findRepo(start) {
  let dir = path.resolve(start);
  for (let i = 0; i < 6; i++) {
    if (fs.existsSync(path.join(dir, "data", "site"))) return dir;
    dir = path.dirname(dir);
  }
  throw new Error(`data/site/ not found walking up from ${start}`);
}

export const REPO = findRepo(process.cwd());
const SITE_DATA = path.join(REPO, "data", "site");
const cache = new Map();

function load(name) {
  if (!cache.has(name)) {
    const file = path.join(SITE_DATA, name);
    cache.set(name, JSON.parse(fs.readFileSync(file, "utf8")));
  }
  return cache.get(name);
}
function optional(name) {
  return fs.existsSync(path.join(SITE_DATA, name)) ? load(name) : null;
}

export const meta = () => load("meta.json");
export const summary = () => load("summary.json");
export const racesFile = () => load("races.json");
export const pollsFile = () => load("polls.json");
export const generic = () => load("generic.json");
export const history = () => optional("history.json");
export const backtest = () => optional("backtest.json");
export const scorecard = () => optional("scorecard.json");
export const simParams = () => optional("sim.json");

/** The commit this build is made from: the deploy timer compares it with main. */
export function buildCommit() {
  try {
    return execSync("git rev-parse HEAD", { cwd: REPO, stdio: ["ignore", "pipe", "ignore"] })
      .toString()
      .trim();
  } catch {
    return "unknown";
  }
}

/** Read a repo file as text (docs/method.md and friends), or null. */
export function repoText(rel) {
  const file = path.join(REPO, rel);
  return fs.existsSync(file) ? fs.readFileSync(file, "utf8") : null;
}
