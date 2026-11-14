// root-file category rule (#470) — delete old template docs at the repo root.
// They are docs, so no neutralization is needed; users deleted these leftovers by hand every time, so delete is expected.
import { existsSync, readFileSync, rmSync } from "node:fs";
import { join } from "node:path";

function target(targetRoot, entry) {
  return join(targetRoot, entry.file);
}

export function detect(targetRoot, entry) {
  const p = target(targetRoot, entry);
  if (!existsSync(p)) return false;
  // Avoid false hits on generic file names — with a contentMarker, the content must also match to count as template-owned
  if (entry.contentMarker) {
    try { return readFileSync(p, "utf8").includes(entry.contentMarker); }
    catch { return false; }
  }
  return true;
}

export function apply(targetRoot, entry) {
  rmSync(target(targetRoot, entry), { force: true });
  return { action: "deleted", from: entry.file, to: null };
}
