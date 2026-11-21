// Project type registry (#1244): src/core/project-types.json is the only source of type facts.
// User repos and skills get generated copies (scripts/build_project_types.mjs); array order = detection and primary order.
import { readFileSync } from "node:fs";

// Allowed keys per level. Unknown keys are errors so a typo cannot silently do nothing
const ENTRY_KEYS = ["id", "label", "description", "detect", "path_search", "version", "axes", "is_app",
  "launch_kinds", "root_resolver", "deploy_trigger_workflows"];
const DETECT_KEYS = ["markers", "package_json", "fallback_only", "extensions", "secondary"];
const PACKAGE_JSON_KEYS = ["requires_any", "requires_any_prefix", "requires_all", "excludes_any", "excludes_any_prefix"];
const EXTENSIONS_KEYS = ["patterns", "min_count"];
const PATH_SEARCH_KEYS = ["files", "require_dir", "exclude_parts", "gradle_settings_root"];
const VERSION_KEYS = ["format", "build_number", "display", "comment", "example"];
const AXES_KEYS = ["deploy", "publish"];
// Type id shape: lowercase words joined by hyphens (also the workflow folder name)
const TYPE_ID_PATTERN = /^[a-z][a-z0-9]*(-[a-z0-9]+)*$/;

// Keys of `value` not in `allowedKeys` > one problem line each
function unknownKeyProblems(value, allowedKeys, where) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return [`${where}: must be an object`];
  return Object.keys(value).filter((key) => !allowedKeys.includes(key)).map((key) => `${where}: unknown field "${key}"`);
}

function isStringList(value) {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

/**
 * Registry entries > problem list (empty = valid): fields, required values, unique ids
 */
export function validateRegistry(entries) {
  if (!Array.isArray(entries) || entries.length === 0) return ["registry: must be a non-empty array"];
  const problems = [];
  const seenIds = new Set();
  for (const [index, entry] of entries.entries()) {
    const where = `type ${entry?.id ?? `#${index}`}`;
    problems.push(...unknownKeyProblems(entry, ENTRY_KEYS, where));
    if (!entry || typeof entry !== "object") continue;
    // Required scalar fields
    if (!TYPE_ID_PATTERN.test(entry.id ?? "")) problems.push(`${where}: id must be lowercase words joined by hyphens`);
    if (seenIds.has(entry.id)) problems.push(`${where}: duplicate id`);
    seenIds.add(entry.id);
    for (const key of ["label", "description"]) {
      if (typeof entry[key] !== "string" || !entry[key]) problems.push(`${where}: ${key} is required`);
    }
    if (typeof entry.is_app !== "boolean") problems.push(`${where}: is_app must be true or false`);
    // @wizard auto:<name> resolver for the type folder (APP_ROOT), or null
    if (entry.root_resolver !== null && !/^[a-z]+-root$/.test(entry.root_resolver ?? "")) {
      problems.push(`${where}: root_resolver must be null or a name like "flutter-root"`);
    }
    for (const key of ["launch_kinds", "deploy_trigger_workflows"]) {
      if (!isStringList(entry[key])) problems.push(`${where}: ${key} must be a list of strings`);
    }
    // Nested objects (detect, path_search, version, axes)
    problems.push(...unknownKeyProblems(entry.detect, DETECT_KEYS, `${where}.detect`));
    if (entry.detect && !isStringList(entry.detect.markers)) problems.push(`${where}.detect: markers must be a list of strings`);
    if (entry.detect?.package_json !== undefined) {
      problems.push(...unknownKeyProblems(entry.detect.package_json, PACKAGE_JSON_KEYS, `${where}.detect.package_json`));
    }
    if (entry.detect?.extensions !== undefined) {
      problems.push(...unknownKeyProblems(entry.detect.extensions, EXTENSIONS_KEYS, `${where}.detect.extensions`));
    }
    problems.push(...unknownKeyProblems(entry.path_search, PATH_SEARCH_KEYS, `${where}.path_search`));
    if (entry.path_search && !isStringList(entry.path_search.files)) problems.push(`${where}.path_search: files must be a list of strings`);
    problems.push(...unknownKeyProblems(entry.version, VERSION_KEYS, `${where}.version`));
    for (const key of ["display", "comment", "example"]) {
      if (entry.version && typeof entry.version[key] !== "string") problems.push(`${where}.version: ${key} is required`);
    }
    problems.push(...unknownKeyProblems(entry.axes, AXES_KEYS, `${where}.axes`));
    if (entry.axes && !(isStringList(entry.axes.deploy) && isStringList(entry.axes.publish))) {
      problems.push(`${where}.axes: deploy and publish must be lists of strings`);
    }
  }
  return problems;
}

/**
 * src/core/project-types.json > validated, frozen entries (throws with every problem)
 */
function loadRegistry() {
  const entries = JSON.parse(readFileSync(new URL("./project-types.json", import.meta.url), "utf8"));
  const problems = validateRegistry(entries);
  if (problems.length) throw new Error(`project type registry is invalid:\n- ${problems.join("\n- ")}`);
  return Object.freeze(entries.map((entry) => Object.freeze(entry)));
}

export const PROJECT_TYPES = loadRegistry();
export const VALID_TYPES = Object.freeze(PROJECT_TYPES.map((type) => type.id));

export function typeById(typeId) {
  return PROJECT_TYPES.find((type) => type.id === typeId);
}

/**
 * Push-to-deploy workflow file names owned by types (branch-sub.js adds the type-independent ones)
 */
export function deployTriggerWorkflows() {
  return PROJECT_TYPES.flatMap((type) => type.deploy_trigger_workflows);
}
