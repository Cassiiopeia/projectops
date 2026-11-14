// Store for new templates of skipped workflows (#654).
// Workflows the user modified are kept, not overwritten. Instead, a copy goes to an untracked place
// so the user can compare how the new template differs.
// Never write to .github/workflows — files there run as real workflows on GitHub.
import { join } from "node:path";
import { writeText } from "./fsutil.js";

export const INCOMING_DIR = ".github/.projectops/incoming";
// The folder carries its own ignore rule (same as logs/.gitignore; the root .gitignore is untouched)
export const INCOMING_GITIGNORE = [
  "# New template copies of workflows projectops skipped — not tracked in the repository.",
  "# Temporary material for merge review, overwritten with the latest on every run.",
  "*",
  "!.gitignore",
  "",
].join("\n");

const toLines = (s) => {
  const lines = String(s).split(/\r?\n/);
  if (lines.length && lines[lines.length - 1] === "") lines.pop(); // Drop the empty line made by the trailing newline
  return lines;
};

// Count of added/removed lines. LCS-based, so lines that only moved are not overcounted.
// removed: lines only in the user copy, added: lines only in the new template.
export function lineDiffCounts(userText, incomingText) {
  const a = toLines(userText);
  const b = toLines(incomingText);
  // Trim the common prefix/suffix before LCS (most of a workflow is identical, so the table stays small)
  let s = 0;
  while (s < a.length && s < b.length && a[s] === b[s]) s++;
  let ea = a.length; let eb = b.length;
  while (ea > s && eb > s && a[ea - 1] === b[eb - 1]) { ea--; eb--; }
  const x = a.slice(s, ea); const y = b.slice(s, eb);
  if (x.length * y.length > 25_000_000) {
    // Abnormally large file — approximate by size difference instead of exactness (never fail)
    return { added: y.length, removed: x.length };
  }
  let prev = new Array(y.length + 1).fill(0);
  for (let i = 1; i <= x.length; i++) {
    const cur = new Array(y.length + 1).fill(0);
    for (let j = 1; j <= y.length; j++) {
      cur[j] = x[i - 1] === y[j - 1] ? prev[j - 1] + 1 : Math.max(prev[j], cur[j - 1]);
    }
    prev = cur;
  }
  const common = prev[y.length];
  return { added: y.length - common, removed: x.length - common };
}

// Save the new template into the incoming folder. Returns a path relative to the target (always '/').
export function saveIncoming(targetRoot, filename, content) {
  writeText(join(targetRoot, INCOMING_DIR, ".gitignore"), INCOMING_GITIGNORE);
  writeText(join(targetRoot, INCOMING_DIR, filename), content);
  return `${INCOMING_DIR}/${filename}`;
}
