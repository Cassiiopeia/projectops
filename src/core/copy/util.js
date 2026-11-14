// Copy util modules (force path).
// If tempDir/.github/util/<type>/ exists, (force) copy all of it to .github/util/<type>/ and count modules.
import { join } from "node:path";
import { readdirSync } from "node:fs";
import { exists, copyDirSync } from "../fsutil.js";

// Returns {copied:bool, moduleCount:number}. Skipped when not force (non-TTY).
// ⚠️ This is an overlay copy — old files deleted/renamed in the template are not removed here.
//    Cleaning up old util files is the job of the migrations registry (util-file category) (#500).
export function copyUtilModules(tempDir, type, { force = false } = {}, targetRoot = ".") {
  const src = join(tempDir, ".github", "util", type);
  if (!exists(src)) return { copied: false, moduleCount: 0 };
  if (!force) return { copied: false, moduleCount: 0 }; // SP2-B: force path only

  const dst = join(targetRoot, ".github", "util", type);
  copyDirSync(src, dst);

  // Number of subdirectories = number of modules
  // Folders starting with `_` are not modules but assets shared by modules
  // (e.g. flutter/_shared — CSS/JS shared by the 3 wizards). Excluded from the count.
  let moduleCount = 0;
  for (const e of readdirSync(dst, { withFileTypes: true })) {
    if (e.isDirectory() && !e.name.startsWith("_")) moduleCount++;
  }
  return { copied: true, moduleCount };
}
