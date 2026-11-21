import { PROJECT_TYPES, typeById } from "./project-types.js";

// Types decided by package.json (registry entries with a package_json rule or fallback_only)
const PACKAGE_TYPES = PROJECT_TYPES.filter((type) => type.detect.package_json || type.detect.fallback_only);

// Dependency keys of a parsed package.json (dependencies + devDependencies; peer and optional are ignored)
function dependencyNames(packageJson) {
  return Object.keys({ ...(packageJson?.dependencies || {}), ...(packageJson?.devDependencies || {}) });
}

// One registry package_json rule against a dependency name list
function matchesPackageRule(rule, names) {
  const hasName = (name) => names.includes(name);
  const hasPrefix = (prefix) => names.some((name) => name.startsWith(prefix));
  if ((rule.requires_all || []).some((name) => !hasName(name))) return false;
  const anyNames = rule.requires_any || [];
  const anyPrefixes = rule.requires_any_prefix || [];
  if ((anyNames.length || anyPrefixes.length) && !anyNames.some(hasName) && !anyPrefixes.some(hasPrefix)) return false;
  if ((rule.excludes_any || []).some(hasName)) return false;
  if ((rule.excludes_any_prefix || []).some(hasPrefix)) return false;
  return true;
}

// Broken JSON: substring rule on the raw text, so detection never fails on a half-written file
function classifyBrokenPackageText(raw) {
  if (raw.includes("@react-native") || raw.includes("react-native")) {
    return raw.includes("expo") ? "react-native-expo" : "react-native";
  }
  if (raw.includes('"react"') || raw.includes('"next"')) return "react";
  return "node";
}

/**
 * Raw package.json text > package type id (registry dependency rules; fallback_only type when none match)
 */
export function classifyPackageText(raw) {
  const text = String(raw || "");
  let packageJson;
  try {
    packageJson = JSON.parse(text);
  } catch {
    return classifyBrokenPackageText(text);
  }
  const names = dependencyNames(packageJson);
  const matched = PACKAGE_TYPES.find((type) => type.detect.package_json && matchesPackageRule(type.detect.package_json, names));
  return (matched || PACKAGE_TYPES.find((type) => type.detect.fallback_only)).id;
}

// Convenience: for a parsed object, re-serialize to text and apply the rules above
export function classifyPackageJson(pkgOrRaw) {
  const raw = typeof pkgOrRaw === "string" ? pkgOrRaw : JSON.stringify(pkgOrRaw || {});
  return classifyPackageText(raw);
}

/**
 * Marker scan of one folder > type ids in registry order (["basic"] when nothing matches)
 * has(relpath)=>bool, read(relpath)=>raw text|null. A fallback_only type counts only when nothing else matched.
 */
export function detectTypesFromMarkers({ has, read }) {
  const types = [];
  let packageTypeId = null;
  for (const type of PROJECT_TYPES) {
    if (!type.detect.markers.some((marker) => has(marker))) continue;
    if (type.detect.package_json || type.detect.fallback_only) {
      // All package types share package.json: classify once, at the position of the first package type
      if (packageTypeId === null) packageTypeId = classifyPackageText(read ? read("package.json") : "");
      if (packageTypeId === type.id) types.push(type.id);
      continue;
    }
    types.push(type.id);
  }
  const fallbackIds = new Set(PROJECT_TYPES.filter((type) => type.detect.fallback_only).map((type) => type.id));
  const result = types.length > 1 ? types.filter((id) => !fallbackIds.has(id)) : types;
  return result.length ? [...new Set(result)] : ["basic"];
}

const VERSION_RE = /^\d+\.\d+\.\d+$/;

// Version detection (behavior spec §3.3) — first success in order. Injects read(relpath)=>string|null.
export function detectVersionFromFiles({ read, readJson, hasJq, gitTag }) {
  const pkg = readJson?.("package.json");
  if (hasJq && pkg?.version && VERSION_RE.test(pkg.version)) return pkg.version;
  const grab = (content, re) => {
    for (const line of (content || "").split("\n")) {
      const m = line.match(re);
      if (m && VERSION_RE.test(m[1])) return m[1];
    }
    return null;
  };
  let v;
  if ((v = grab(read("build.gradle"), /version\s*=\s*["']?(\d+\.\d+\.\d+)/))) return v;
  if ((v = grab(read("pubspec.yaml"), /^version:\s*(\d+\.\d+\.\d+)/))) return v;
  if ((v = grab(read("pyproject.toml"), /version\s*=\s*["']?(\d+\.\d+\.\d+)/))) return v;
  if (gitTag) { const t = String(gitTag).replace(/^v/, ""); if (VERSION_RE.test(t)) return t; }
  return "0.0.1";
}

// Main marker file of a type for path display and search (first path_search file; package.json when the type has none)
export function markerForType(type) {
  return typeById(type)?.path_search.files[0] ?? "package.json";
}

// Secondary marker files of a type (spring build.gradle.kts/pom.xml, python setup.py/requirements.txt)
export function extraMarkers(type) {
  return typeById(type)?.path_search.files.slice(1) ?? [];
}

// Extension frequency scan recommendation (step 2 when there are no markers, #458).
// Secondary recommendation used only when there are no markers at all (= basic fallback). files = pruned relative paths.
// Thresholds come from registry detect.extensions; a fallback_only type is suggested only when nothing else is.
export function suggestTypesByExtScan(files) {
  const countMatches = (patterns) => patterns.reduce(
    (total, pattern) => total + files.filter((file) => new RegExp(pattern).test(file)).length, 0);
  const meetsThreshold = (type) => type.detect.extensions && countMatches(type.detect.extensions.patterns) >= type.detect.extensions.min_count;
  const found = PROJECT_TYPES.filter((type) => !type.detect.fallback_only && meetsThreshold(type)).map((type) => type.id);
  if (found.length) return found;
  return PROJECT_TYPES.filter((type) => type.detect.fallback_only && meetsThreshold(type)).map((type) => type.id);
}
