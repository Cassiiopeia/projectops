// Post-install verification (#549) — rereads installed workflows to see "will this run as is".
//
// Why after, not before install: substitution happens scattered per file, and auto tokens depend on
// resolver results. Looking at the final disk content is the only way to see what will actually deploy.
import { join } from "node:path";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { PATHS } from "./paths.js";

// Tokens that are not substitution targets — heredoc delimiters inside workflow scripts. They are syntax,
// not values, so they are excluded from the unreplaced check. (e.g. cat <<'__SUH_FILE_CONTENT_EOF__')
const SENTINEL_RE = /^__SUH_[A-Z0-9_]*__$/;
const PLACEHOLDER_RE = /__[A-Z][A-Z0-9_]*__/g;

// Commented-out lines — they never run, so they are not checked.
// Templates ship whole "[optional] ..." sample steps commented out; counting them would
// tell users to "register" secrets they never use.
const isCommented = (line) => /^\s*#/.test(line);

// Files to check. If the caller does not specify, scan every installed workflow
// (looking at the final disk state fits the purpose better than assembling the copy result list).
function listWorkflowFiles(workflowsDir, filenames) {
  if (filenames && filenames.length) return filenames;
  if (!existsSync(workflowsDir)) return [];
  try {
    return readdirSync(workflowsDir, { withFileTypes: true })
      .filter((e) => e.isFile() && /\.ya?ml$/.test(e.name))
      .map((e) => e.name)
      .sort();
  } catch {
    return [];
  }
}

function readLines(workflowsDir, filename) {
  const p = join(workflowsDir, filename);
  if (!existsSync(p)) return null;
  try {
    return readFileSync(p, "utf8").split(/\r?\n/);
  } catch {
    return null;
  }
}

// Unreplaced placeholder scan.
// When an auto token computation fails (e.g. application.yaml not found, empty path), the line is left
// untouched, so a workflow still holding __APPLICATION_YML_DIR__ ends as "install succeeded".
// The problem only shows at deploy time, when a directory with that name gets created.
//
// Returns [{ filename, line, token, text }] — includes line numbers so people can fix it right away.
export function scanUnsubstituted(workflowsDir, filenames = []) {
  const found = [];
  for (const filename of listWorkflowFiles(workflowsDir, filenames)) {
    const lines = readLines(workflowsDir, filename);
    if (!lines) continue;
    lines.forEach((text, i) => {
      if (isCommented(text)) return;
      for (const token of text.match(PLACEHOLDER_RE) || []) {
        if (SENTINEL_RE.test(token)) continue;
        found.push({ filename, line: i + 1, token, text: text.trim() });
      }
    });
  }
  return found;
}

// GITHUB_TOKEN is injected by Actions automatically, so users do not register it.
const AUTO_SECRETS = new Set(["GITHUB_TOKEN"]);

// Secrets the workflow runs without — the fallback is documented. Mixing them with required ones under "needed to work"
// would make the notice itself untrustworthy, so they are kept separate.
//   MODEL_API_KEY      → if registered, external AI summary; otherwise Copilot → commit analysis (#455·#566 ladder)
//   _GITHUB_PAT_TOKEN  → if missing, merge with GITHUB_TOKEN and wake follow-up workflows directly (#551)
export const OPTIONAL_SECRETS = new Set(["MODEL_API_KEY", "_GITHUB_PAT_TOKEN"]);

const SECRET_RE = /secrets\.([A-Z_][A-Z0-9_]*)/g;

// GitHub secrets required by the installed workflows.
// Because the finish screen said nothing, values the deploy workflows actually need, like
// SERVER_HOST and SSH_KEY, never surfaced. Right after install the deploy cannot run,
// and there was no way to know it.
//
// Returns Map<secretName, string[] file names using that secret> (sorted by name)
export function collectRequiredSecrets(workflowsDir, filenames = []) {
  const out = new Map();
  for (const filename of listWorkflowFiles(workflowsDir, filenames)) {
    const lines = readLines(workflowsDir, filename);
    if (!lines) continue;
    for (const line of lines) {
      if (isCommented(line)) continue;
      for (const m of line.matchAll(SECRET_RE)) {
        const name = m[1];
        if (AUTO_SECRETS.has(name) || OPTIONAL_SECRETS.has(name)) continue;
        if (!out.has(name)) out.set(name, []);
        const users = out.get(name);
        if (!users.includes(filename)) users.push(filename);
      }
    }
  }
  return new Map([...out.entries()].sort(([a], [b]) => a.localeCompare(b)));
}

// Entry point run once right after install. Finds the workflow folder under targetRoot.
// Returns { unresolved: [...], secrets: Map, ok: boolean }
export function verifyInstall(targetRoot = ".", filenames = []) {
  const workflowsDir = join(targetRoot, PATHS.workflowsDir);
  const unresolved = scanUnsubstituted(workflowsDir, filenames);
  const secrets = collectRequiredSecrets(workflowsDir, filenames);
  return { unresolved, secrets, ok: unresolved.length === 0 };
}
