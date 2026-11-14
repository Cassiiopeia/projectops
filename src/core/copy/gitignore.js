// Ensure .gitignore (normalize entries > check missing > add).
import { join } from "node:path";
import { existsSync, readFileSync, writeFileSync } from "node:fs";

const REQUIRED_ENTRIES = ["/.idea", "/.claude/settings.local.json"];

// Normalize an entry: strip comment, trim, drop leading /, leading ./ and trailing /. Original if empty.
export function normalizeGitignoreEntry(entry) {
  let e = String(entry);
  e = e.replace(/#.*$/, "");        // Strip comment
  e = e.trim();                      // Trim whitespace
  e = e.replace(/^\//, "");         // Leading /
  e = e.replace(/^\.\//, "");       // Leading ./
  e = e.replace(/\/$/, "");         // Trailing /
  return e === "" ? String(entry) : e;
}

function entryExists(target, content) {
  const nt = normalizeGitignoreEntry(target);
  for (const line of content.split("\n")) {
    if (/^\s*#/.test(line)) continue;
    if (/^\s*$/.test(line)) continue;
    if (normalizeGitignoreEntry(line) === nt) return true;
  }
  return false;
}

const NEW_FILE_CONTENT =
  "# IDE Settings\n" +
  "/.idea\n" +
  "\n" +
  "# Claude AI Settings\n" +
  "/.claude/settings.local.json\n";

// Returns {created, added:[...]}
export function ensureGitignore(targetRoot = ".") {
  const p = join(targetRoot, ".gitignore");
  if (!existsSync(p)) {
    writeFileSync(p, NEW_FILE_CONTENT);
    return { created: true, added: REQUIRED_ENTRIES.slice() };
  }
  let content = readFileSync(p, "utf8");
  const toAdd = REQUIRED_ENTRIES.filter((e) => !entryExists(e, content));
  if (toAdd.length === 0) return { created: false, added: [] };

  // Add a newline if the file does not end with one
  if (content.length > 0 && !content.endsWith("\n")) content += "\n";
  content += "\n";
  content += "# ====================================================================\n";
  content += "# projectops: Auto-added entries\n";
  content += "# ====================================================================\n";
  for (const e of toAdd) content += e + "\n";
  writeFileSync(p, content);
  return { created: false, added: toAdd };
}
