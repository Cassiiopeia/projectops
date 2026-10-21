// Cursor 어댑터 (skills 복사·메타 기록·제거).
// 마켓플레이스 없음 → ~/.cursor/skills/ 에 skills/ 폴더, ~/.cursor/scripts/ 에 공용 파이썬을 복사하고 meta.json으로 버전 추적.
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
  migrateLegacy(io, ctx);   // 옛 이름/버전 감지 시 projectops 소유 항목 선별 삭제
  migrateConfigRoot(io);    // 공용 config 루트 이관
  return applyHomeSkills(io, ctx, homeSkillsOptions(io));
}

// 타 스킬(somansa-tools 등) 남으면 폴더 유지
function remove(io, ctx = {}) {
  return removeHomeSkills(io, ctx, homeSkillsOptions(io));
}

// 옛 이름/버전 meta면 projectops 소유 항목만 선별 삭제 → apply가 신규 재설치.
function migrateLegacy(io, ctx) {
  const mp = metaPath(io);
  if (!existsSync(mp)) return;
  let meta = {};
  try { meta = JSON.parse(readFileSync(mp, "utf8")); } catch { return; }
  const oldName = meta.name && LEGACY_NAMES.includes(String(meta.name).toLowerCase());
  const oldVer = isLegacyVersion(meta.version, LEGACY_MAX_VERSION);
  if (!(oldName || oldVer)) return;
  for (const name of ownedEntries(skillsDir(io), ctx, META_FILE_NAME)) {
    try { rmSync(join(skillsDir(io), name), { recursive: true, force: true }); } catch { /* 무시 */ }
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
