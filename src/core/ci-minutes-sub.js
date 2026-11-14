// CI minutes saver substitution (#1114) — only with version.yml options.ci_minutes_saver: true.
// Private repos pay for Actions minutes. Cuts CI that runs twice on the same commit, CI on doc-only changes, and macOS runners (10x per minute).
// Not called when off (install output byte-identical). If a pattern is not found (user-edited file), only that transform is skipped.
// Runs before branch substitution — patterns match the raw template (develop).

// Skip CI for PRs that change only docs (paths that select code differ per repo, so the template cannot decide them)
const DOCS_ONLY_PATHS_IGNORE = `    paths-ignore: ["**/*.md", "docs/**", "LICENSE"]   # ci_minutes_saver: docs-only changes skip CI\n`;

// push: event block under on: (child lines indented 4+). Removed only when the block holds just a branches filter
const PUSH_BLOCK_RE = /^ {2}push:[ \t]*\n((?: {4,}.*\n|[ \t]*\n)*)/m;

// CI running twice for the same change via PR and push > drop push (PR only)
function dropPushTrigger(s) {
  const pushBlock = s.match(PUSH_BLOCK_RE);
  if (!pushBlock) return s;
  const children = pushBlock[1].split("\n").filter((line) => line.trim() && !line.trim().startsWith("#"));
  const isBranchFilterOnly = children.every((line) => /^\s+(branches:|-\s)/.test(line));
  return isBranchFilterOnly ? s.replace(PUSH_BLOCK_RE, "") : s;
}

// Add doc path exclusions right under the events (pull_request · push)
function addDocsPathsIgnore(s, event) {
  const re = new RegExp(`^( {2}${event}:[ \\t]*\\n)`, "m");
  if (!re.test(s) || s.includes("ci_minutes_saver: docs-only")) return s;
  return s.replace(re, `$1${DOCS_ONLY_PATHS_IGNORE}`);
}

// Turn off automatic iOS (macOS runner) builds — enabled only via the manual input enable_ios
function disableIosByDefault(s) {
  // Eat one trailing space for each added character to keep the comment column aligned
  return s.replace(/^( {2}ENABLE_IOS: )"true" ?/m, `$1"false"`);
}

// File name (exact match) > transforms to apply. Store deploys and comment-triggered builds are not included
export const CI_MINUTES_SAVER_RULES = new Map([
  ["PROJECT-FLUTTER-CI.yaml", [dropPushTrigger, (s) => addDocsPathsIgnore(s, "pull_request"), disableIosByDefault]],
  ["PROJECT-PYTHON-CI.yaml", [dropPushTrigger, (s) => addDocsPathsIgnore(s, "pull_request")]],
  ["PROJECT-SPRING-NEXUS-CI.yml", [dropPushTrigger, (s) => addDocsPathsIgnore(s, "pull_request")]],
  // No PR trigger, so keep push and filter only doc changes
  ["PROJECT-REACT-CI.yaml", [(s) => addDocsPathsIgnore(s, "push")]],
  // Jobs unrelated to pushes > manual runs only
  ["PROJECT-COMMON-SECRET-FILE-UPLOAD.yaml", [dropPushTrigger]],
]);

export function substituteCiMinutesSaver(content, filename = "") {
  const transforms = CI_MINUTES_SAVER_RULES.get(filename);
  if (!transforms) return content;
  return transforms.reduce((s, transform) => transform(s), String(content));
}
