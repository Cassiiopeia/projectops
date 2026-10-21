// GitHub Copilot 어댑터 (agent skills 복사·메타 기록·제거).
// 개인 스킬 폴더 ~/.copilot/skills/<이름>/SKILL.md 를 VS Code·Copilot CLI·JetBrains 플러그인이 모두 기본으로 읽는다
//   (JetBrains 1.18 기본 위치: .agents/.github/.claude skills + ~/.agents·~/.copilot·~/.claude skills)
// ~/.copilot/intellij-skills 는 JetBrains 플러그인이 내장 스킬을 덮어쓰는 관리 폴더라 쓰지 않는다.
// 스킬 이름(frontmatter name)은 폴더명과 같아야 로드된다 — pro-* 폴더가 이미 그 규칙을 지킨다.
import { join } from "node:path";
import { existsSync, readdirSync } from "node:fs";
import { migrateConfigRoot } from "../legacy.js";
import { t } from "../../../i18n/index.js";
import { readSkillsMeta } from "../skills-copy.js";
import { applyHomeSkills, removeHomeSkills } from "../home-skills.js";

const META_FILE_NAME = "copilot-skills-meta.json";
const MESSAGE_PREFIX = "ide.copilot";
// Copilot 사용 흔적 4종: copilot CLI, ~/.copilot 폴더(CLI·JetBrains 가 만듦), VS Code 확장, JetBrains 플러그인
const COPILOT_CLI_NAME = "copilot";
const COPILOT_HOME_DIR = ".copilot";
const VSCODE_EXTENSION_DIRS = [".vscode/extensions", ".vscode-insiders/extensions"];
// VS Code 확장 폴더명: github.copilot-1.2.3 · github.copilot-chat-0.30.0
const VSCODE_EXTENSION_PREFIX = "github.copilot";
// IDE 설정 루트 (macOS · Windows · Linux) > <제품><버전>/plugins/github-copilot-intellij
//   Linux 는 플러그인이 <제품><버전>/ 바로 아래에 깔린다. Android Studio 도 같은 플러그인을 쓴다.
const JETBRAINS_CONFIG_ROOTS = [
  "Library/Application Support/JetBrains", "AppData/Roaming/JetBrains", ".local/share/JetBrains",
  "Library/Application Support/Google", "AppData/Roaming/Google", ".local/share/Google",
];
const JETBRAINS_PLUGIN_PREFIX = "github-copilot";

function skillsDir(io) { return join(io.home(), COPILOT_HOME_DIR, "skills"); }
function metaPath(io) { return join(skillsDir(io), META_FILE_NAME); }
function homeSkillsOptions(io) { return { skillsDest: skillsDir(io), metaFileName: META_FILE_NAME, messagePrefix: MESSAGE_PREFIX }; }

// 쓰지 않는 사람 홈에 ~/.copilot 을 만들지 않도록, 흔적이 있을 때만 설치 후보로 둔다
function isCopilotDetected(io) {
  if (io.which(COPILOT_CLI_NAME)) return true;
  if (existsSync(join(io.home(), COPILOT_HOME_DIR))) return true;
  if (VSCODE_EXTENSION_DIRS.some((dir) => hasEntryWithPrefix(join(io.home(), dir), VSCODE_EXTENSION_PREFIX))) return true;
  return JETBRAINS_CONFIG_ROOTS.some((root) => hasJetBrainsCopilotPlugin(join(io.home(), root)));
}

function hasJetBrainsCopilotPlugin(configRoot) {
  for (const productDir of listNames(configRoot)) {
    const productPath = join(configRoot, productDir);
    if (hasEntryWithPrefix(join(productPath, "plugins"), JETBRAINS_PLUGIN_PREFIX)) return true;
    if (hasEntryWithPrefix(productPath, JETBRAINS_PLUGIN_PREFIX)) return true;
  }
  return false;
}

function hasEntryWithPrefix(dir, prefix) {
  return listNames(dir).some((name) => name.toLowerCase().startsWith(prefix));
}

function listNames(dir) {
  if (!existsSync(dir)) return [];
  try { return readdirSync(dir); } catch { return []; }
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
  return applyHomeSkills(io, ctx, homeSkillsOptions(io));
}

// 사용자가 직접 넣은 스킬이 남으면 폴더 유지
function remove(io, ctx = {}) {
  return removeHomeSkills(io, ctx, homeSkillsOptions(io));
}

function manualHint() {
  return t("ide.copilot.manual");
}

export const copilotAdapter = {
  id: "copilot", label: "GitHub Copilot", order: 45,
  detect, apply, remove, manualHint,
};
