// CLI argument parsing.
import { existsSync, statSync, realpathSync } from "node:fs";
import { join, relative, isAbsolute } from "node:path";
import { VALID_TYPES } from "../context.js";
import { SUPPORTED_LANGS, t } from "../i18n/index.js";
import { REPO_LANGUAGES } from "../core/repo-language.js";

import { DEPLOY_TARGETS, PUBLISH_TARGETS, INTENT_VALUES, LABEL_STYLES } from "../core/constants.js";

// core/constants.js owns the value lists. Re-exported here so existing import paths keep working.
export { DEPLOY_TARGETS, PUBLISH_TARGETS, INTENT_VALUES };
export const LABEL_STYLE_VALUES = LABEL_STYLES;
// repo-language.js holds the single list of supported languages (#787). A separate copy here would drift.
export const LANGUAGE_VALUES = REPO_LANGUAGES;
const SEMVER_RE = /^\d+\.\d+\.\d+$/;
// Unicode letters and digits allowed (#719) — spaces and shell metacharacters are not in the class, so still rejected.
const BRANCH_RE = /^[\p{L}\p{N}][\p{L}\p{N}._/-]*$/u;
// Allowed run modes (#665) — keeps a typo from ending silently as "0 copies, success".
export const MODE_VALUES = ["full", "version", "workflows", "issues", "skills", "doctor", "options", "interactive"];

// argv (process.argv.slice(2)) → parse result. Throws on error (caller exits 1).
export function parseArgs(argv) {
  const result = {
    mode: "interactive",
    version: "",             // Initial version of the target project (--project-version)
    types: [],
    primaryType: "",
    deployTarget: null,      // Deploy axis (#439): docker-ssh|vercel|none, null = unset
    publishTargets: null,    // Publish axis (#439): target array, null = unset
    deployBranch: "",        // Release PR head branch (#456): --deploy-branch, empty = not given
    deployTriggerBranch: "", // Branch that triggers deploy workflows (#1114): --deploy-trigger-branch, empty = default branch
    language: null,          // Repo text language (#769): --language en|ko (differs from the screen language --lang)
    labelStyle: null,        // Status label style (#776): --label-style en|ko
    intent: null,            // Project nature (#485): --intent app|library|both|none|manual, null = unset (inferred)
    includeSecretBackup: null,
    aiPrSummary: null,   // #566 — whether to include the AI change summary workflow
    codeReviewCoderabbit: null, // --coderabbit: whether to install the CodeRabbit code review config (.coderabbit.yaml) (null = not given → saved value, else off)
    projectsSync: null,  // #716 — whether to include the Projects board sync workflow (null = not given)
    ciMinutesSaver: null, // #1114 — CI minutes saver substitution (null = not given → saved value, else off)
    json: false,         // --json: machine-readable output (--mode options)
    removeLegacy: false, // #809 — also move old-generation deploy workflows (confirm tier) aside as .bak
    createDevelopmentBranch: false, // #715 — create and push the development branch non-interactively (writes to the remote, so only when explicit)
    pathsCsv: "",            // Raw "flutter=app,react=client" (normalized in the resolve step)
    force: false,
    lang: null,              // --lang en|ko (null = decided by src/i18n resolveLang)
    help: false,
    showVersion: false,      // -v/--version → print the projectops package version (npm convention)
  };
  const args = [...argv];
  while (args.length > 0) {
    const a = args.shift();
    switch (a) {
      case "-m": case "--mode":
      {
        const v = (args.shift() ?? "").trim();
        if (!MODE_VALUES.includes(v)) {
          throw new CliError(t("args.mode", { values: MODE_VALUES.join(" | "), v }));
        }
        result.mode = v;
        break;
      }
      case "-v": case "--version":
        // npm convention: -v/--version prints the package version. (The initial version is set with --project-version)
        result.showVersion = true; break;
      case "--project-version":
      {
        // version.yml and shell scripts read this value as is, so only x.y.z is accepted (#676)
        // 'v1.0.0' is a common user notation, so it is accepted with the prefix stripped rather than rejected
        const v = (args.shift() ?? "").trim().replace(/^[vV](?=\d)/, "");
        if (!SEMVER_RE.test(v)) {
          throw new CliError(t("args.projectVersion", { v }));
        }
        result.version = v;
        break;
      }
      case "-t": case "--type": {
        const csv = args.shift() ?? "";
        const seen = new Set();
        const types = [];
        for (let ty of csv.split(",")) {
          ty = ty.replace(/\s/g, "");
          if (ty === "") continue;
          if (seen.has(ty)) continue;         // dedup
          if (!VALID_TYPES.includes(ty)) {
            throw new CliError(t("args.unsupportedType", { type: ty, valid: VALID_TYPES.join(" ") }));
          }
          seen.add(ty);
          types.push(ty);
        }
        if (types.length === 0) throw new CliError(t("args.typeEmpty"));
        result.types = types;
        result.primaryType = types[0];
        break;
      }
      case "--force": case "-y": case "--yes": result.force = true; break;
      case "--lang": {
        const v = (args.shift() ?? "").trim().toLowerCase();
        if (!SUPPORTED_LANGS.includes(v)) {
          throw new CliError(t("cli.langInvalid", { values: SUPPORTED_LANGS.join(" | "), value: v }));
        }
        result.lang = v;
        break;
      }
      case "--deploy": {
        const v = args.shift() ?? "";
        if (!DEPLOY_TARGETS.includes(v)) {
          throw new CliError(t("args.deploy", { values: DEPLOY_TARGETS.join(" | "), v }));
        }
        result.deployTarget = v;
        break;
      }
      case "--publish": {
        const csv = args.shift() ?? "";
        const targets = [];
        for (let pt of csv.split(",")) {
          pt = pt.replace(/\s/g, "");
          if (pt === "") continue;
          if (!PUBLISH_TARGETS.includes(pt)) {
            throw new CliError(t("args.publish", { values: PUBLISH_TARGETS.join(" | "), v: pt }));
          }
          if (!targets.includes(pt)) targets.push(pt);
        }
        result.publishTargets = targets;
        break;
      }
      case "--deploy-branch": {
        // Release PR head branch (#456). Separate from default_branch.
        const v = (args.shift() ?? "").trim();
        // Inserted as is into workflow yaml and shell, so only safe branch names are allowed (#676)
        if (v && (!BRANCH_RE.test(v) || v.includes("..") || v.endsWith("/") || v.endsWith(".lock"))) {
          throw new CliError(t("args.deployBranch", { v }));
        }
        if (v) result.deployBranch = v;
        break;
      }
      case "--deploy-trigger-branch": {
        // Branch whose push runs the deploy (#1114). Used only when split from the default branch. Goes into workflow yaml as is, so same check as --deploy-branch.
        const v = (args.shift() ?? "").trim();
        if (v && (!BRANCH_RE.test(v) || v.includes("..") || v.endsWith("/") || v.endsWith(".lock"))) {
          throw new CliError(t("args.deployBranch", { v }));
        }
        if (v) result.deployTriggerBranch = v;
        break;
      }
      case "--intent": {
        // Project nature (#485). If not given, inferred from --deploy/--publish.
        const v = (args.shift() ?? "").trim();
        if (!INTENT_VALUES.includes(v)) {
          throw new CliError(t("args.intent", { values: INTENT_VALUES.join(" | "), v }));
        }
        result.intent = v;
        break;
      }
      case "--language": {
        // Repo text language (#769). If not given, saved version.yml value → (new en / existing ko).
        // Differs from the screen language (--lang): this is the language of templates written into the user repo.
        const v = (args.shift() ?? "").trim();
        if (!LANGUAGE_VALUES.includes(v)) {
          throw new CliError(`--language must be one of ${LANGUAGE_VALUES.join(" | ")}: '${v}'`);
        }
        result.language = v;
        break;
      }
      case "--label-style": {
        // Status label style (#776). If not given, saved version.yml value → (new en / existing ko).
        const v = (args.shift() ?? "").trim();
        if (!LABEL_STYLE_VALUES.includes(v)) {
          throw new CliError(`--label-style must be one of ${LABEL_STYLE_VALUES.join(" | ")}: '${v}'`);
        }
        result.labelStyle = v;
        break;
      }
      // ── deprecated alias (kept for 1 minor — #439) ──
      case "--nexus":
        process.stderr.write(t("args.nexusDeprecated") + "\n");
        result.publishTargets = [...new Set([...(result.publishTargets ?? []), "nexus"])];
        if (result.deployTarget === null) result.deployTarget = "none";
        break;
      case "--no-nexus":
        result.publishTargets = (result.publishTargets ?? []).filter((t) => t !== "nexus");
        break;
      case "--secret-backup": result.includeSecretBackup = true; break;
      case "--no-secret-backup": result.includeSecretBackup = false; break;
      // #566 — must be switchable non-interactively too. Otherwise automation has no choice.
      case "--coderabbit": result.codeReviewCoderabbit = true; break;
      case "--no-coderabbit": result.codeReviewCoderabbit = false; break;
      case "--ai-summary": result.aiPrSummary = true; break;
      case "--no-ai-summary": result.aiPrSummary = false; break;
      case "--projects-sync": result.projectsSync = true; break;
      case "--no-projects-sync": result.projectsSync = false; break;
      case "--ci-minutes-saver": result.ciMinutesSaver = true; break;
      case "--no-ci-minutes-saver": result.ciMinutesSaver = false; break;
      case "--remove-legacy": result.removeLegacy = true; break;
      case "--create-development-branch": result.createDevelopmentBranch = true; break;
      case "--json": result.json = true; break;
      case "--npm-publish":
        process.stderr.write(t("args.npmPublishDeprecated") + "\n");
        result.publishTargets = [...new Set([...(result.publishTargets ?? []), "npm"])];
        break;
      case "--no-npm-publish":
        result.publishTargets = (result.publishTargets ?? []).filter((t) => t !== "npm");
        break;
      case "--paths": result.pathsCsv = args.shift() ?? ""; break;
      case "-h": case "--help": result.help = true; break;
      default:
        throw new CliError(t("args.unknownOption", { opt: a }));
    }
  }
  return result;
}

export class CliError extends Error {}

// Path normalization: trim spaces, \→/, strip trailing / and leading ./, empty→"."
export function normalizePath(p) {
  let s = String(p).trim();
  s = s.replace(/\\/g, "/");
  s = s.replace(/\/+$/, "");   // Trailing /
  s = s.replace(/^\.\//, "");  // Leading ./
  return s === "" ? "." : s;
}

// --paths map validation (#674) — a path outside the repo is the most dangerous, since version_manager actually edits that file.
//   · reject absolute paths and `..` segments (only paths relative to the repo root)
//   · reject type keys not chosen with --type
//   · reject folders that do not exist (realpath also blocks symlinks pointing outside)
export function validatePathsMap(map, { root, types }) {
  for (const [type, p] of map) {
    if (!types.includes(type)) {
      throw new CliError(t("args.paths.unselected", { type, types: types.join(",") || t("args.paths.none") }));
    }
    if (p.startsWith("/") || /^[A-Za-z]:/.test(p) || p.split("/").includes("..")) {
      throw new CliError(t("args.paths.relative", { type, path: p }));
    }
    const abs = join(root, p);
    if (!existsSync(abs) || !statSync(abs).isDirectory()) {
      throw new CliError(t("args.paths.missing", { type, path: p }));
    }
    const rel = relative(realpathSync(root), realpathSync(abs));
    if (rel.startsWith("..") || isAbsolute(rel)) {
      throw new CliError(t("args.paths.outside", { type, path: p }));
    }
  }
}

// "flutter=app,react=client" → Map<type, normalizedPath>. Validates types (invalid → throw).
export function parsePathsCsv(csv) {
  const map = new Map();
  if (!csv) return map;
  for (const pair of csv.split(",")) {
    if (pair.trim() === "") continue;
    const eq = pair.indexOf("=");
    const type = (eq >= 0 ? pair.slice(0, eq) : pair).trim();
    const rawPath = eq >= 0 ? pair.slice(eq + 1) : "";
    if (!VALID_TYPES.includes(type)) {
      throw new CliError(t("args.paths.badType", { type }));
    }
    map.set(type, normalizePath(rawPath));
  }
  return map;
}
