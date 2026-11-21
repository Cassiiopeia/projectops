// Shared skill folder copy (Cursor, Copilot): skills/ + shared Python scripts/ > home install root, tests excluded, obsolete cleanup, meta record
// Kept in one place so IDEs that read SKILL.md folders directly without a marketplace use the same rules.
// Install layout matches the plugin cache: <install root>/skills/pro-*/scripts/x_cli.py + <install root>/scripts/common
//   (the skill CLI bootstrap uses scripts/ three levels above x_cli.py as an import path)
import { dirname, join, relative } from "node:path";
import { existsSync, readFileSync, mkdirSync, rmSync, writeFileSync, readdirSync } from "node:fs";
import { copyPathSync } from "../fsutil.js";
import { TEMPLATE_REPO_WEB_URL } from "../paths.js";

// Not needed by skill users. These are tests that check projectops itself.
// skills/ is copied whole, so without filtering here they pile up in the user's home.
export const SKIP_IN_COPY = new Set(["conftest.py", "pytest.ini"]);
export const TEST_PATH = /(^|[\\/])(tests?|__pycache__)([\\/]|$)/;
// Our skill prefixes: pro- current, suh- old name
const OWNED_SKILL_NAME = /^(pro|suh)-/;
// Shared Python package marker: scripts/common/__init__.py
const SHARED_SCRIPTS_MARKER = join("common", "__init__.py");
export const SHARED_SCRIPTS_DIR_NAME = "scripts";
const PYTHON_CACHE_DIR_NAME = "__pycache__";
// Top-level shared entries used only by repo maintainers: guide doc, troubleshooting index generator, extras copy sync (#988), project type generator (#1244)
// Why an exclude list, not an allow list: missing a new runtime module kills skills on import,
// while missing a new dev file only ships one extra file. test/ide-home-install-e2e.test.js catches runtime entries landing here
export const SHARED_SCRIPTS_DEV_ONLY = new Set(["README.md", "build_troubleshooting.py", "sync_extras.py", "build_project_types.mjs"]);

// Skill source: downloaded template (TEMP)/skills first, else local skills/
export function resolveSkillsSrc(ctx = {}) {
  const cands = [ctx.sourceSkillsDir, ctx.tempDir && join(ctx.tempDir, "skills"), "skills"].filter(Boolean);
  for (const c of cands) if (existsSync(c)) return c;
  return "";
}

// Shared Python source: explicit > template (TEMP)/scripts > scripts/ next to the skill source (same repo)
export function resolveScriptsSrc(ctx = {}, skillsSrc = "") {
  const cands = [ctx.sourceScriptsDir, ctx.tempDir && join(ctx.tempDir, SHARED_SCRIPTS_DIR_NAME),
    skillsSrc && join(dirname(skillsSrc), SHARED_SCRIPTS_DIR_NAME)].filter(Boolean);
  for (const c of cands) if (existsSync(join(c, SHARED_SCRIPTS_MARKER))) return c;
  return "";
}

// Meta file > {installed, version, sharedScripts} (corrupt meta counts as installed)
export function readSkillsMeta(metaFile) {
  if (!existsSync(metaFile)) return { installed: false, version: null, sharedScripts: [] };
  try {
    const meta = JSON.parse(readFileSync(metaFile, "utf8"));
    return { installed: true, version: meta.version || null, sharedScripts: Array.isArray(meta.sharedScripts) ? meta.sharedScripts : [] };
  } catch { return { installed: true, version: null, sharedScripts: [] }; }
}

// Copy top-level source entries (tests and conftest excluded). The filter uses paths relative to the source —
// with absolute paths, everything would be filtered when the source sits under ~/test/....
// skipNames: extra top-level names to leave out (dev-only shared Python entries)
function copyEntriesWithoutTests(src, dest, skipNames = new Set()) {
  mkdirSync(dest, { recursive: true });
  const copiedNames = [];
  for (const e of readdirSync(src, { withFileTypes: true })) {
    if (SKIP_IN_COPY.has(e.name) || TEST_PATH.test(e.name) || skipNames.has(e.name)) continue;
    // Tests that check this repo's own code have no reason to go to someone else's computer (#591).
    copyPathSync(join(src, e.name), join(dest, e.name), (p) => !TEST_PATH.test(relative(src, p)));
    copiedNames.push(e.name);
  }
  return copiedNames;
}

/**
 * Copy skills: source > dest (tests excluded) > remove our skills that vanished from the source
 * Returns the list of obsolete skill names. Copy failures are thrown (the caller logs and returns false).
 */
export function copySkillsTree(src, dest, metaFileName) {
  copyEntriesWithoutTests(src, dest);
  // The copy is an overlay, so overwriting alone leaves **obsolete skills on users' computers forever**, still picked up (#500).
  // Others' skills are filtered out by prefix and left untouched.
  const srcNames = new Set(readdirSync(src));
  const obsoleteNames = [];
  for (const name of readdirSync(dest)) {
    if (srcNames.has(name) || name === metaFileName) continue;
    if (!OWNED_SKILL_NAME.test(name)) continue;
    try {
      rmSync(join(dest, name), { recursive: true, force: true });
      obsoleteNames.push(name);
    } catch { /* ignore — keep installing even if it cannot be deleted */ }
  }
  return obsoleteNames;
}

// Replace-copy the shared Python: remove last install's entries > copy runtime entries only (so obsolete modules and old dev files do not linger). Returns copied entry names
function replaceSharedScripts(scriptsSrc, scriptsDest, previousNames) {
  removeNamedEntries(scriptsDest, previousNames);
  return copyEntriesWithoutTests(scriptsSrc, scriptsDest, SHARED_SCRIPTS_DEV_ONLY);
}

// Delete the name list + __pycache__ made by Python runs > delete the folder too if empty
function removeNamedEntries(dir, names) {
  for (const name of [...names, PYTHON_CACHE_DIR_NAME]) {
    // Names come from meta, so block path traversal (../)
    if (!name || name.includes("/") || name.includes("\\") || name === "..") continue;
    rmSync(join(dir, name), { recursive: true, force: true });
  }
  if (existsSync(dir) && readdirSync(dir).length === 0) rmSync(dir, { recursive: true, force: true });
}

/**
 * One home install: copy skills > replace-copy shared Python > record meta
 * Returns {obsoleteNames, hasSharedScripts}. Failures are thrown.
 */
export function installHomeSkills({ skillsSrc, scriptsSrc, skillsDest, metaFileName, templateVersion }) {
  const metaFile = join(skillsDest, metaFileName);
  const previousSharedScripts = readSkillsMeta(metaFile).sharedScripts;
  const obsoleteNames = copySkillsTree(skillsSrc, skillsDest, metaFileName);
  const scriptsDest = join(dirname(skillsDest), SHARED_SCRIPTS_DIR_NAME);
  const sharedScripts = scriptsSrc ? replaceSharedScripts(scriptsSrc, scriptsDest, previousSharedScripts) : previousSharedScripts;
  writeSkillsMeta(skillsDest, metaFileName, templateVersion, { sharedScripts });
  return { obsoleteNames, hasSharedScripts: !!scriptsSrc };
}

// Entries considered installed here by projectops: source folder names ∪ pro-/suh- prefixes ∪ meta file
// Folders without the prefix (others' skills like somansa-tools) are excluded → kept
export function ownedEntries(dir, ctx, metaFileName) {
  if (!existsSync(dir)) return [];
  let srcNames = new Set();
  const src = resolveSkillsSrc(ctx);
  if (src && existsSync(src)) srcNames = new Set(readdirSync(src));
  // Obsolete skills are not in the source, so srcNames does not catch them (#619).
  return readdirSync(dir).filter((name) => srcNames.has(name) || OWNED_SKILL_NAME.test(name) || name === metaFileName);
}

// Delete only our entries (including shared Python listed in meta) > delete the folder too if empty. Failures are thrown.
export function removeOwnedEntries(dir, ctx, metaFileName) {
  const { sharedScripts } = readSkillsMeta(join(dir, metaFileName));
  for (const name of ownedEntries(dir, ctx, metaFileName)) rmSync(join(dir, name), { recursive: true, force: true });
  if (existsSync(dir) && readdirSync(dir).length === 0) rmSync(dir, { recursive: true, force: true });
  const scriptsDest = join(dirname(dir), SHARED_SCRIPTS_DIR_NAME);
  if (sharedScripts.length && existsSync(scriptsDest)) removeNamedEntries(scriptsDest, sharedScripts);
}

// Record meta: for version tracking (installedAt keeps the first install time). extraFields: sharedScripts, etc.
export function writeSkillsMeta(destDir, metaFileName, templateVersion, extraFields = {}) {
  const version = templateVersion || "unknown";
  const now = new Date().toISOString().replace(/\.\d+Z$/, "Z");
  const file = join(destDir, metaFileName);
  let installedAt = now;
  if (existsSync(file)) { try { installedAt = JSON.parse(readFileSync(file, "utf8")).installedAt || now; } catch { /* harmless */ } }
  const meta = {
    name: "projectops", version, scope: "user",
    source: TEMPLATE_REPO_WEB_URL,
    installPath: destDir, installedAt, lastUpdated: now,
    ...extraFields,
  };
  mkdirSync(destDir, { recursive: true });
  writeFileSync(file, JSON.stringify(meta, null, 2) + "\n");
}
