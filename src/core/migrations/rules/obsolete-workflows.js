// workflow category rule (#470) — neutralize old template workflows in .github/workflows/ as .bak.
// GitHub Actions runs only .yaml/.yml, so a .bak rename = instant neutralization + restorable.
import { existsSync, readFileSync, renameSync, rmSync } from "node:fs";
import { join } from "node:path";
import { EXTRACTORS } from "./settings-extractors.js";

const WF_DIR = join(".github", "workflows");

function target(targetRoot, entry) {
  return join(targetRoot, WF_DIR, entry.file);
}

export function detect(targetRoot, entry) {
  const p = target(targetRoot, entry);
  if (!existsSync(p)) return false;
  if (entry.contentMarker) {
    try { return readFileSync(p, "utf8").includes(entry.contentMarker); }
    catch { return false; }
  }
  return true;
}

export function apply(targetRoot, entry) {
  // Migrate settings before neutralizing (neutralization proceeds even on failure — partial failure allowed)
  let carried = [];
  let carryFailed = null;
  if (entry.settingsExtractor && EXTRACTORS[entry.settingsExtractor]) {
    try { carried = EXTRACTORS[entry.settingsExtractor](targetRoot, entry).carried; }
    catch (error) { carried = []; carryFailed = error?.message || String(error); }
  }
  const src = target(targetRoot, entry);
  const bak = `${src}.bak`;
  if (existsSync(bak)) rmSync(bak, { force: true }); // Windows rename fails when the target exists
  renameSync(src, bak);
  const result = { action: "bak", from: entry.file, to: `${entry.file}.bak` };
  if (carried.length > 0) result.carried = carried;
  if (carryFailed) result.carryFailed = carryFailed;
  return result;
}
