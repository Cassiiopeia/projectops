// Orphan type workflow detection and cleanup (#487) — detects template workflows of types dropped from the selection
// by a type change and neutralizes them as .bak (same approach as the legacy migration).
// Safety rule: only exact file name matches against the template inventory — no prefix matching
// (avoids hitting user custom workflows). common/ is not a type, so it is skipped in the loop.
import { existsSync, renameSync, rmSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { PATHS } from "./paths.js";
import { exists, listYamlFiles } from "./fsutil.js";
import { commonOptionalGroups, SERVER_DEPLOY_DIR } from "./workflow-groups.js";

// Template inventory of project-types/<type>/ — direct children + server-deploy/ + publish/*/ (same scope as the copy engine)
function typeInventory(projectTypesDir, type) {
  const typeDir = join(projectTypesDir, type);
  const dirs = [typeDir, join(typeDir, SERVER_DEPLOY_DIR)];
  const pubRoot = join(typeDir, "publish");
  if (exists(pubRoot)) {
    for (const e of readdirSync(pubRoot, { withFileTypes: true })) {
      if (e.isDirectory()) dirs.push(join(pubRoot, e.name));
    }
  }
  const files = new Set();
  for (const d of dirs) {
    if (!exists(d)) continue;
    for (const f of listYamlFiles(d)) files.add(f);
  }
  return files;
}

// Folders under common/ that are "copied only when selected" (#566).
// Turning one on makes the copy engine add it, but turning it off left the existing files in place, still running.
// For a user who turned the axis off that means "I turned it off, why does it run" — caught here as orphans.
// On/off is read from the same table as the copy engine (workflow-groups.js) (#851).
function commonOptionalOrphans(commonDir, opts) {
  const out = [];
  for (const group of commonOptionalGroups(commonDir, opts)) {
    if (group.enabled) continue;
    const d = join(commonDir, group.dir);
    if (!exists(d)) continue;
    for (const f of listYamlFiles(d)) out.push({ filename: f, type: group.orphanLabel });
  }
  return out;
}

// Returns as orphans the template workflows of unselected types/options that exist in the target repo.
export function detectOrphanWorkflows({ tempDir, targetRoot = ".", selectedTypes = [], options = null }) {
  const projectTypesDir = join(tempDir, PATHS.workflowsDir, PATHS.projectTypesDir);
  if (!exists(projectTypesDir)) return [];
  const selected = new Set(selectedTypes);
  // File names used by the selected types — cross-check (names are unique by type prefix, but as a safety net)
  const keep = new Set();
  for (const t of selected) for (const f of typeInventory(projectTypesDir, t)) keep.add(f);
  const workflowsDir = join(targetRoot, PATHS.workflowsDir);
  const orphans = [];
  for (const e of readdirSync(projectTypesDir, { withFileTypes: true })) {
    if (!e.isDirectory() || e.name === "common" || selected.has(e.name)) continue;
    for (const f of typeInventory(projectTypesDir, e.name)) {
      if (keep.has(f)) continue;
      if (existsSync(join(workflowsDir, f))) orphans.push({ filename: f, type: e.name });
    }
  }
  // Conditional folders under common — checked only for callers that pass options (keeps old callers' behavior).
  if (options) {
    const commonDir = join(projectTypesDir, "common");
    for (const o of commonOptionalOrphans(commonDir, options)) {
      if (keep.has(o.filename)) continue;
      if (existsSync(join(workflowsDir, o.filename))) orphans.push(o);
    }
  }
  return orphans.sort((a, b) => a.filename.localeCompare(b.filename));
}

// .bak neutralizer — tolerates partial failure (same principle as migrations applySafeMigrations).
export function applyOrphanCleanup(targetRoot, orphans) {
  const workflowsDir = join(targetRoot, PATHS.workflowsDir);
  const results = [];
  for (const { filename } of orphans) {
    try {
      const src = join(workflowsDir, filename);
      const bak = `${src}.bak`;
      if (existsSync(bak)) rmSync(bak, { force: true }); // Windows rename fails when the target exists
      renameSync(src, bak);
      results.push({ filename, action: "bak" });
    } catch (err) {
      results.push({ filename, action: "error", error: err.message });
    }
  }
  return results;
}
