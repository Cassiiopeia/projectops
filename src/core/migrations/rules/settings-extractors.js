// Settings migrator (#470 extension, #478) — moves custom settings of old workflows into version.yml before neutralizing.
// Rules: migrate only values that differ from defaults / leave an existing issue_helper section untouched (new form wins, idempotent)
//       / skip if there is no version.yml / never block neutralization on failure (caller uses try-catch).
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

// with: defaults of the shipped old MODULE workflow — values equal to these are not user customizations
const OLD_DEFAULTS = {
  branch_prefix: "",
  max_branch_length: "100",
  commit_template: "${issueTitle} : feat : {변경 사항에 대한 설명} ${issueUrl}",
  comment_marker: "<!-- 이 댓글은 SUH-ISSUE-HELPER 에 의해 자동으로 생성되었습니다. - https://github.com/Cassiiopeia/github-issue-helper -->",
};

const KEYS = Object.keys(OLD_DEFAULTS);

function unquote(v) { return v.trim().replace(/^["']|["']$/g, ""); }

function parseWithValues(content) {
  const out = {};
  for (const key of KEYS) {
    const m = content.match(new RegExp(`^\\s*${key}:\\s*(.+)$`, "m"));
    if (m) out[key] = unquote(m[1].replace(/\s+#.*$/, ""));
  }
  return out;
}

// Insert the issue_helper block into version.yml. Creates the hierarchy (metadata/template/options) if missing.
function insertIssueHelperBlock(vyText, carried) {
  const lines = Object.entries(carried)
    .map(([k, v]) => `        ${k}: "${v.replace(/"/g, '\\"')}"`);
  const block = ["      issue_helper:", ...lines].join("\n");

  if (/^\s{4}options:\s*$/m.test(vyText))
    return vyText.replace(/^(\s{4}options:\s*)$/m, `$1\n${block}`);
  if (/^\s{2}template:\s*$/m.test(vyText))
    return vyText.replace(/^(\s{2}template:\s*)$/m, `$1\n    options:\n${block}`);
  if (/^metadata:\s*$/m.test(vyText))
    return vyText.replace(/^(metadata:\s*)$/m, `$1\n  template:\n    options:\n${block}`);
  return `${vyText.replace(/\n*$/, "\n")}metadata:\n  template:\n    options:\n${block}\n`;
}

// Old SUH-ISSUE-HELPER-MODULE with: → options.issue_helper migration. Returns { carried: [keys...] }
export function extractIssueHelperModule(targetRoot, entry) {
  const wf = join(targetRoot, ".github", "workflows", entry.file);
  const vy = join(targetRoot, "version.yml");
  if (!existsSync(wf) || !existsSync(vy)) return { carried: [] };

  const vyText = readFileSync(vy, "utf8");
  if (/^\s*issue_helper:/m.test(vyText)) return { carried: [] }; // New-form settings win

  const vals = parseWithValues(readFileSync(wf, "utf8"));
  const carried = {};
  for (const [k, v] of Object.entries(vals)) {
    if (v !== OLD_DEFAULTS[k]) carried[k] = v; // Only values that differ from defaults
  }
  if (Object.keys(carried).length === 0) return { carried: [] };

  writeFileSync(vy, insertIssueHelperBlock(vyText, carried));
  return { carried: Object.keys(carried) };
}

export const EXTRACTORS = {
  "suh-issue-helper-module": extractIssueHelperModule,
};
