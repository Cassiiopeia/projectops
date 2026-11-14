// Status label style (#776): English standard ("en") and legacy Korean ("ko").
// The template source is English only. Korean mode renames back right after copying —
// a separate Korean copy would drift from the English one.
import { join } from "node:path";
import { existsSync, readFileSync, writeFileSync, readdirSync } from "node:fs";

export const LABEL_STYLES = ["en", "ko"];

// [English standard, legacy Korean]
export const LABEL_PAIRS = [
  ["status: todo", "작업전"],
  ["status: in progress", "작업중"],
  ["status: needs review", "담당자확인"],
  ["status: feedback", "피드백"],
  ["status: done", "작업완료"],
  ["status: on hold", "보류"],
  ["status: cancelled", "취소"],
  ["priority: urgent", "긴급"],
  ["documentation", "문서"],
];
const EN_TO_KO = new Map(LABEL_PAIRS);

// Decision when version.yml has no saved value. New installs get English; existing installs keep Korean.
// Renaming labels in a repo already using them just through an update would silently break the Projects board mapping.
export function resolveLabelStyle({ flag, stored, existing }) {
  if (LABEL_STYLES.includes(flag)) return flag;
  if (LABEL_STYLES.includes(stored)) return stored;
  return existing ? "ko" : "en";
}

function rewrite(file, fn) {
  if (!existsSync(file)) return false;
  const before = readFileSync(file, "utf8");
  const after = fn(before);
  if (after === before) return false;
  writeFileSync(file, after);
  return true;
}

const quoted = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

// Korean mode: rename labels in copied files back to Korean. English mode does nothing.
// Returns the relative paths of changed files.
export function applyLabelStyle(targetRoot, style) {
  if (style !== "ko") return [];
  const changed = [];
  const gh = join(targetRoot, ".github");

  // Label definitions: change only the name line and drop the from_name rename line (already Korean, not needed).
  const labelsFile = join(gh, "config", "issue-labels.yml");
  if (rewrite(labelsFile, (txt) => {
    let out = txt.replace(/^\s*from_name:.*\n/gm, "");
    for (const [en, ko] of LABEL_PAIRS) {
      out = out.replace(new RegExp(`^(- name:\\s*)"?${quoted(en)}"?\\s*$`, "gm"), `$1${ko}`);
    }
    return out;
  })) changed.push(".github/config/issue-labels.yml");

  // Issue template default labels: only the labels line in the front matter.
  const tplDir = join(gh, "ISSUE_TEMPLATE");
  if (existsSync(tplDir)) {
    for (const name of readdirSync(tplDir).filter((f) => f.endsWith(".md"))) {
      const f = join(tplDir, name);
      if (rewrite(f, (txt) => txt.replace(/^labels:\s*\[(.*)\]\s*$/m, (m, inner) => {
        let list = inner;
        for (const [en, ko] of LABEL_PAIRS) list = list.split(`"${en}"`).join(ko).split(`'${en}'`).join(ko);
        return `labels: [${list}]`;
      }))) changed.push(`.github/ISSUE_TEMPLATE/${name}`);
    }
  }

  // Discussion template default labels (#988): only the "- name" lines of the top labels: list
  const discussionDir = join(gh, "DISCUSSION_TEMPLATE");
  if (existsSync(discussionDir)) {
    for (const name of readdirSync(discussionDir).filter((f) => /\.ya?ml$/.test(f))) {
      const f = join(discussionDir, name);
      if (rewrite(f, (txt) => txt.replace(/^labels:\s*\n((?:[ \t]+-[^\n]*\n)+)/m, (m, list) => {
        let out = list;
        for (const [en, ko] of LABEL_PAIRS) {
          out = out.replace(new RegExp(`^([ \\t]+-[ \\t]*)["']?${quoted(en)}["']?[ \\t]*$`, "gm"), `$1"${ko}"`);
        }
        return `labels:\n${out}`;
      }))) changed.push(`.github/DISCUSSION_TEMPLATE/${name}`);
    }
  }

  // Default labels attached by the QA issue bot
  const bot = join(gh, "workflows", "PROJECT-COMMON-QA-ISSUE-CREATION-BOT.yaml");
  if (rewrite(bot, (txt) => txt.replace(/labels:\s*\['status: todo'\]/g, `labels: ['${EN_TO_KO.get("status: todo")}']`))) {
    changed.push(".github/workflows/PROJECT-COMMON-QA-ISSUE-CREATION-BOT.yaml");
  }
  return changed;
}
