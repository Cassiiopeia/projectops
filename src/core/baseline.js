// Install-time baseline (#557) — the reference point that tells, during an update, "who changed it".
//
// Why: isUnchanged() compares the template (theirs) with the installed copy (ours) 2-way.
// With no base, a one-character upstream fix makes a file the user never touched fall into changed,
// leaving only two choices: "skip everything (no updates)" or "overwrite everything (all user edits lost)".
// The real conflicts that need sorting get buried among the rest.
//
// Stores hashes, not file copies — the goal is classification, not automatic merging.
//
// Why two hashes: a file with user values substituted via env differs on disk from the "render with
// defaults" from the start. One hash cannot answer both questions.
//   - installed : what we wrote to disk at install time     → "did the user edit it since?"
//   - rendered  : the template rendered with defaults then   → "did upstream change since?"
//
// installed is filled only for files we actually wrote. Recording a user-edited file as installed
// would falsely claim "we wrote it", and the next update would silently overwrite that file.
import { createHash } from "node:crypto";
import { join } from "node:path";
import { existsSync, readFileSync } from "node:fs";
import { writeText } from "./fsutil.js";

export const BASELINE_DIR = ".github/.projectops";
export const BASELINE_PATH = ".github/.projectops/baseline.json";

export function sha256(text) {
  return "sha256:" + createHash("sha256").update(String(text), "utf8").digest("hex");
}

// null when missing or broken — the caller falls back to "base unknown" (never silently use an empty baseline;
// an empty baseline could be read as "everything was deleted" rather than "no record").
export function readBaseline(targetRoot = ".") {
  const p = join(targetRoot, BASELINE_PATH);
  if (!existsSync(p)) return null;
  try {
    const data = JSON.parse(readFileSync(p, "utf8"));
    if (!data || typeof data !== "object" || typeof data.files !== "object" || data.files === null) return null;
    return data;
  } catch {
    return null; // Treat a corrupt baseline as missing — do not block the update
  }
}

// entries: Map<filename, {installed?:string|null, rendered:string}>
// The existing baseline is merged — files not touched in this run keep their reference point.
export function writeBaseline(targetRoot, { templateVersion, installedAt, entries, previous = null }) {
  const files = { ...(previous?.files || {}) };
  for (const [filename, entry] of entries) {
    const prev = files[filename] || {};
    files[filename] = {
      // installed is updated only when actually written this time. Kept (skipped) files keep the old reference point.
      installed: entry.installed ?? prev.installed ?? null,
      rendered: entry.rendered,
    };
  }
  const out = {
    templateVersion: templateVersion || "unknown",
    installedAt: installedAt || "",
    files,
  };
  writeText(join(targetRoot, BASELINE_PATH), JSON.stringify(out, null, 2) + "\n");
  return out;
}

// Did the user edit this file after install?
// null when there is no baseline or no record for the file — that means "unknown", not "untouched".
// The caller must fall back to the current 2-way check on null.
export function isUserModified(baseline, filename, installedContent) {
  const rec = baseline?.files?.[filename];
  if (!rec || !rec.installed) return null;
  return rec.installed !== sha256(installedContent);
}

// In the baseline but missing on disk = deleted by the user.
// A by-product of this design: no separate deletion history file is needed.
// candidates: file names the template wants to install this time (other baseline entries are irrelevant)
export function detectRemoved(baseline, candidates, workflowsDir) {
  if (!baseline) return [];
  const removed = [];
  for (const filename of candidates) {
    if (!baseline.files[filename]) continue;      // We never installed this file — no basis to judge
    if (existsSync(join(workflowsDir, filename))) continue;
    removed.push(filename);
  }
  return removed;
}
