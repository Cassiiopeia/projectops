// GitHub Copilot adapter (copy agent skills, record meta, remove).
// The personal skill folder ~/.copilot/skills/<name>/SKILL.md is read by default by VS Code, Copilot CLI and the JetBrains plugin
//   (JetBrains 1.18 default locations: .agents/.github/.claude skills + ~/.agents, ~/.copilot, ~/.claude skills)
// ~/.copilot/intellij-skills is not used — it is a managed folder where the JetBrains plugin overwrites built-in skills.
// A skill loads only when its name (frontmatter name) matches the folder name — pro-* folders already follow that rule.
import { join } from "node:path";
import { existsSync, readdirSync } from "node:fs";
import { migrateConfigRoot } from "../legacy.js";
import { t } from "../../../i18n/index.js";
import { readSkillsMeta } from "../skills-copy.js";
import { applyHomeSkills, removeHomeSkills } from "../home-skills.js";

const META_FILE_NAME = "copilot-skills-meta.json";
const MESSAGE_PREFIX = "ide.copilot";
// 4 signs of Copilot use: copilot CLI, ~/.copilot folder (made by the CLI and JetBrains), VS Code extension, JetBrains plugin
const COPILOT_CLI_NAME = "copilot";
const COPILOT_HOME_DIR = ".copilot";
const VSCODE_EXTENSION_DIRS = [".vscode/extensions", ".vscode-insiders/extensions"];
// VS Code extension folder names: github.copilot-1.2.3 · github.copilot-chat-0.30.0
const VSCODE_EXTENSION_PREFIX = "github.copilot";
// IDE settings roots (macOS · Windows · Linux) > <product><version>/plugins/github-copilot-intellij
//   On Linux the plugin sits directly under <product><version>/. Android Studio uses the same plugin.
const JETBRAINS_CONFIG_ROOTS = [
  "Library/Application Support/JetBrains", "AppData/Roaming/JetBrains", ".local/share/JetBrains",
  "Library/Application Support/Google", "AppData/Roaming/Google", ".local/share/Google",
];
const JETBRAINS_PLUGIN_PREFIX = "github-copilot";

function skillsDir(io) { return join(io.home(), COPILOT_HOME_DIR, "skills"); }
function metaPath(io) { return join(skillsDir(io), META_FILE_NAME); }
function homeSkillsOptions(io) { return { skillsDest: skillsDir(io), metaFileName: META_FILE_NAME, messagePrefix: MESSAGE_PREFIX }; }

// Only an install candidate when there are signs of use, so ~/.copilot is not created in the home of non-users
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
  migrateConfigRoot(io);    // Migrate the shared config root
  return applyHomeSkills(io, ctx, homeSkillsOptions(io));
}

// Keep the folder if skills the user added remain
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
