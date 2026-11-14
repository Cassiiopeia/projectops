// legacy-dir category rule (#476) — move old-name output folders to the new name.
// The folder holds user-written documents (issues, reports), so it is never deleted or neutralized — lossless move only.
// If the target folder exists, merge recursively, leaving conflicting files in place (respects the user's judgment).
import { existsSync, statSync, readdirSync, renameSync, mkdirSync, rmdirSync } from "node:fs";
import { join } from "node:path";

export function detect(targetRoot, entry) {
  const p = join(targetRoot, entry.file);
  try { return existsSync(p) && statSync(p).isDirectory(); }
  catch { return false; }
}

// Recursive merge: files move only when absent at the target, subfolders recurse. Source folders emptied completely are removed.
function mergeDir(from, to) {
  mkdirSync(to, { recursive: true });
  let moved = 0, skipped = 0;
  for (const e of readdirSync(from, { withFileTypes: true })) {
    const s = join(from, e.name);
    const d = join(to, e.name);
    if (e.isDirectory()) {
      const r = mergeDir(s, d);
      moved += r.moved; skipped += r.skipped;
    } else if (existsSync(d)) {
      skipped++; // Same-name file conflict — leave it in place
    } else {
      renameSync(s, d); moved++;
    }
  }
  try { rmdirSync(from); } catch { /* Not empty due to leftover conflicts — leave it */ }
  return { moved, skipped };
}

export function apply(targetRoot, entry) {
  const { moved, skipped } = mergeDir(join(targetRoot, entry.file), join(targetRoot, entry.replacedBy));
  return { action: "moved", from: entry.file, to: entry.replacedBy, moved, skipped };
}
