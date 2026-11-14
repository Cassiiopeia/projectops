// Cursor adapter (copy skills, record meta, remove).
// No marketplace → copy the skills/ folder to ~/.cursor/skills/ and the shared Python to ~/.cursor/scripts/, tracking the version in meta.json.
import { join } from "node:path";
import { existsSync, readFileSync, rmSync } from "node:fs";
import { migrateConfigRoot, isLegacyVersion } from "../legacy.js";
import { t } from "../../../i18n/index.js";
import { readSkillsMeta, ownedEntries } from "../skills-copy.js";
import { applyHomeSkills, removeHomeSkills } from "../home-skills.js";

const LEGACY_NAMES = ["cassiiopeia", "suh-devops-template"];
const LEGACY_MAX_VERSION = "4.2.4";
const META_FILE_NAME = "cursor-skills-meta.json";
const MESSAGE_PREFIX = "ide.cursor";

function skillsDir(io) { return join(io.home(), ".cursor/skills"); }
function metaPath(io) { return join(skillsDir(io), META_FILE_NAME); }
function homeSkillsOptions(io) { return { skillsDest: skillsDir(io), metaFileName: META_FILE_NAME, messagePrefix: MESSAGE_PREFIX }; }

function detect(io) {
  const { installed, version } = readSkillsMeta(metaPath(io));
  return { installed, version, cliMissing: false };
}

function apply(io, ctx = {}) {
  migrateLegacy(io, ctx);   // On an old name/version, selectively delete projectops-owned entries
  migrateConfigRoot(io);    // Migrate the shared config root
  return applyHomeSkills(io, ctx, homeSkillsOptions(io));
}

// Keep the folder if other skills (somansa-tools, etc.) remain
function remove(io, ctx = {}) {
  return removeHomeSkills(io, ctx, homeSkillsOptions(io));
}

// If meta has an old name/version, selectively delete only projectops-owned entries → apply reinstalls fresh.
function migrateLegacy(io, ctx) {
  const mp = metaPath(io);
  if (!existsSync(mp)) return;
  let meta = {};
  try { meta = JSON.parse(readFileSync(mp, "utf8")); } catch { return; }
  const oldName = meta.name && LEGACY_NAMES.includes(String(meta.name).toLowerCase());
  const oldVer = isLegacyVersion(meta.version, LEGACY_MAX_VERSION);
  if (!(oldName || oldVer)) return;
  for (const name of ownedEntries(skillsDir(io), ctx, META_FILE_NAME)) {
    try { rmSync(join(skillsDir(io), name), { recursive: true, force: true }); } catch { /* ignore */ }
  }
  io.log(t("ide.cursor.legacy", { name: meta.name, version: meta.version }));
}

function manualHint() {
  return t("ide.cursor.manual");
}

export const cursorAdapter = {
  id: "cursor", label: "Cursor", order: 20,
  detect, apply, remove, manualHint,
};
