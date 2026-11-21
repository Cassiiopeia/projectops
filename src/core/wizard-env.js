// @wizard env token engine: value substitution, leftover token substitution, unchanged check.
// ⚠️ No YAML parse/re-serialize — line-based string handling (keeping format and comments is a premise of the unchanged check).
import { substituteBranches } from "./branch-sub.js";

// KEY regex: [A-Z_]+ (uppercase and underscore only). Only lines with an ask/auto marker.
const MARKER_RE = /#\s*@wizard\s+(ask|auto):(.*)$/;
const KEY_RE = /^(\s*)([A-Z_]+):/;
const PATHS_ANCHOR_RE = /#\s*@wizard\s+paths-anchor/;

// Parse one line and return {indent,key,action,arg}. null without an ask/auto marker.
export function parseWizardLine(line) {
  const marker = line.match(MARKER_RE);
  if (!marker) return null;
  const km = line.match(KEY_RE);
  if (!km) return null; // Ignore anything not in KEY: form (e.g. the paths-anchor comment)
  return { indent: km[1], key: km[2], action: marker[1], arg: marker[2].trim() };
}

// Replace the quoted value in `KEY: "..."` + drop the trailing `# @wizard ...` comment on that line.
// Works on a single line. Skips substitution when value is an empty string.
export function setEnvLine(line, key, value) {
  if (value === "" || value == null) return line;
  // CRLF safe: split off the trailing \r, process, then restore (for autocrlf projects)
  const cr = line.endsWith("\r") ? "\r" : "";
  const body = cr ? line.slice(0, -1) : line;
  // Value substitution: KEY: "old" → KEY: "value"
  let out = body.replace(
    new RegExp(`^(\\s*${key}:\\s*")[^"]*(")`),
    (_m, p1, p2) => `${p1}${value}${p2}`,
  );
  // Drop the trailing # @wizard ... comment on that line (including the leading space)
  out = out.replace(/(\S)[^\S\r\n]*#[^\S\r\n]*@wizard[^\S\r\n].*$/, "$1");
  return out + cr;
}

// Extract real env values from the installed copy (#502 — update mode carryover).
// Substitution drops the @wizard comment but keeps the `KEY: "value"` line (setEnvLine) — collect that value.
// No template knowledge needed: substituteEnv looks up values only for ask keys, so unrelated keys are harmless.
// Empty values ("") are excluded — substituteEnv also ignores an empty choice and uses the default (same rule).
export function extractEnvValues(installedContent) {
  const values = new Map();
  for (const raw of String(installedContent || "").split(/\r?\n/)) {
    const m = raw.match(/^\s*([A-Z_]+):\s*"([^"]*)"/);
    if (m && m[2] !== "") values.set(m[1], m[2]);
  }
  return values;
}

// Sample defaults (#810) — deployed as is, requests would go to someone else's domain.
// On paths where the user picked no value (--force, defaults), leave __KEY__ unfilled.
// Post-install verification (verify.js) then flags it as unreplaced and the finish screen shows it as "fill in yourself".
export function isPlaceholderDefault(value) {
  return /(^|\.)example\.(com|org|net)$/i.test(String(value || "").trim());
}

// resolver — value computation is delegated to injected resolvers (keeps it pure).
// resolvers: { repo, "spring-app-yml-dir"(type), "spring-app-yml-path"(type), "flutter-root", "expo-root" }
export function resolveToken(name, type, resolvers = {}) {
  const fn = resolvers[name];
  return typeof fn === "function" ? (fn(type) ?? "") : "";
}

// Leftover global token substitution — the file body, collected values (#489) and card display all use this rule.
// The single point that keeps values written to files and the version.yml deploy block memory in sync.
export function resolveGlobalTokens(s, repoName = "") {
  if (typeof s !== "string" || (!s.includes("__PROJECT_NAME__") && !s.includes("__APP_ARTIFACT_NAME__"))) return s;
  return s.replaceAll("__PROJECT_NAME__", repoName).replaceAll("__APP_ARTIFACT_NAME__", repoName);
}

// Whole-file substitution.
// content: original workflow text. Returns: substituted text.
// opts:
//   type          - project type (for resolvers and value lookup)
//   values        - Map<key,value>: user choices for ask keys (default = arg or resolver when missing)
//   useDefaults   - when true, ask keys also use defaults (WF_USE_DEFAULTS=true, the premise of the unchanged comparison)
//   resolvers     - for resolveToken
//   repoName      - value for __PROJECT_NAME__/__APP_ARTIFACT_NAME__
//   projectPath   - for paths-anchor substitution ('.' leaves the anchor unchanged)
//   collectSubs   - if an array, push {key, action, before, after} per substitution (for the #494 trace)
export function substituteEnv(content, opts = {}) {
  const { type = "", values = new Map(), useDefaults = true, resolvers = {}, repoName = "", projectPath = ".", collectAsks = null, collectSubs = null } = opts;
  if (!content.includes("@wizard")) return content;

  // CRLF safe: split off EOLs, parse and substitute on LF, then restore the original EOL style.
  // (A JS regex `.` does not match \r, so `(.*)$` marker parsing fails on CRLF.)
  const usesCRLF = content.includes("\r\n");
  const lines = content.split(/\r?\n/);
  for (let i = 0; i < lines.length; i++) {
    const p = parseWizardLine(lines[i]); // Line already stripped of \r
    if (!p) continue;
    let val = "";
    if (p.action === "auto") {
      val = resolveToken(p.arg, type, resolvers);
    } else { // ask
      let def = p.arg.startsWith("@") ? resolveToken(p.arg.slice(1), type, resolvers) : p.arg;
      const chosen = values.get(p.key);
      if (chosen != null && chosen !== "" && !useDefaults) val = chosen;
      else if (isPlaceholderDefault(def)) continue; // Sample values are not written — token and marker stay (#810)
      else val = def;
      // Collect ask keys only (auto is not saved). For the deploy block.
      // #489 — the file body goes through the global token substitution below, so collected values get the same substitution
      //        to keep the version.yml deploy block byte-identical to the installed copy.
      if (collectAsks) collectAsks.set(p.key, resolveGlobalTokens(val, repoName));
    }
    // #494 trace — record before/after values (after resolves global tokens too, matching the final file)
    if (Array.isArray(collectSubs) && val !== "" && val != null) {
      const before = (lines[i].match(/:\s*"([^"]*)"/) || [])[1] ?? "";
      collectSubs.push({ key: p.key, action: p.action, before, after: resolveGlobalTokens(val, repoName) });
    }
    lines[i] = setEnvLine(lines[i], p.key, val);
  }
  let out = lines.join(usesCRLF ? "\r\n" : "\n");

  // Leftover global tokens
  out = resolveGlobalTokens(out, repoName);

  // paths-anchor: when the path is not '.', replace the whole comment line with a paths line
  if (PATHS_ANCHOR_RE.test(out) && projectPath && projectPath !== ".") {
    const eol = out.includes("\r\n") ? "\r\n" : "\n";
    out = out.split(/\r?\n/).map((line) => {
      if (PATHS_ANCHOR_RE.test(line)) {
        const indent = (line.match(/^(\s*)/) || ["", ""])[1];
        return `${indent}paths: ['${projectPath}/**']`;
      }
      return line;
    }).join(eol);
  }
  return out;
}

// Unchanged check: byte-compare the installed copy with the original "virtually substituted with defaults".
export function isUnchanged(templateContent, installedContent, opts = {}) {
  // Branch substitution (#477) is part of the virtual comparison — otherwise substituted installs are misjudged as "changed" and
  // recopied on every update (.bak churn). No-op when opts.branches is unset or standard.
  const virtual = substituteBranches(
    substituteEnv(templateContent, { ...opts, useDefaults: true }),
    opts.branches ?? null, opts.filename ?? "",
  );
  return virtual === installedContent;
}
