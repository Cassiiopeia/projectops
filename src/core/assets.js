// Fetch template assets + apply exclusions.
import { execFileSync } from "node:child_process";
import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { exists, readText, copyDirSync, remove } from "./fsutil.js";
import { DOCS_TO_REMOVE, PLUGIN_ITEMS_TO_REMOVE } from "./exclusions.js";
import { DEFAULT_VERSION } from "../context.js";
import { TEMPLATE_REPO } from "./paths.js";

// Fetch the template into tempDir.
// source:
//   {type:'git', repo?}   → git clone --depth 1 (default repo=TEMPLATE_REPO)
//   {type:'local', path}  → copy a local tree (for offline equivalence checks)
// Skip if tempDir/.github already exists (prevents duplicate calls). Calls applyExclusions automatically after fetching.
// keep: exclusion entries to keep (skill install path needs scripts/common > ["scripts"], #994)
export function acquireTemplate({ tempDir, source = { type: "git" }, keep = [] }) {
  if (exists(join(tempDir, ".github"))) {
    applyExclusions(tempDir, { keep });
    return;
  }
  remove(tempDir);
  if (source.type === "local") {
    copyDirSync(source.path, tempDir);
  } else {
    const repo = source.repo || TEMPLATE_REPO;
    // clone discards stdio, so the cause of failure is lost — a read-only folder would be misreported as "could not download".
    // Create it first so permission errors (EACCES/EPERM/EROFS) surface as is (#720). clone works into an empty folder.
    mkdirSync(tempDir, { recursive: true });
    execFileSync("git", ["clone", "-c", "core.longpaths=true", "--depth", "1", "--quiet", repo, tempDir], { stdio: ["ignore", "ignore", "pipe"] });
  }
  applyExclusions(tempDir, { keep });
}

// Delete DOCS_TO_REMOVE + PLUGIN_ITEMS_TO_REMOVE (except keep entries). skills/ is kept.
// The integration copy reads only explicit paths such as .github > scripts/ left in tempDir never reaches the user repo
export function applyExclusions(tempDir, { keep = [] } = {}) {
  const keptItems = new Set(keep);
  for (const doc of DOCS_TO_REMOVE) remove(join(tempDir, doc));
  for (const item of PLUGIN_ITEMS_TO_REMOVE) if (!keptItems.has(item)) remove(join(tempDir, item));
}

// The ^version: value in tempDir/version.yml. DEFAULT_VERSION if missing.
export function readTemplateVersion(tempDir) {
  const p = join(tempDir, "version.yml");
  if (!exists(p)) return DEFAULT_VERSION;
  for (const line of readText(p).split("\n")) {
    const m = line.match(/^version:\s*["']?([^"'\s]+)["']?/);
    if (m) return m[1];
  }
  return DEFAULT_VERSION;
}
