// Detect and settle per-type project paths. In a monorepo, decides which folder holds
// each type's version file using a 5-step priority.
//
// io injection contract (same signatures as readline-engine):
//   io.select({message, options:[{value,label}]}) → value | CANCEL(symbol)
//   io.text({message, defaultValue})              → string | CANCEL
//   io.confirm({message, initialValue})           → bool | CANCEL
//   io.log(line)                                   → notice output (stderr if missing)
import { existsSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { t as msg } from "../i18n/index.js";
import { markerForType as baseMarkerForType, extraMarkers } from "./detect.js";
import { PROJECT_TYPES, typeById } from "./project-types.js";
import { normalizePath } from "../cli/args.js";

// Cancel (ESC/Ctrl+C) is the CANCEL symbol — judged only by symbol identity, without importing ui (avoids a core→ui back reference)
const isCancel = (v) => typeof v === "symbol";

// Main marker file name of a type.
// detect.js returns package.json for unknown types by default — wrapped here so it becomes an empty string.
const KNOWN_MARKER_TYPES = new Set(PROJECT_TYPES.filter((type) => type.path_search.files.length).map((type) => type.id));
export function markerForType(type) {
  return KNOWN_MARKER_TYPES.has(type) ? baseMarkerForType(type) : "";
}

// Returns the marker file name that actually exists in the directory — including secondary markers, else the main marker (for display).
// (spring build.gradle/.kts/pom.xml, python pyproject/setup.py/requirements.txt)
export function existingMarkerInDir(type, dir) {
  const primary = markerForType(type);
  const names = primary ? [primary, ...extraMarkers(type)] : [];
  for (const n of names) {
    if (existsSync(join(dir, n))) return n;
  }
  return primary;
}

// Recursive file search with maxdepth 3 — collects the relative "directory" path of matching files (root is ".").
// find's maxdepth counts path components of the file (./a/b/f = depth 3), so compute the same way.
function walkFindDirs(root, { prune, match, maxDepth = 3 }) {
  const hits = [];
  const walk = (rel, depth) => {
    let entries;
    try { entries = readdirSync(join(root, rel || "."), { withFileTypes: true }); } catch { return; }
    for (const e of entries) {
      const childDepth = depth + 1;
      const childRel = rel ? `${rel}/${e.name}` : e.name;
      if (e.isDirectory()) {
        // Pruned folders exclude everything below them
        if (prune.has(e.name)) continue;
        // Descend only when child files stay within depth ≤ maxDepth
        if (childDepth < maxDepth) walk(childRel, childDepth);
        // Files inside a directory at childDepth === maxDepth-0 are at depth maxDepth+1 → find does not see them
        else if (childDepth === maxDepth) { /* Files only up to maxDepth — no need to descend */ }
      } else if (childDepth <= maxDepth && match(e.name)) {
        hits.push(rel === "" ? "." : rel);
      }
    }
  };
  walk("", 0);
  return [...new Set(hits)].sort(); // Dedupe + sort
}

// Search marker file candidates per type.
// Returns an array of candidate directory relative paths (root is ".").
export function findTypePathCandidates(root, type) {
  const search = typeById(type)?.path_search;
  if (!search || !search.files.length) return [];

  // ── Spring multi-module: collapse to the settings.gradle(.kts) folder = module root ──
  // version_manager updates every build.gradle under that folder, so submodules are not expanded.
  // settings.gradle under android/ (Flutter/RN) is not spring, so prune it.
  if (search.gradle_settings_root) {
    const mm = walkFindDirs(root, {
      prune: new Set(["node_modules", ".git", "build", "dist", ".gradle", "android", "ios"]),
      match: (n) => n === "settings.gradle" || n === "settings.gradle.kts",
    });
    if (mm.length) return mm;
    // No settings.gradle → single module, fall back to build.gradle below
  }

  const prune = new Set([
    "node_modules", ".git", "build", "dist", ".dart_tool", "android", "ios",
    ".gradle", "venv", ".venv", "__pycache__",
  ]);
  // If found by a higher-priority marker, use only that
  let found = [];
  for (const n of search.files) {
    found = walkFindDirs(root, { prune, match: (name) => name === n });
    if (found.length) break;
  }

  return found.filter((d) => {
    // Exclude false hits: example apps (flutter), android/build.gradle of app projects (spring)
    if ((search.exclude_parts || []).some((part) => d.includes(part))) return false;
    // Required sibling folder (flutter lib/) — avoids false hits
    if (search.require_dir && !existsSync(d === "." ? join(root, search.require_dir) : join(root, d, search.require_dir))) return false;
    return true;
  });
}

// Detect and confirm paths for all selected types and settle a Map<type,path>
// (5-step priority).
//   ① already in paths (--paths) → keep
//   ② marker at the root → "." automatically
//   ③ existingPaths (saved in version.yml)
//   ④ candidate scan
//   ⑤ branch — non-interactive: existing value → single candidate → root fallback / interactive: confirm, select, manual input
export async function resolveProjectPaths({
  root, types = [], paths = new Map(), existingPaths = new Map(),
  force = false, tty = true, io = {},
}) {
  const say = io.log || ((m) => process.stderr.write(`${m}\n`));
  const result = new Map(paths); // Keep --paths presets (the caller's Map is not mutated)
  const targets = types.filter((t) => t !== "basic"); // basic needs no path
  if (targets.length === 0) return result;

  const total = targets.length;
  // ── Intro notice (detection result + what will happen) ──
  say("");
  if (total > 1) say(msg("paths.multi", { total }));
  else say(msg("paths.single", { type: targets[0] }));
  for (const t of targets) say(`   • ${t.padEnd(8)} → ${existingMarkerInDir(t, root)}`);
  say("");
  say(msg("paths.rootDef"));
  say("");

  let idx = 0;
  for (const t of targets) {
    idx += 1;
    const prog = `[${idx}/${total}]`;

    // ① already given via --paths etc. → top priority
    if (result.get(t)) {
      say(msg("paths.byFlag", { type: t, path: result.get(t) }));
      continue;
    }

    // ② marker at the root → settle "." automatically (including secondary markers)
    const rootMarker = existingMarkerInDir(t, root);
    if (rootMarker && existsSync(join(root, rootMarker))) {
      result.set(t, ".");
      say(msg("paths.atRoot", { type: t, marker: rootMarker }));
      continue;
    }

    // ③ saved value in the existing version.yml → default suggestion
    const existing = existingPaths.get(t) || "";

    // ④ candidate search
    const candidates = findTypePathCandidates(root, t);
    let chosen = "";

    // ── ⑤-a non-interactive (--force or no TTY) ──
    if (force || !tty) {
      if (existing) {
        chosen = existing;
        say(msg("paths.keptSaved", { type: t, path: chosen }));
      } else if (candidates.length === 1) {
        chosen = candidates[0];
        say(msg("paths.autoDetected", { type: t, path: chosen }));
      } else {
        chosen = ".";
        say(msg("paths.ambiguous", { type: t, count: candidates.length }));
      }
      result.set(t, chosen);
      continue;
    }

    // ── ⑤-b interactive: branch by candidate count + type escape hatch (#487) ──
    const EXCLUDE = "이 타입 제외"; // Sentinel — exposed as a Korean value (same pattern as the existing "직접 입력")
    let excluded = false;
    if (candidates.length === 1) {
      const cand = candidates[0];
      const candMarker = existingMarkerInDir(t, cand === "." ? root : join(root, cand));
      const candFull = cand === "." ? candMarker : `${cand}/${candMarker}`;
      say("");
      say(msg("paths.found", { prog, type: t, marker: candMarker }));
      say(msg("paths.location", { file: candFull }));
      const sel = await io.select({
        message: msg("paths.confirmPrompt", { type: t, cand }),
        options: [
          { value: cand, label: msg("paths.confirmYes", { cand, file: candFull }) },
          { value: "직접 입력", label: msg("paths.confirmManual") },
          { value: EXCLUDE, label: msg("paths.exclude", { type: t }) },
        ],
      });
      if (sel === EXCLUDE) excluded = true;
      else if (!isCancel(sel) && sel != null && sel !== "직접 입력") chosen = sel;
      // ESC/manual input → manual input loop below
    } else if (candidates.length > 1) {
      say("");
      say(msg("paths.multiFound", { prog, type: t, count: candidates.length }));
      // Candidates + 'manual input'/'exclude this type' menu — the value itself is Korean (avoids exposing a sentinel)
      const options = candidates.map((c) => ({
        value: c,
        label: `${c} (${existingMarkerInDir(t, c === "." ? root : join(root, c))})`,
      }));
      options.push({ value: "직접 입력", label: msg("paths.manual") });
      options.push({ value: EXCLUDE, label: msg("paths.exclude", { type: t }) });
      const sel = await io.select({ message: msg("paths.selectPrompt", { type: t }), options });
      // ESC (cancel) also falls back to manual input
      if (sel === EXCLUDE) excluded = true;
      else if (!isCancel(sel) && sel != null && sel !== "직접 입력") chosen = sel;
    } else {
      say("");
      say(msg("paths.notFound", { prog, type: t }));
    }

    // ── Manual input loop (when not settled above) — includes the exclude escape hatch (#487) ──
    while (!chosen && !excluded) {
      const hintMarker = existingMarkerInDir(t, root);
      let prompt = msg("paths.inputPrompt", { type: t, marker: hintMarker });
      if (existing) prompt += msg("paths.inputCurrent", { value: existing });
      prompt += "): ";
      let input = await io.text({ message: prompt, defaultValue: "" });
      if (isCancel(input) || input == null) input = ""; // ESC → empty (fallback below)
      input = String(input).trim();
      // Empty → existing value or root — decided before normalizePath
      input = input === "" ? (existing || ".") : normalizePath(input);
      // Validate: check the marker exists at the entered path (including secondary markers)
      const m = existingMarkerInDir(t, input === "." ? root : join(root, input));
      if (m && existsSync(join(root, input === "." ? "" : input, m))) {
        chosen = input;
      } else {
        say(msg("paths.missingFile", { path: input, marker: m }));
        const act = await io.select({
          message: msg("paths.actionPrompt"),
          options: [
            { value: "retry", label: msg("paths.retry") },
            { value: "force", label: msg("paths.force", { path: input }) },
            { value: EXCLUDE, label: msg("paths.exclude", { type: t }) },
          ],
        });
        if (act === "force") chosen = input;
        else if (act === EXCLUDE) excluded = true;
        // retry/ESC → keep looping
      }
    }

    if (excluded) {
      say(msg("paths.excluded", { type: t }));
      continue;
    }

    result.set(t, chosen);
    say(`  ✅ ${t} → ${chosen}`);
  }

  // ── Summary + warning for duplicate marker files ──
  say("");
  say(msg("paths.summary"));
  const fileToTypes = new Map(); // Marker file relative path → types using that file
  for (const [pt, pp] of result) {
    const m = existingMarkerInDir(pt, pp === "." ? root : join(root, pp));
    const file = pp === "." ? m : `${pp}/${m}`;
    say(`   ${pt} → ${file}`);
    if (!fileToTypes.has(file)) fileToTypes.set(file, []);
    fileToTypes.get(file).push(pt);
  }
  for (const [file, ts] of fileToTypes) {
    if (ts.length > 1) {
      // Idempotent, so warn only instead of blocking
      say(msg("paths.duplicate", { types: ts.join(" "), file }));
      say(msg("paths.duplicateNote"));
    }
  }
  say("");
  return result;
}

// Apply types excluded at the path step (#487) — remove non-basic types missing from paths.
// If all are excluded, fall back to basic (zero types is not allowed). No-op for non-interactive, which cannot exclude.
export function filterExcludedTypes(types, paths) {
  const kept = types.filter((t) => t === "basic" || paths.has(t));
  return kept.length ? kept : ["basic"];
}
