// Shared install/remove flow for home-copy IDEs (Cursor, Copilot): find source > copy > entry points > log
// Messages use per-adapter key sets (<messagePrefix>.copying, etc.).
import { existsSync } from "node:fs";
import { join } from "node:path";
import { t } from "../../i18n/index.js";
import { resolveSkillsSrc, resolveScriptsSrc, installHomeSkills, removeOwnedEntries } from "./skills-copy.js";
import { refreshStableEntrypoints, projectopsHomeOf } from "./stable-entry.js";

/**
 * Install/update: check skill source > copy skills and shared Python > stable entry points > result log
 * options: { skillsDest, metaFileName, messagePrefix }
 */
export function applyHomeSkills(io, ctx, { skillsDest, metaFileName, messagePrefix }) {
  const skillsSrc = resolveSkillsSrc(ctx);
  if (!skillsSrc) { io.log(t(`${messagePrefix}.noSource`)); return false; }
  const scriptsSrc = resolveScriptsSrc(ctx, skillsSrc);
  io.log(t(`${messagePrefix}.copying`));
  try {
    const { obsoleteNames, hasSharedScripts } = installHomeSkills({
      skillsSrc, scriptsSrc, skillsDest, metaFileName, templateVersion: ctx.templateVersion,
    });
    for (const name of obsoleteNames) io.log(t("ide.skillsCopy.obsolete", { name }));
    // Without the shared Python, skill CLIs fail on import → notify only (doc-only skills still work)
    if (!hasSharedScripts) io.log(t("ide.skillsCopy.noScripts"));
    io.log(t(`${messagePrefix}.installed`, { dest: skillsDest, version: ctx.templateVersion || "unknown" }));
  } catch (e) {
    io.log(t(`${messagePrefix}.copyFailed`));
    io.log(`  ${e?.message || e}`);
    return false;
  }
  installStableEntrypoints(io, skillsSrc, scriptsSrc);
  return true;
}

// An entry point failure is not an install failure (Python reinstalls it on the first CLI run)
function installStableEntrypoints(io, skillsSrc, scriptsSrc) {
  try {
    const projectopsHome = projectopsHomeOf(io);
    for (const name of refreshStableEntrypoints(projectopsHome, { skillsSrc, scriptsSrc })) {
      io.log(t("ide.skillsCopy.entrypoint", { path: join(projectopsHome, "bin", name) }));
    }
  } catch { io.log(t("ide.skillsCopy.entrypointFailed")); }
}

// Remove: skip if no meta > delete only our entries and the shared Python (keep the folder if others' skills remain)
export function removeHomeSkills(io, ctx, { skillsDest, metaFileName, messagePrefix }) {
  if (!existsSync(join(skillsDest, metaFileName))) { io.log(t(`${messagePrefix}.removeNone`)); return true; }
  try {
    removeOwnedEntries(skillsDest, ctx, metaFileName);
    io.log(t(`${messagePrefix}.removed`, { dir: skillsDest }));
    return true;
  } catch { io.log(t(`${messagePrefix}.removeFailed`, { dir: skillsDest })); return false; }
}
