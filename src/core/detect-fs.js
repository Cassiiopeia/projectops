// Project detection on the real filesystem.
// Drives the SP2-A detect.js pure functions with fs/git.
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { join, basename } from "node:path";
import { execFileSync } from "node:child_process";
import { detectTypesFromMarkers, detectVersionFromFiles, suggestTypesByExtScan } from "./detect.js";
import { parseExisting, convertLegacySingularType } from "./version-yml.js";
import { VALID_TYPES } from "../context.js";
import { PROJECT_TYPES } from "./project-types.js";

const hasFile = (root) => (rel) => existsSync(join(root, rel));
const readFile = (root) => (rel) => {
  try { return readFileSync(join(root, rel), "utf8"); } catch { return null; }
};

function gitOut(root, args) {
  try {
    return execFileSync("git", args, { cwd: root, encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }).trim();
  } catch { return ""; }
}

// File list for the extension scan (depth≤3, vendor folders pruned).
const SCAN_PRUNE = new Set([
  "node_modules", ".git", "build", "dist", ".dart_tool",
  "android", "ios", ".gradle", "venv", ".venv", "__pycache__",
  // Keeps the template's own .github/scripts/*.py from being misdetected as python (#671)
  ".github",
  // Template download folder of this installer (holds the template's own scripts)
  ".template_download_temp",
]);
export function listScanFiles(root, maxDepth = 3) {
  const files = [];
  const walk = (rel, depth) => {
    if (depth > maxDepth) return;
    let entries;
    try { entries = readdirSync(join(root, rel), { withFileTypes: true }); } catch { return; }
    for (const e of entries) {
      const childRel = rel ? `${rel}/${e.name}` : e.name;
      if (e.isDirectory()) {
        if (!SCAN_PRUNE.has(e.name)) walk(childRel, depth + 1);
      } else {
        files.push(childRel);
      }
    }
  };
  walk("", 1);
  return files;
}

// Monorepo marker scan: folders up to 2 levels down, a folder with markers is a project (not descended into) (#1243)
const MONOREPO_MARKER_DEPTH = 2;
// Registry order = root scan order (first = primary type)
const MARKER_TYPE_ORDER = VALID_TYPES;
export function detectTypesInSubfolders(root, maxDepth = MONOREPO_MARKER_DEPTH) {
  const found = [];
  const walk = (rel, depth) => {
    if (depth > maxDepth) return;
    let entries;
    try { entries = readdirSync(join(root, rel), { withFileTypes: true }); } catch { return; }
    for (const e of entries) {
      if (!e.isDirectory() || e.name.startsWith(".") || SCAN_PRUNE.has(e.name)) continue;
      const childRel = rel ? `${rel}/${e.name}` : e.name;
      const dir = join(root, childRel);
      const types = detectTypesFromMarkers({ has: hasFile(dir), read: readFile(dir) });
      if (types.length === 1 && types[0] === "basic") walk(childRel, depth + 1);
      else found.push(...types);
    }
  };
  walk("", 1);
  // Same order as the root scan (first = primary type), not folder name order
  const unique = [...new Set(found)].sort((left, right) => MARKER_TYPE_ORDER.indexOf(left) - MARKER_TYPE_ORDER.indexOf(right));
  // Same rule as the root scan: a plain node folder (tooling scripts) does not count next to a real project
  const fallbackIds = new Set(PROJECT_TYPES.filter((type) => type.detect.fallback_only).map((type) => type.id));
  return unique.length > 1 ? unique.filter((type) => !fallbackIds.has(type)) : unique;
}

// Type detection — version.yml project_types first (source of truth), else a marker scan.
// No root markers: markers in subfolders (monorepo, #1243), then a recommendation from extension frequency (#458).
export function detectTypes(root) {
  const vy = join(root, "version.yml");
  if (existsSync(vy)) {
    const { types } = parseExisting(readFileSync(vy, "utf8"));
    if (types.length) return types; // Includes basic; use as is when explicit
    // Singular project_type key from before v4.1.0 (#718) — restore the explicit value even without markers.
    // Otherwise a repo without markers drops to basic and the existing type's workflows are orphaned.
    const legacy = (convertLegacySingularType(readFileSync(vy, "utf8")) || "").match(/^project_types: \["([a-z-]+)"\]/m);
    if (legacy && VALID_TYPES.includes(legacy[1])) return [legacy[1]];
  }
  const byMarkers = detectTypesFromMarkers({ has: hasFile(root), read: readFile(root) });
  if (byMarkers.length === 1 && byMarkers[0] === "basic") {
    const inSubfolders = detectTypesInSubfolders(root);
    if (inSubfolders.length) return inSubfolders; // Folders are settled by resolveProjectPaths (single candidate > automatic)
    const scanned = suggestTypesByExtScan(listScanFiles(root));
    if (scanned.length) return scanned; // Recommendation — the user confirms it in the wizard's confirm/edit loop
  }
  return byMarkers;
}

// Version detection. jq availability is judged by the command existing.
export function detectVersion(root, { hasJq } = {}) {
  const read = readFile(root);
  const readJson = (rel) => { const c = read(rel); try { return c ? JSON.parse(c) : null; } catch { return null; } };
  const jq = hasJq ?? hasCommand("jq");
  const gitTag = gitOut(root, ["describe", "--tags", "--abbrev=0"]);
  return detectVersionFromFiles({ read, readJson, hasJq: jq, gitTag });
}

// Default branch detection — symbolic-ref → remote show → main.
export function detectDefaultBranch(root) {
  let b = gitOut(root, ["symbolic-ref", "refs/remotes/origin/HEAD"]);
  if (b) return b.replace(/^refs\/remotes\/origin\//, "");
  const show = gitOut(root, ["remote", "show", "origin"]);
  const m = show.match(/HEAD branch:\s*(\S+)/);
  if (m) return m[1];
  // Local repo without origin (#477) — the current HEAD branch is the best guess (fixable in the interactive edit menu)
  const head = gitOut(root, ["branch", "--show-current"]);
  if (head) return head;
  return "main";
}

// Repo name — last segment of git remote get-url origin, folder name on failure.
export function detectRepoName(root) {
  const url = gitOut(root, ["remote", "get-url", "origin"]);
  if (url) {
    const seg = url.replace(/\.git$/, "").split(/[/:]/).pop();
    if (seg) return seg;
  }
  return basename(root);
}

function hasCommand(cmd) {
  try {
    execFileSync(process.platform === "win32" ? "where" : "which", [cmd], { stdio: "ignore" });
    return true;
  } catch { return false; }
}

// Find Spring application*.yml
// fs recursive version of find {base} -path "*/src/main/resources/application*.yml" | head -1.
// Returns a path relative to root (e.g. "server/src/main/resources/application.yml") or "".
export function findSpringAppYml(root, base = ".") {
  const startRel = base === "." ? "" : base;
  const PRUNE = new Set(["node_modules", ".git", "build", ".gradle", "target", ".idea"]);
  let hit = "";
  const walk = (rel, depth) => {
    if (hit || depth > 8) return; // Equivalent to head -1 — stop at the first match
    let entries;
    try { entries = readdirSync(join(root, rel), { withFileTypes: true }); } catch { return; }
    // Sort to make traversal order deterministic (removes platform differences in find order)
    for (const e of entries.sort((a, b) => a.name.localeCompare(b.name))) {
      if (hit) return;
      const childRel = rel ? `${rel}/${e.name}` : e.name;
      if (e.isDirectory()) {
        if (PRUNE.has(e.name)) continue;
        walk(childRel, depth + 1);
      } else if (/^application.*\.yml$/.test(e.name) && childRel.includes("src/main/resources/")) {
        hit = childRel;
      }
    }
  };
  walk(startRel, 0);
  return hit;
}

// Builds the real set of resolvers — shared by index and interactive.
// paths: Map<type, path> (monorepo paths).
export function makeResolvers(root, repoName, paths) {
  const springBase = (t) => paths.get(t || "spring") || paths.get("spring") || ".";
  return {
    repo: () => repoName,
    "spring-app-yml-dir": (t) => {
      const f = findSpringAppYml(root, springBase(t));
      return f ? f.split("/").slice(0, -1).join("/") : "";
    },
    "spring-app-yml-path": (t) => findSpringAppYml(root, springBase(t)) || "",
    // Type folder resolvers (APP_ROOT of app workflows): registry root_resolver names, e.g. flutter-root, expo-root
    ...Object.fromEntries(PROJECT_TYPES.filter((type) => type.root_resolver)
      .map((type) => [type.root_resolver, () => paths.get(type.id) || "."])),
  };
}
