// Copy .coderabbit.yaml (force path).
// SP2-B implements only the force/non-interactive path. The interactive overwrite/skip menu is SP2-C.
import { join } from "node:path";
import { exists, copyFileSync } from "../fsutil.js";

// Returns 'skip-disabled' | 'skip-no-src' | 'copied-new' | 'overwritten-backup' | 'skip-non-tty'
// opts: { force, tty, enabled }  — SP2-B verification uses the force:true path.
// enabled=false (#457, CodeRabbit not used) does not copy the file at all.
// enabled unset (undefined) keeps the old behavior (copy) — backward compat for old callers.
export function copyCoderabbit(tempDir, { force = false, tty = false, enabled } = {}, targetRoot = ".") {
  if (enabled === false) return "skip-disabled";
  const src = join(tempDir, ".coderabbit.yaml");
  if (!exists(src)) return "skip-no-src";
  const dst = join(targetRoot, ".coderabbit.yaml");

  if (exists(dst)) {
    if (force) {
      copyFileSync(dst, dst + ".bak"); // Back up, then overwrite
      copyFileSync(src, dst);
      return "overwritten-backup";
    }
    if (!tty) return "skip-non-tty"; // Non-TTY & !force → keep
    // The interactive menu is SP2-C — here, keep unless force
    return "skip-non-tty";
  }
  copyFileSync(src, dst); // New file
  return "copied-new";
}
