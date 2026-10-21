// GitHub Copilot 어댑터 (agent skills 복사·메타 기록·제거).
// Copilot(VS Code·Copilot CLI)은 개인 스킬을 ~/.copilot/skills/<이름>/SKILL.md 에서 바로 읽는다 → Cursor 와 같은 복사 방식.
// 스킬 이름(frontmatter name)은 폴더명과 같아야 로드된다 — pro-* 폴더가 이미 그 규칙을 지킨다.
import { join } from "node:path";
import { existsSync, readdirSync } from "node:fs";
import { migrateConfigRoot } from "../legacy.js";
import { t } from "../../../i18n/index.js";
import {
  resolveSkillsSrc, readSkillsMeta, copySkillsTree, removeOwnedEntries, writeSkillsMeta,
} from "../skills-copy.js";

const META_FILE_NAME = "copilot-skills-meta.json";
// Copilot 사용 흔적 3종: copilot CLI, ~/.copilot 폴더(CLI 설정), VS Code Copilot 확장
const COPILOT_CLI_NAME = "copilot";
const COPILOT_HOME_DIR = ".copilot";
const VSCODE_EXTENSION_DIRS = [".vscode/extensions", ".vscode-insiders/extensions"];
// 확장 폴더명: github.copilot-1.2.3 · github.copilot-chat-0.30.0
const COPILOT_EXTENSION_PREFIX = "github.copilot";

function skillsDir(io) { return join(io.home(), COPILOT_HOME_DIR, "skills"); }
function metaPath(io) { return join(skillsDir(io), META_FILE_NAME); }

// 쓰지 않는 사람 홈에 ~/.copilot 을 만들지 않도록, 흔적이 있을 때만 설치 후보로 둔다
function isCopilotDetected(io) {
  if (io.which(COPILOT_CLI_NAME)) return true;
  if (existsSync(join(io.home(), COPILOT_HOME_DIR))) return true;
  return VSCODE_EXTENSION_DIRS.some((dir) => hasCopilotExtension(join(io.home(), dir)));
}

function hasCopilotExtension(extensionsDir) {
  if (!existsSync(extensionsDir)) return false;
  try {
    return readdirSync(extensionsDir).some((name) => name.toLowerCase().startsWith(COPILOT_EXTENSION_PREFIX));
  } catch { return false; }
}

function detect(io) {
  const { installed, version } = readSkillsMeta(metaPath(io));
  if (installed) return { installed, version, cliMissing: false };
  if (isCopilotDetected(io)) return { installed: false, version: null, cliMissing: false, note: t("ide.copilot.detected") };
  return { installed: false, version: null, cliMissing: true, note: t("ide.copilot.notDetected") };
}

function apply(io, ctx = {}) {
  if (detect(io).cliMissing) { io.log(manualHint()); return false; }
  migrateConfigRoot(io);    // 공용 config 루트 이관
  const src = resolveSkillsSrc(ctx);
  if (!src) { io.log(t("ide.copilot.noSource")); return false; }
  const dest = skillsDir(io);
  io.log(t("ide.copilot.copying"));
  try {
    for (const name of copySkillsTree(src, dest, META_FILE_NAME)) io.log(t("ide.skillsCopy.obsolete", { name }));
    writeSkillsMeta(dest, META_FILE_NAME, ctx.templateVersion);
    io.log(t("ide.copilot.installed", { dest, version: ctx.templateVersion || "unknown" }));
    return true;
  } catch {
    io.log(t("ide.copilot.copyFailed"));
    return false;
  }
}

function remove(io, ctx = {}) {
  const dir = skillsDir(io);
  if (!existsSync(metaPath(io))) { io.log(t("ide.copilot.removeNone")); return true; }
  try {
    // 사용자가 직접 넣은 스킬이 남으면 폴더 유지
    removeOwnedEntries(dir, ctx, META_FILE_NAME);
    io.log(t("ide.copilot.removed", { dir }));
    return true;
  } catch { io.log(t("ide.copilot.removeFailed", { dir })); return false; }
}

function manualHint() {
  return t("ide.copilot.manual");
}

export const copilotAdapter = {
  id: "copilot", label: "GitHub Copilot", order: 45,
  detect, apply, remove, manualHint,
};
