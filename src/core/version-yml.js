// version.yml parse and generate (full regeneration strategy D4).
// ⚠️ No YAML re-serialization — comments are data. Pinned byte for byte with template strings.
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { DEPLOY_TARGETS, LABEL_STYLES } from "./constants.js";
import { REPO_LANGUAGES } from "./repo-language.js";
import { PROJECT_TYPES } from "./project-types.js";

// Match patterns built from the value lists — adding a language or style to a list makes the parser read it automatically.
// (Hardcoding languages in the pattern means a newly saved language is unreadable on the next update and reverts to ko.)
const alt = (values) => values.map((v) => v.replace(/[.*+?^${}()|[\]\\-]/g, "\\$&")).join("|");
const LANGUAGE_RE = new RegExp(`^\\s+language:\\s*["']?(${alt(REPO_LANGUAGES)})["']?`);
const DEPLOY_TRIGGER_BRANCH_RE = /^\s+deploy_trigger_branch:\s*["']?([A-Za-z0-9._\/-]+)["']?/;
const CI_MINUTES_SAVER_RE = /^\s+ci_minutes_saver:\s*["']?(true|false)["']?/;
const LABEL_STYLE_RE = new RegExp(`^\\s+label_style:\\s*["']?(${alt(LABEL_STYLES)})["']?`);

// "Files synced per project type" lines, one per registry type (language-neutral, both headers)
const TYPE_SYNC_LINES = PROJECT_TYPES.map((type) => `# - ${type.id}: ${type.version.comment}`).join("\n");

const HEADER_EN = `# ===================================================================
# Project version management file
# ===================================================================
#
# This file keeps version information in one place for every project type.
# GitHub Actions workflows read this file and manage the version automatically.
#
# Usage:
# 1. version: "1.0.0" - the version shown to users
# 2. version_code: 1 - Play Store/App Store build number (auto-incremented from 1)
# 3. project_types: array of project types, the first entry is the primary one
# 4. project_paths: project folder per type (relative to the repo root, for monorepos)
#
# Automatic version updates:
# - version_code: incremented by 1 on every build (independent of the rules below)
# - How far the version is bumped is decided by metadata.template.options.semver_auto
#   semver_auto: true  -> decided by the commit titles in the release range (also when the key is missing)
#                         "title : feat! : body" or "feat!:" -> major (x+1.0.0)
#                         "title : feat : body"  or "feat:"  -> minor (x.y+1.0)
#                         anything else (fix/docs/chore/refactor/test) -> patch (x.y.z+1)
#   semver_auto: false -> always patch +1
# - You may edit the version value by hand regardless of the rules above
#
# Files synced per project type:
${TYPE_SYNC_LINES}
#
# Related workflows:
# - .github/workflows/PROJECT-VERSION-CONTROL.yaml
# - .github/workflows/PROJECT-README-VERSION-UPDATE.yaml
# - .github/workflows/PROJECT-RELEASE-CHANGELOG.yaml
#
# Notes:
# - Do not change project_types after the initial setup
# - The version is always synced automatically to the highest one
# ===================================================================
`;

// Korean repos (options.language: ko) get Korean comments too (#811).
// Every update (--force fixes the screen to en) turned the Korean comments English, making the version.yml diff 86 lines.
const HEADER_KO = `# ===================================================================
# 프로젝트 버전 관리 파일
# ===================================================================
#
# 이 파일은 다양한 프로젝트 타입에서 버전 정보를 중앙 관리하기 위한 파일입니다.
# GitHub Actions 워크플로우가 이 파일을 읽어 자동으로 버전을 관리합니다.
#
# 사용법:
# 1. version: "1.0.0" - 사용자에게 표시되는 버전
# 2. version_code: 1 - Play Store/App Store 빌드 번호 (1부터 자동 증가)
# 3. project_types: 프로젝트 타입 배열 — 첫 항목이 primary
# 4. project_paths: 타입별 프로젝트 폴더 (레포 루트 기준 상대경로, 모노레포용)
#
# 자동 버전 업데이트:
# - version_code: 매 빌드마다 자동으로 1씩 증가 (아래 판정과 무관)
# - 버전 승격 폭은 metadata.template.options.semver_auto 가 정합니다
#   semver_auto: true  -> 릴리스 구간 커밋 제목으로 판정 (키가 없어도 같다)
#                         "제목 : feat! : 내용" 또는 "feat!:" -> major (x+1.0.0)
#                         "제목 : feat : 내용"  또는 "feat:"  -> minor (x.y+1.0)
#                         그 외(fix/docs/chore/refactor/test) -> patch (x.y.z+1)
#   semver_auto: false -> 항상 patch +1
# - 위 판정과 무관하게 version 값을 직접 수정해도 됩니다
#
# 프로젝트 타입별 동기화 파일:
${TYPE_SYNC_LINES}
#
# 연관된 워크플로우:
# - .github/workflows/PROJECT-VERSION-CONTROL.yaml
# - .github/workflows/PROJECT-README-VERSION-UPDATE.yaml
# - .github/workflows/PROJECT-RELEASE-CHANGELOG.yaml
#
# 주의사항:
# - project_types는 최초 설정 후 변경하지 마세요
# - 버전은 항상 높은 버전으로 자동 동기화됩니다
# ===================================================================
`;

// One-line comment next to each key. Language follows the repo text language (options.language), not the screen language.
const COMMENTS = {
  en: {
    versionCode: "app build number",
    projectTypes: "array of types, first entry is primary, safe to edit by hand",
    projectPaths: "project folder per type (relative to the repo root)",
    mode: "install scope (full/version/workflows), used when re-running update mode",
    intent: "project kind (app/library/both/none/manual), drives the deploy questions",
    semverAuto: "decide the version bump from commit titles (false means always patch)",
    projectsSync: "include the GitHub Projects status sync workflow",
    closeOnRelease: "close issues labelled done when a release is merged (false or missing means do not close)",
    language: "issue/PR template language (en | ko)",
    labelStyle: "status label style (en: status: todo / ko: Korean names)",
    deployTriggerBranch: "branch whose push runs the deploy workflows (missing = the default branch)",
    ciMinutesSaver: "install CI workflows in their Actions-minutes-saving form (missing = off)",
    appRelease: "whether releases go through App Store / Play Store review",
    deploy: "deploy settings remembered by the wizard (non-sensitive, safe to edit by hand)",
    excluded: "workflow files the update must never install (safe to edit by hand)",
    storeLocales: "store release-note languages, first is the default (missing = one text for every store language)",
    storeLocalesStore: "same, only for this store when its languages differ from store_locales (optional)",
    legacyDeployBranch: "old name of development_branch, kept equal for older skills",
  },
  ko: {
    versionCode: "app build number",
    projectTypes: "멀티타입 배열 — 첫 항목이 primary, 직접 편집 가능",
    projectPaths: "타입별 프로젝트 폴더 (레포 루트 기준 상대경로)",
    mode: "통합 범위(full/version/workflows) — 업데이트 모드 재실행 기준",
    intent: "프로젝트 성격(app/library/both/none/manual) — 배포 질문 유도 기준",
    semverAuto: "커밋 제목으로 버전 승격 폭 결정 (false면 항상 patch)",
    projectsSync: "GitHub Projects 상태 동기화 워크플로우 포함 여부",
    closeOnRelease: "릴리스 머지 때 완료 라벨 이슈를 닫는다 (false/미기재면 닫지 않음)",
    language: "이슈/PR 템플릿 언어 (en | ko)",
    labelStyle: "상태 라벨 표기 (en: status: todo / ko: 작업전)",
    deployTriggerBranch: "branch whose push runs the deploy workflows (missing = the default branch)",
    ciMinutesSaver: "install CI workflows in their Actions-minutes-saving form (missing = off)",
    appRelease: "앱스토어·플레이스토어 심사로 이어지는 배포인가",
    deploy: "마법사가 기억하는 배포 설정 (비민감 / 직접 수정 가능)",
    excluded: "업데이트가 절대 설치하지 않을 워크플로우 파일 (직접 수정 가능)",
    storeLocales: "스토어 릴리스 노트 언어 목록, 첫 항목이 기본 언어 (미기재면 모든 스토어 언어에 같은 문구)",
    storeLocalesStore: "이 스토어만 언어 구성이 store_locales 와 다를 때 쓰는 선택 키",
    legacyDeployBranch: "development_branch 의 구 이름 — 구버전 스킬용으로 같은 값 유지",
  },
};
// Comment table for a repo language: ko > Korean, anything else > English
export const commentsFor = (lang) => COMMENTS[lang === "ko" ? "ko" : "en"];

// Decide last_updated_by (#811): the git user who ran it → existing value → template_integrator.
// Overwriting with "template_integrator" every time loses who made the change.
export function resolveUpdatedBy(existingContent = "", cwd = ".") {
  try {
    const name = execFileSync("git", ["config", "user.name"],
      { cwd, encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }).trim();
    if (name) return name;
  } catch { /* No git or no config (CI) — use the existing value */ }
  const m = String(existingContent || "").match(/^\s+last_updated_by:\s*"([^"]*)"/m);
  return m && m[1] ? m[1] : "template_integrator";
}

// State-machine parse of metadata.template.options.
// Returns (#439 deploy/publish axes): { deploy: string|null, publish: string[]|null, secretBackup: bool|null }
//   deploy: 'docker-ssh'|'vercel'|'none', publish: subset of ['nexus','npm','github-packages']. null = not set.
// Old keys (nexus/npm_publish/synology) are migrated to the new axes on read (compat with files before v4.2.0):
//   nexus:true → 'nexus' in publish + 'none' if deploy is unset (old behavior: nexus excluded server deploy)
//   npm_publish:true → 'npm' in publish
//   synology:true → secret_backup true if unset (#473 — the old Synology option included the secret upload, so
//                   without carrying it over, a non-interactive update silently loses the secret backup workflow)
// (options-ask.js imports this function — defined here (version-yml) to avoid a circular import.)
export function parseTemplateOptions(content) {
  const out = { deploy: null, publish: null, secretBackup: null,
                changelogProvider: null, changelogBaseUrl: null, codeReviewCoderabbit: null, aiPrSummary: null, projectsSync: null,
                deployBranch: null, deployTriggerBranch: null, ciMinutesSaver: null, intent: null, semverAuto: null, appRelease: null, labelStyle: null, closeOnRelease: null, language: null, excludedWorkflows: null, storeLocales: null, storeLocalesIos: null, storeLocalesPlay: null };
  // The development branch sits directly under metadata (#456) — outside template.options, so scanned separately.
  out.deployBranch = readDevelopmentBranch(content);
  let legacyNexus = null;
  let legacyNpm = null;
  let legacySynology = null;
  // Normalize a value: strip quotes + trim
  const strip = (s) => String(s).replace(/["']/g, "").trim();
  let inTemplate = false;
  let inOptions = false;
  let inCodeReview = false;
  let inChangelog = false;
  for (const line of String(content || "").split("\n")) {
    if (/^\s*template:/.test(line)) { inTemplate = true; continue; }
    if (inTemplate && /^\s+options:/.test(line)) { inOptions = true; continue; }
    if (inTemplate && inOptions) {
      // Detect nested block headers (one level under options) — code_review / changelog (#455)
      if (/^\s+code_review:\s*$/.test(line)) { inCodeReview = true; inChangelog = false; continue; }
      if (/^\s+changelog:\s*$/.test(line)) { inChangelog = true; inCodeReview = false; continue; }
      if (inCodeReview) {
        const cm = line.match(/^\s+coderabbit:\s*(.+)/);
        if (cm) { const v = strip(cm[1]); if (v === "true") out.codeReviewCoderabbit = true; if (v === "false") out.codeReviewCoderabbit = false; continue; }
        // #566 — whether the AI change summary workflow is included. A missing key stays null (unset)
        // so the wizard can ask once when an existing repo updates.
        const am = line.match(/^\s+ai_summary:\s*(.+)/);
        if (am) { const v = strip(am[1]); if (v === "true") out.aiPrSummary = true; if (v === "false") out.aiPrSummary = false; continue; }
      }
      if (inChangelog) {
        const pm = line.match(/^\s+provider:\s*(.+)/);
        if (pm) { out.changelogProvider = strip(pm[1]); continue; }
        const bm = line.match(/^\s+base_url:\s*(.*)/);
        if (bm) { out.changelogBaseUrl = strip(bm[1]); continue; }
      }
      // intent (project nature, #485) — matched before the deploy line (tells deploy: from intent:).
      // An inline comment (# ...) follows the value, so take only the quoted value or the first token.
      let im = line.match(/^\s+intent:\s*["']?([a-z]+)["']?/);
      if (im) {
        const v = im[1];
        if (["app", "library", "both", "none", "manual"].includes(v)) out.intent = v;
        continue;
      }
      let m = line.match(/^\s+deploy:\s*(.+)/);
      if (m) {
        const v = strip(m[1]);
        if (DEPLOY_TARGETS.includes(v)) out.deploy = v;
        continue;
      }
      m = line.match(/^\s+publish:\s*\[([^\]]*)\]/);
      if (m) {
        out.publish = strip(m[1]).split(",").map((t) => t.trim()).filter(Boolean);
        continue;
      }
      m = line.match(/^\s+nexus:\s*(.+)/);
      if (m) {
        const v = strip(m[1]);
        if (v === "true") legacyNexus = true;
        if (v === "false") legacyNexus = false;
        continue;
      }
      m = line.match(/^\s+secret_backup:\s*(.+)/);
      if (m) {
        const v = strip(m[1]);
        if (v === "true") out.secretBackup = true;
        if (v === "false") out.secretBackup = false;
        continue;
      }
      // Automatic semver bump (#546). null (unset) is read as ON (true) by the caller (#814). Only an explicit false turns it off.
      // Capture is limited to true|false (same as intent) — if the trailing inline comment came along with the value,
      // strip() only removes quotes and spaces, leaving "true # ..." and the match fails silently.
      m = line.match(/^\s+semver_auto:\s*["']?(true|false)["']?/);
      if (m) {
        out.semverAuto = m[1] === "true";
        continue;
      }
      // Repo text language (#769) — en | ko. Unset signals an "existing integrated repo", which the caller reads as ko.
      m = line.match(LANGUAGE_RE);
      if (m) {
        out.language = m[1];
        continue;
      }
      // Status label style (#776) — en (English standard) | ko (legacy Korean). Unset signals an "existing integrated repo", which the caller reads as ko.
      m = line.match(LABEL_STYLE_RE);
      if (m) {
        out.labelStyle = m[1];
        continue;
      }
      // Deploy trigger branch (#1114) — same as the default branch when unset.
      m = line.match(DEPLOY_TRIGGER_BRANCH_RE);
      if (m) {
        out.deployTriggerBranch = m[1];
        continue;
      }
      // CI minutes saver (#1114) — off when unset.
      m = line.match(CI_MINUTES_SAVER_RE);
      if (m) {
        out.ciMinutesSaver = m[1] === "true";
        continue;
      }
      // Projects board sync (#716). null (unset) is read by the caller as "keep if already installed, else exclude".
      m = line.match(/^\s+projects_sync:\s*["']?(true|false)["']?/);
      if (m) {
        out.projectsSync = m[1] === "true";
        continue;
      }
      // Close done issues on release (#771). null (unset) signals an "existing integrated repo" — the workflow does nothing.
      m = line.match(/^\s+close_on_release:\s*["']?(true|false)["']?/);
      if (m) {
        out.closeOnRelease = m[1] === "true";
        continue;
      }
      // Workflows not to install (#810) — inline array. The explicit way to keep updates from restoring deleted files.
      m = line.match(/^\s+excluded_workflows:\s*\[([^\]]*)\]/);
      if (m) {
        out.excludedWorkflows = m[1].split(",").map((s) => s.trim().replace(/^["']|["']$/g, "")).filter(Boolean);
        continue;
      }
      // Store release note languages (#829) — inline array, first entry is the default. Unset keeps current behavior (one text for every language).
      m = line.match(/^\s+store_locales:\s*\[([^\]]*)\]/);
      if (m) {
        out.storeLocales = m[1].split(",").map((s) => s.trim().replace(/^["']|["']$/g, "")).filter(Boolean);
        continue;
      }
      // Optional key used only when stores support different languages — if present, that store uses it instead of the shared store_locales.
      m = line.match(/^\s+store_locales_(ios|play):\s*\[([^\]]*)\]/);
      if (m) {
        out[m[1] === "ios" ? "storeLocalesIos" : "storeLocalesPlay"] = m[2].split(",").map((s) => s.trim().replace(/^["']|["']$/g, "")).filter(Boolean);
        continue;
      }
      // Project nature (#553) — whether the repo goes through app review. Workflows and skills read the same value.
      m = line.match(/^\s+app_release:\s*["']?(true|false)["']?/);
      if (m) {
        out.appRelease = m[1] === "true";
        continue;
      }
      m = line.match(/^\s+npm_publish:\s*(.+)/);
      if (m) {
        const v = strip(m[1]);
        if (v === "true") legacyNpm = true;
        if (v === "false") legacyNpm = false;
        continue;
      }
      m = line.match(/^\s+synology:\s*(.+)/);
      if (m) {
        const v = strip(m[1]);
        if (v === "true") legacySynology = true;
        if (v === "false") legacySynology = false;
        continue;
      }
      // Another key indented 0-4 spaces → end of the options section
      if (/^\s{0,4}[a-z_]+:/.test(line)) { inOptions = false; inTemplate = false; }
    }
    // Top-level key → end of the template section
    if (inTemplate && /^[a-z_]+:/.test(line)) { inTemplate = false; inOptions = false; }
  }
  // ── Old key migration — only when the new publish key is absent ──
  if (out.publish === null && (legacyNexus !== null || legacyNpm !== null)) {
    out.publish = [];
    if (legacyNexus === true) {
      out.publish.push("nexus");
      if (out.deploy === null) out.deploy = "none";
    }
    if (legacyNpm === true) out.publish.push("npm");
  }
  // Old synology key → carry over to secret_backup (#473) — if the new key is explicit, it wins
  if (out.secretBackup === null && legacySynology === true) out.secretBackup = true;
  return out;
}

// Infer intent (project nature) back from saved deploy/publish values (#485 — compat with old version.yml without an intent key).
//   deploy≠none & publish=[]  → app     (server/app only)
//   deploy=none & publish≠[]  → library (library only)
//   deploy≠none & publish≠[]  → both
//   deploy=none & publish=[]  → none
// If deploy/publish are still null (unset), intent cannot be inferred either → return null (so the intro question is asked).
export function inferIntent(deploy, publish) {
  if (deploy == null && (publish == null)) return null;
  const hasServer = deploy != null && deploy !== "none";
  const hasLib = Array.isArray(publish) && publish.length > 0;
  if (hasServer && hasLib) return "both";
  if (hasServer) return "app";
  if (hasLib) return "library";
  return "none";
}

// Minimal conversion of the pre-v4.1.0 singular project_type key → project_types array (#471).
// On paths that do not regenerate version.yml (workflows mode), keeps it consistent with the new version_manager (which rejects
// an explicit singular key) — replaces only that line and leaves the rest untouched.
// If the array key already exists, only the leftover singular key is removed (4.1.0: singular ignored when both exist — cleanup).
// Returns the full converted content string, or null when there is nothing to convert.
export function convertLegacySingularType(content) {
  const lines = String(content || "").split(/\r?\n/);
  let hasArray = false, idx = -1, value = "";
  lines.forEach((l, i) => {
    if (/^project_types:/.test(l)) hasArray = true;
    const m = l.match(/^project_type:\s*["']?([a-z-]+)["']?/);
    if (m && idx < 0) { idx = i; value = m[1]; }
  });
  if (idx < 0) return null;
  if (hasArray) {
    lines.splice(idx, 1);
    return lines.join("\n");
  }
  const type = value === "next" ? "react" : value; // The next type was merged into react in 4.1.0
  lines[idx] = `project_types: ["${type}"]   # array of types, first entry is primary, safe to edit by hand`;
  return lines.join("\n");
}

// Development (release source) branch = release PR head (#915)
// 2 keys: development_branch (source of truth) > deploy_branch (old name — written too, as old skills read only that)
// Returns the branch name, or null if neither exists
export const DEVELOPMENT_BRANCH_KEYS = ["development_branch", "deploy_branch"];
export function readDevelopmentBranch(content) {
  const lines = String(content || "").split("\n").filter((l) => !l.startsWith("#"));
  for (const key of DEVELOPMENT_BRANCH_KEYS) {
    const re = new RegExp(`^\\s+${key}:\\s*"([^"]*)"`);
    for (const l of lines) {
      const m = l.match(re);
      if (m) return m[1];
    }
  }
  return null;
}

/**
 * Branch keys in an existing version.yml: development_branch + deploy_branch, deploy_trigger_branch (#1248)
 * For modes that do not regenerate version.yml (workflows), so flags and the wizard give the same file as full mode
 * deployBranch     : "" = leave as is
 * deployTriggerBranch : "" = remove the key (deploys follow the default branch), otherwise set
 * Returns the new content (unchanged when nothing applies)
 */
export function upsertBranchKeys(content, { deployBranch = "", deployTriggerBranch = "", language = null } = {}) {
  const C = commentsFor(language === "ko" ? "ko" : "en");
  const eol = String(content).includes("\r\n") ? "\r\n" : "\n";
  const lines = String(content).split(/\r?\n/);
  const findLine = (re) => lines.findIndex((l) => !l.startsWith("#") && re.test(l));

  // metadata.development_branch / deploy_branch (both keys, same value — #915)
  if (deployBranch) {
    const developmentLine = `  development_branch: "${deployBranch}"`;
    const legacyLine = `  deploy_branch: "${deployBranch}"   # ${C.legacyDeployBranch}`;
    const developmentIndex = findLine(/^ {2}development_branch:/);
    const legacyIndex = findLine(/^ {2}deploy_branch:/);
    if (developmentIndex >= 0) lines[developmentIndex] = developmentLine;
    if (legacyIndex >= 0) lines[legacyIndex] = legacyLine;
    if (developmentIndex < 0 || legacyIndex < 0) {
      // Missing keys go right after default_branch (else right after metadata:), same order as buildVersionYml
      const anchorIndex = findLine(/^ {2}default_branch:/) >= 0 ? findLine(/^ {2}default_branch:/) : findLine(/^metadata:/);
      const missing = [];
      if (developmentIndex < 0) missing.push(developmentLine);
      if (legacyIndex < 0) missing.push(legacyLine);
      if (anchorIndex >= 0) lines.splice(anchorIndex + 1, 0, ...missing);
    }
  }

  // metadata.template.options.deploy_trigger_branch
  const triggerIndex = findLine(/^ {6}deploy_trigger_branch:/);
  if (deployTriggerBranch) {
    const triggerLine = `      deploy_trigger_branch: "${deployTriggerBranch}"   # ${C.deployTriggerBranch}`;
    if (triggerIndex >= 0) lines[triggerIndex] = triggerLine;
    else {
      const optionsIndex = findLine(/^ {4}options:\s*$/);
      if (optionsIndex >= 0) lines.splice(optionsIndex + 1, 0, triggerLine);
    }
  } else if (triggerIndex >= 0) {
    lines.splice(triggerIndex, 1);
  }
  return lines.join(eol);
}

// Extract values from the existing version.yml (line regexes, avoiding false hits on comment lines).
export function parseExisting(content) {
  const text = String(content || "");
  const line = (re) => {
    for (const l of text.split("\n")) {
      if (l.startsWith("#")) continue; // Skip comments
      const m = l.match(re);
      if (m) return m[1];
    }
    return null;
  };
  // version: "x.y.z" (only number.number.number)
  const version = line(/^version:\s*["']?([0-9][0-9.]*)["']?/) || "";
  // version_code: N (positive integer, else 1)
  let versionCode = parseInt(line(/^version_code:\s*([0-9]+)/) || "", 10);
  if (!Number.isInteger(versionCode) || versionCode <= 0) versionCode = 1;
  // project_types: ["a","b"]
  const typesRaw = line(/^project_types:\s*(\[[^\]]*\])/);
  let types = [];
  if (typesRaw) types = [...typesRaw.matchAll(/"([^"]+)"/g)].map((m) => m[1]);
  // project_paths block: "  type: "path""
  const paths = new Map();
  let inPaths = false;
  for (const l of text.split("\n")) {
    if (/^project_paths:/.test(l)) { inPaths = true; continue; }
    if (inPaths) {
      const m = l.match(/^\s+([a-z-]+):\s*"([^"]*)"/);
      if (m) paths.set(m[1], m[2]);
      else if (/^\S/.test(l)) inPaths = false; // Indentation ends → end of block
    }
  }
  // version + mode in the template: block (#502 — the integration scope that update mode re-runs)
  let templateVersion = "";
  let templateMode = null;
  let inTemplate = false;
  for (const l of text.split("\n")) {
    if (/^\s*template:/.test(l)) { inTemplate = true; continue; }
    if (inTemplate) {
      const vm = l.match(/^\s*version:\s*"([0-9][0-9.]*)"/);
      if (vm && !templateVersion) templateVersion = vm[1];
      const mm = l.match(/^\s*mode:\s*"([a-z]+)"/);
      if (mm && ["full", "version", "workflows"].includes(mm[1])) templateMode = mm[1];
      if (/^\S/.test(l)) break;
    }
  }
  // Branch info (#456) — default_branch (repo default) and the development branch (release PR head) are separate.
  const defaultBranch = line(/^\s*default_branch:\s*"([^"]*)"/);
  const deployBranch = readDevelopmentBranch(text);
  // Optional workflow options (metadata.template.options — nexus/secret_backup)
  const options = parseTemplateOptions(text);
  return { version, versionCode, types, paths, templateVersion, templateMode, options, defaultBranch, deployBranch };
}

// ── Keep keys the generator does not know (#835) ─────────────────────────────────────────────
// version.yml is rewritten from scratch on every full/version run. Writing only known keys drops what the user added —
// notably the documented `options.issue_helper` (branch prefix, commit template, time zone …) was silently reset on every update.
// So known keys are built as now, and unknown keys are written back **verbatim** (including indentation and comments).
// project_type (singular) was removed in v4.1.0 — keeping it makes version_manager reject the file. So it is dropped, not kept.
const OWNED_TOP = new Set(["version", "version_code", "project_types", "project_type", "project_paths", "metadata", "deploy"]);
// Keys under metadata.template.options that the generator writes itself. Only keys not listed here are kept.
// Must match the 6-space keys buildVersionYml writes — a missing one gets written twice on every re-run.
// nexus · npm_publish · synology are old keys — the parser rewrites them in the new form (publish · secret_backup), so keeping them would double-record.
export const OWNED_OPTION_KEYS = new Set(["intent", "deploy", "publish", "secret_backup", "semver_auto", "projects_sync", "close_on_release",
  "language", "label_style", "deploy_trigger_branch", "ci_minutes_saver", "app_release", "excluded_workflows", "store_locales", "store_locales_ios", "store_locales_play",
  "code_review", "changelog",
  "nexus", "npm_publish", "synology"]);

// Cut one key line starting at indent spaces together with its children (deeper indentation, blank lines, comments below) as one chunk.
function keyBlocks(lines, indent, isOwned) {
  const keyRe = new RegExp(`^ {${indent}}([A-Za-z_][\\w-]*):`);
  const blocks = [];
  for (let i = 0; i < lines.length; i++) {
    const m = lines[i].match(keyRe);
    if (!m) continue;
    let j = i + 1;
    while (j < lines.length && (lines[j].trim() === "" || /^\s/.test(lines[j]) && lines[j].search(/\S/) > indent
      || (lines[j].trim().startsWith("#") && lines[j].search(/\S/) > indent))) j++;
    while (j > i + 1 && lines[j - 1].trim() === "") j--;   // Drop blank lines at the end of the chunk
    const block = lines.slice(i, j).join("\n");
    if (!isOwned(m[1]) && looksWellFormed(block)) blocks.push(block);
    i = j - 1;
  }
  return blocks;
}

// If a chunk written back is broken YAML, the whole version.yml breaks — and no workflow can read the version.
// Check only what is possible without dependencies: matching brackets/braces, unclosed quotes. Drop it when in doubt (file integrity before preservation).
function looksWellFormed(block) {
  const text = block.split("\n").map((l) => l.replace(/\s#.*$/, "")).join("\n");   // Leave trailing comments out of the pair check
  const stack = [];
  const pairs = { "]": "[", "}": "{" };
  let quote = null;
  for (const ch of text) {
    if (quote) { if (ch === quote) quote = null; continue; }
    if (ch === '"' || ch === "'") { quote = ch; continue; }
    if (ch === "[" || ch === "{") stack.push(ch);
    else if (ch === "]" || ch === "}") { if (stack.pop() !== pairs[ch]) return false; }
  }
  return !quote && stack.length === 0;
}

/** Extract only what the generator does not know from the existing version.yml. { optionBlocks: string[], topBlocks: string[] } */
export function extractCustomYml(content) {
  const lines = String(content || "").split(/\r?\n/);
  const topBlocks = keyBlocks(lines, 0, (k) => OWNED_TOP.has(k));
  // Cut only the metadata → template → options range and look at 6-space indented keys
  const find = (from, to, re) => { for (let i = from; i < to; i++) if (re.test(lines[i])) return i; return -1; };
  const end = (start, indent) => { let j = start + 1; while (j < lines.length && (lines[j].trim() === "" || lines[j].search(/\S/) > indent)) j++; return j; };
  const md = find(0, lines.length, /^metadata:/);
  let optionBlocks = [];
  if (md >= 0) {
    const mdEnd = end(md, 0);
    const tp = find(md + 1, mdEnd, /^ {2}template:/);
    if (tp >= 0) {
      const tpEnd = end(tp, 2);
      const op = find(tp + 1, tpEnd, /^ {4}options:/);
      if (op >= 0) optionBlocks = keyBlocks(lines.slice(op + 1, end(op, 4)), 6, (k) => OWNED_OPTION_KEYS.has(k));
    }
  }
  return { optionBlocks, topBlocks };
}

/**
 * Helper spread straight into buildVersionYml: `...customYml(path)`.
 * Keeps nothing if the file is missing or unreadable — a read failure must not block the update.
 */
export function customYml(file) {
  try {
    const { optionBlocks, topBlocks } = extractCustomYml(readFileSync(file, "utf8"));
    return { customOptionBlocks: optionBlocks, customTopBlocks: topBlocks };
  } catch {
    return {};
  }
}

// deploy block of the existing version.yml → Map<type, Map<key,value>> (#670 — keeps user edits on re-run).
// To also read the broken structure 4.28.0 produced (a 2-space indented template hanging under deploy),
// the 2-space key `template` is treated as the end of the block, not a type.
export function parseDeployBlock(content) {
  const out = new Map();
  let inDeploy = false;
  let type = null;
  for (const line of String(content || "").split(/\r?\n/)) {
    if (/^deploy:/.test(line)) { inDeploy = true; type = null; continue; }
    if (!inDeploy) continue;
    if (line === "" || /^\s*#/.test(line)) continue;
    if (/^\S/.test(line) || /^ {2}template:/.test(line)) { inDeploy = false; continue; }
    const t = line.match(/^ {2}([A-Za-z0-9_-]+):\s*(#.*)?$/);
    if (t) { type = t[1]; if (!out.has(type)) out.set(type, new Map()); continue; }
    const kv = line.match(/^ {4}([A-Za-z0-9_.-]+):\s*"([^"]*)"/);
    if (kv && type) out.get(type).set(kv[1], kv[2]);
  }
  return out;
}

// On re-run, merge with existing deploy values first (#670) — values the user edited in version.yml are not
// overwritten by template defaults. Existing values win; only keys newly asked this time are added.
export function mergeDeployValues(existingContent, fresh) {
  const merged = parseDeployBlock(existingContent);
  for (const [t, kv] of fresh) {
    if (!merged.has(t)) merged.set(t, new Map());
    for (const [k, v] of kv) if (!merged.get(t).has(k)) merged.get(t).set(k, v);
  }
  return merged;
}

// Generate the whole version.yml (metadata > template options > deploy > user blocks).
// opts: { version, types:[], paths:Map, pathMarkers?:Map, branch, versionCode, now, today, templateOptions? }
// The primary type has no separate key; it is project_types[0] (v4.1.0 SSOT — singular project_type key removed).
//   now   = "YYYY-MM-DD HH:MM:SS" (UTC) — injected for determinism
//   today = "YYYY-MM-DD" (UTC)
//   pathMarkers = Map<type, markerFilename> (for project_paths comments)
//   templateOptions = { templateVersion, deployTarget, publishTargets, includeSecretBackup, optionsDate } (template block)
export function buildVersionYml({ version, types = [], paths = new Map(), pathMarkers = new Map(), branch = "main", deployBranch = "", versionCode = 1, now, today, templateOptions = null, deployValues = new Map(), updatedBy = "template_integrator", customOptionBlocks = [], customTopBlocks = [] }) {
  const lang = templateOptions?.language === "ko" ? "ko" : "en";
  const C = commentsFor(lang);
  const typesJson = types.length ? `[${types.map((t) => `"${t}"`).join(",")}]` : `["basic"]`;

  let out = (lang === "ko" ? HEADER_KO : HEADER_EN) + "\n";
  out += `version: "${version}"\n`;
  out += `version_code: ${versionCode} # ${C.versionCode}\n`;   // One space — must match what version_manager.py writes so updates produce no diff
  out += `project_types: ${typesJson}   # ${C.projectTypes}\n`;

  // project_paths block. pathMarkers: Map<type, markerFilename> (if present, a "  type: "path"   # path/marker" comment).
  if (paths.size) {
    out += `project_paths:                # ${C.projectPaths}\n`;
    for (const [t, p] of paths) {
      const marker = pathMarkers.get(t) || "";
      const pf = p === "." ? marker : (marker ? `${p}/${marker}` : p);
      out += marker ? `  ${t}: "${p}"   # ${pf}\n` : `  ${t}: "${p}"\n`;
    }
  }

  out += `metadata:\n`;
  out += `  last_updated: "${now}"\n`;
  out += `  last_updated_by: "${String(updatedBy || "template_integrator").replace(/"/g, "")}"\n`;
  out += `  default_branch: "${branch}"\n`;
  // Development (release source) branch = release PR head (#456). A separate concept from default_branch (repo default).
  // Written only when set — if unset, skills fall back to develop.
  // Also write deploy_branch: so old skills (changelog_cli) that read only that key do not fall back to develop (#915)
  if (deployBranch) {
    out += `  development_branch: "${deployBranch}"\n`;
    out += `  deploy_branch: "${deployBranch}"   # ${C.legacyDeployBranch}\n`;
  }
  out += `  integrated_from: "projectops"\n`;
  out += `  integration_date: "${today}"\n`;

  // template options block. When templateOptions is given.
  if (templateOptions) {
    const { templateVersion = "unknown", deployTarget = "docker-ssh", publishTargets = [], includeSecretBackup = false, optionsDate = today,
            changelogProvider = "commit", changelogBaseUrl = "", codeReviewCoderabbit = true, aiPrSummary = true, intent = null, mode = null,
            semverAuto = true, appRelease = null, labelStyle = null, deployTriggerBranch = "", ciMinutesSaver = false, closeOnRelease = null, projectsSync = null, language = null, excludedWorkflows = null, storeLocales = null, storeLocalesIos = null, storeLocalesPlay = null } = templateOptions;
    const publishJson = `[${publishTargets.map((t) => `"${t}"`).join(",")}]`;
    // intent (project nature, #485) — if unset, inferred from deploy/publish and recorded (skips the intro question on re-integration)
    const intentVal = intent || inferIntent(deployTarget, publishTargets) || "manual";
    out += `  template:\n`;
    out += `    source: "projectops"\n`;
    out += `    version: "${templateVersion}"\n`;
    // mode (#502) — the scope integrated into this repo. The basis for update mode re-running the same scope.
    if (mode) out += `    mode: "${mode}"   # ${C.mode}\n`;
    out += `    integrated_date: "${optionsDate}"\n`;
    out += `    last_update_date: "${optionsDate}"\n`;
    out += `    options:\n`;
    out += `      intent: "${intentVal}"   # ${C.intent}\n`;
    out += `      deploy: "${deployTarget}"\n`;
    out += `      publish: ${publishJson}\n`;
    out += `      secret_backup: ${includeSecretBackup}\n`;
    // Automatic semver bump (#546) — on release, decides major/minor/patch from commit titles. false means always patch.
    out += `      semver_auto: ${semverAuto}   # ${C.semverAuto}\n`;
    // Projects board sync (#716) — no key written when unset.
    if (projectsSync !== null) out += `      projects_sync: ${projectsSync}   # ${C.projectsSync}\n`;
    // Close done issues on release (#771) — no key written when unset (existing repos keep current behavior).
    if (closeOnRelease !== null) out += `      close_on_release: ${closeOnRelease}   # ${C.closeOnRelease}\n`;
    // Status label style (#776) — no key written when unset (existing repos unchanged).
    // Repo text language (#769) — no key written when unset (existing repos unchanged).
    // Install exclusion list (#810) — full regeneration, so not rewriting it would drop the user's list.
    if (excludedWorkflows && excludedWorkflows.length) out += `      excluded_workflows: [${excludedWorkflows.map((f) => `"${f}"`).join(", ")}]   # ${C.excluded}\n`;
    // Store release note languages (#829) — no key written when unset. Full regeneration, so not rewriting it would drop the user's value.
    if (storeLocales && storeLocales.length) out += `      store_locales: [${storeLocales.map((l) => `"${l}"`).join(", ")}]   # ${C.storeLocales}\n`;
    if (storeLocalesIos && storeLocalesIos.length) out += `      store_locales_ios: [${storeLocalesIos.map((l) => `"${l}"`).join(", ")}]   # App Store: ${C.storeLocalesStore}\n`;
    if (storeLocalesPlay && storeLocalesPlay.length) out += `      store_locales_play: [${storeLocalesPlay.map((l) => `"${l}"`).join(", ")}]   # Play: ${C.storeLocalesStore}\n`;
    if (language) out += `      language: ${language}   # ${C.language}\n`;
    if (labelStyle) out += `      label_style: ${labelStyle}   # ${C.labelStyle}\n`;
    // Deploy trigger branch (#1114) — no key written when unset (existing repos unchanged).
    if (deployTriggerBranch) out += `      deploy_trigger_branch: "${deployTriggerBranch}"   # ${C.deployTriggerBranch}\n`;
    // CI minutes saver (#1114) — written only when on (existing repos unchanged).
    if (ciMinutesSaver) out += `      ci_minutes_saver: true   # ${C.ciMinutesSaver}\n`;
    // Whether the repo deploys through app review (#553) — no key written when unset (existing repos unchanged).
    if (appRelease !== null) {
      out += `      app_release: ${appRelease}   # ${C.appRelease}\n`;
    }
    out += `      code_review:\n`;
    out += `        coderabbit: ${codeReviewCoderabbit}\n`;
    out += `        ai_summary: ${aiPrSummary}\n`;
    out += `      changelog:\n`;
    out += `        provider: "${changelogProvider}"\n`;
    out += `        base_url: "${changelogBaseUrl}"\n`;
    // Options the generator does not know (issue_helper, etc.) are written back as is (#835)
    for (const b of customOptionBlocks) out += `${b}\n`;
  }

  // deploy block. deployValues: Map<type, Map<key,value>>.
  // Only types with WF ask values. Must be a separate top-level key after template — placed between metadata and template,
  // template would become a child of deploy and break the metadata.template.options structure (#670).
  const deployTypes = [...deployValues.keys()].filter((t) => deployValues.get(t) && deployValues.get(t).size > 0);
  if (deployTypes.length) {
    out += `\n`;
    out += `deploy:                          # ${C.deploy}\n`;
    for (const t of deployTypes) {
      out += `  ${t}:\n`;
      for (const [k, v] of deployValues.get(t)) out += `    ${k}: "${v}"\n`;
    }
  }
  // Unknown top-level keys are also kept as is (#835)
  for (const b of customTopBlocks) out += `\n${b}\n`;
  return out;
}
