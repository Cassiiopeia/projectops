// Scripts the template workflows run, plus the local files those scripts load (#1288).
// Workflows > referenced script paths > closure over local imports and sibling file names.
// The copy list in simple.js stays the documented set; this closure is the guard that keeps
// a script a workflow calls from being left out of user repos when the list falls behind.
import { join, posix } from "node:path";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { PATHS } from "../paths.js";
import { exists } from "../fsutil.js";

// Workflow call forms: `.github/scripts/<path>` and `$SCRIPTS_DIR/<path>` / `${CI_SCRIPTS_DIR...}/<path>` (default-branch copy, #1006)
const WORKFLOW_SCRIPT_REFERENCE = /(?:\.github\/scripts|SCRIPTS_DIR\}?)\/([A-Za-z0-9_]+(?:\/[A-Za-z0-9_]+)*\.(?:py|sh))/g;
// Inside a script: `import a, b` / `from a import x` (first module segment only)
const PYTHON_IMPORT = /^[ \t]*(?:from[ \t]+([A-Za-z_][A-Za-z0-9_]*)[\w.]*[ \t]+import|import[ \t]+([A-Za-z_][A-Za-z0-9_, \t]*))/gm;
// Inside a script: a sibling file named by string (shell shims, subprocess calls such as the changelog ladder)
const SIBLING_FILE_NAME = /\b([A-Za-z0-9_]+\.(?:py|sh))\b/g;
// Folders copied whole elsewhere (simple.js i18n block), so their files are not listed here
const WHOLE_COPIED_FOLDERS = new Set(["i18n"]);

function listWorkflowFiles(directory) {
  if (!exists(directory)) return [];
  const files = [];
  for (const name of readdirSync(directory)) {
    const path = join(directory, name);
    if (statSync(path).isDirectory()) files.push(...listWorkflowFiles(path));
    else if (/\.ya?ml$/.test(name)) files.push(path);
  }
  return files;
}

function isWholeCopied(relativePath) {
  return WHOLE_COPIED_FOLDERS.has(relativePath.split("/")[0]);
}

// Relative script path ("a.py", "changelog_providers/b.py") > local files it loads, relative to the scripts folder
function findLocalDependencies(scriptsRoot, relativePath) {
  const text = readFileSync(join(scriptsRoot, relativePath), "utf8");
  const folder = posix.dirname(relativePath) === "." ? "" : posix.dirname(relativePath);
  const candidates = new Set();
  for (const match of text.matchAll(SIBLING_FILE_NAME)) candidates.add(match[1]);
  if (relativePath.endsWith(".py")) {
    for (const match of text.matchAll(PYTHON_IMPORT)) {
      const modules = match[1] ? [match[1]] : match[2].split(",").map((m) => m.trim().split(/\s+/)[0]);
      for (const module of modules) if (module) candidates.add(`${module}.py`);
    }
  }
  // Resolve next to the script first, then at the scripts root (scripts add both to sys.path)
  const dependencies = [];
  for (const name of candidates) {
    for (const base of [folder, ""]) {
      const candidate = base ? `${base}/${name}` : name;
      if (exists(join(scriptsRoot, candidate))) { dependencies.push(candidate); break; }
    }
  }
  return dependencies;
}

/**
 * Template workflows (project-types) > every script they need, relative to .github/scripts
 * Missing files are skipped (a workflow may name an optional script)
 */
export function collectReferencedScripts(tempDir) {
  const scriptsRoot = join(tempDir, PATHS.scriptsDir);
  const workflowRoot = join(tempDir, ".github", "workflows", "project-types");
  const pending = [];
  for (const file of listWorkflowFiles(workflowRoot)) {
    for (const match of readFileSync(file, "utf8").matchAll(WORKFLOW_SCRIPT_REFERENCE)) pending.push(match[1]);
  }
  const found = new Set();
  while (pending.length) {
    const relativePath = pending.pop();
    if (found.has(relativePath) || isWholeCopied(relativePath)) continue;
    if (!exists(join(scriptsRoot, relativePath))) continue;
    found.add(relativePath);
    pending.push(...findLocalDependencies(scriptsRoot, relativePath));
  }
  return [...found].sort();
}
