// Workflow copy engine.
//
// Conflict decisions (differs from the existing file) come in via hooks.decisions (Map<filename, 'skip'|'backup'|'template'>).
//   - The real wizard (commands/interactive.js) gets the conflict list from listWorkflowConflicts and builds the Map itself.
import { join, basename } from "node:path";
import { existsSync, readFileSync, writeFileSync, renameSync } from "node:fs";
import { PATHS } from "../paths.js";
import { exists, copyFileSync, listYamlFiles } from "../fsutil.js";
import { isUnchanged, substituteEnv, resolveGlobalTokens, extractEnvValues } from "../wizard-env.js";
import { isUserModified, readBaseline, writeBaseline, sha256 } from "../baseline.js";
import { substituteBranches } from "../branch-sub.js";
import { collectBranchNames, compareBranchLines } from "../branch-diff.js";
import { saveIncoming, lineDiffCounts } from "../incoming.js";
import { branchStatus } from "../git-branch.js";
import { PUBLISH_TARGETS } from "../constants.js";
import { commonOptionalGroups, serverDeployEnabled, SERVER_DEPLOY_DIR } from "../workflow-groups.js";
import { t } from "../../i18n/index.js";

// Are all branch filters in the on: block develop only? (#810)
// Spots workflows that would never run when installed in a repo without a development branch.
// Any event other than workflow_dispatch (schedule, issues, etc.) can make it run on its own, so false.
export function onlyTriggersOnDevelop(content) {
  const m = String(content).match(/^on:\s*\n((?:[ \t]+.*\n|\s*\n)+)/m);
  if (!m) return false;
  const block = m[1];
  const events = [...block.matchAll(/^ {2}([a-z_]+):/gm)].map((x) => x[1]);
  if (!events.length || events.some((e) => !["push", "pull_request", "workflow_dispatch"].includes(e))) return false;
  const branches = [];
  for (const b of block.matchAll(/^\s+branches:\s*\[([^\]]*)\]/gm)) branches.push(...b[1].split(",").map((s) => s.trim().replace(/["']/g, "")).filter(Boolean));
  for (const b of block.matchAll(/^\s+branches:\s*\n((?:\s+-\s*.*\n)+)/gm)) branches.push(...[...b[1].matchAll(/-\s*["']?([^"'\s#]+)/g)].map((x) => x[1]));
  // Every push/pull_request needs a branches filter — a push without a filter runs on every branch
  const filtered = (block.match(/^\s+branches:/gm) || []).length;
  const needFilter = events.filter((e) => e !== "workflow_dispatch").length;
  return branches.length > 0 && filtered >= needFilter && branches.every((b) => b === "develop");
}

// Apply env substitution to one file and update the target file.
// values/useDefaults: env plan (promptEnvPlan) result — if unset, the default path (current force behavior).
// trace (#494): one env.substituted event per substitution (with before/after — evidence to spot substitution mismatch bugs at once).
function configureEnv(targetPath, filename, { type, projectPath = ".", repoName = "", resolvers = {}, collectAsks = null, values = new Map(), useDefaults = true, trace = null }) {
  const content = readFileSync(targetPath, "utf8");
  if (!content.includes("@wizard")) return;
  const collectSubs = trace ? [] : null;
  const out = substituteEnv(content, { type, useDefaults, values, projectPath, repoName, resolvers, collectAsks, collectSubs });
  writeFileSync(targetPath, out);
  if (trace && collectSubs) {
    for (const s of collectSubs) trace.event("env", "substituted", filename, { type, ...s });
  }
}

// util version sync workflow (#491) — meaningful only in repos with .github/util/ modules (version.json).
// Copied into a repo without util (e.g. spring alone), its trigger never fires — no-op pollution.
const UTIL_VERSION_SYNC = "PROJECT-COMMON-TEMPLATE-UTIL-VERSION-SYNC.yml";

// Will util modules exist in this integration — true if already in the target (update),
// or if the selected types' util is in the template and about to be copied (runFull step 6).
function utilSyncApplies(tempDir, targetRoot, types) {
  if (exists(join(targetRoot, ".github", "util"))) return true;
  return types.some((t) => exists(join(tempDir, ".github", "util", t)));
}

// version.yml before this run — holds the branch names the installed workflows were rendered with
function readPreviousVersionYml(targetRoot) {
  const vy = join(targetRoot, PATHS.versionFile);
  try { return existsSync(vy) ? readFileSync(vy, "utf8") : ""; } catch { return ""; }
}

// Incoming render against the installed copy, same pipeline as install: template > env (installed values kept) > branches
// envOpts null = common files (copied raw, no env substitution)
function renderAgainstInstalled(srcDir, filename, envOpts, branches, installed) {
  let content = readFileSync(join(srcDir, filename), "utf8");
  if (envOpts) content = substituteEnv(content, { ...envOpts, values: extractEnvValues(installed), useDefaults: false });
  return substituteBranches(content, branches, filename);
}

// Kept user-modified workflow whose only difference from the incoming render is branch names (#1248)
function isBranchOnlyConflict({ srcDir, filename, workflowsDir, envOpts, branches, branchNames }) {
  const dst = join(workflowsDir, filename);
  if (!existsSync(dst)) return false;
  try {
    const installed = readFileSync(dst, "utf8");
    return compareBranchLines(installed, renderAgainstInstalled(srcDir, filename, envOpts, branches, installed), branchNames).isBranchOnly;
  } catch { return false; }
}

// 4 classes (new/unchanged/upstream/changed) — relative to the target workflow directory.
//
// upstream (#557): the user did not touch it, only the template changed. No reason to ask,
// so just bring it up to date. Needs the baseline (install-time hashes) to decide.
// Without a baseline or a record for the file, it cannot be decided → falls into changed as before
// (behavior of existing integrated repos does not change).
function classify(srcDir, workflowsDir, envOpts, baseline = null) {
  const result = { newFiles: [], unchanged: [], changed: [], upstream: [] };
  for (const filename of listYamlFiles(srcDir)) {
    const src = join(srcDir, filename);
    const dst = join(workflowsDir, filename);
    if (existsSync(dst)) {
      const tpl = readFileSync(src, "utf8");
      const inst = readFileSync(dst, "utf8");
      if (isUnchanged(tpl, inst, { ...envOpts, filename })) { result.unchanged.push(filename); continue; }
      // Reaching here means "current template render ≠ installed copy" — either a user edit or an upstream change.
      // The baseline tells the two apart.
      const modified = isUserModified(baseline, filename, inst);
      if (modified === false) result.upstream.push(filename);
      else result.changed.push(filename);
    } else {
      result.newFiles.push(filename);
    }
  }
  return result;
}

// copy_workflows main body (sync — existing callers unchanged).
// context: { types:[], paths:Map, deployTarget, publishTargets:[], includeSecretBackup, aiPrSummary, force, repoName, resolvers,
//            envValues?:Map<key,value>, envUseDefaults?:boolean }  ← injection point for the env plan (promptEnvPlan) result
//   deployTarget (#439 pick one): 'docker-ssh' (default) | 'vercel' | 'none' — server-deploy only with docker-ssh,
//   common/deploy/<target>/ copied for that target. publishTargets (#439 multiple): 'nexus'|'npm'|'github-packages'.
// hooks: { decisions?: Map<filename, 'skip'|'backup'|'template'> } — conflict decisions for existing (changed) files.
// Returns {copied, skipped, templateAdded, optionalCopied, copiedFiles[]} — copiedFiles are the file names actually copied or replaced (#473 summary)
export function copyWorkflows(context, tempDir, targetRoot = ".", hooks = {}) {
  const { types = [], paths = new Map(), deployTarget = "docker-ssh", publishTargets = [], includeSecretBackup = false, aiPrSummary = true, projectsSync = true, repoName = "", resolvers = {}, envValues = new Map(), envUseDefaults = true, branch = "", deployBranch = "", deployTriggerBranch = "", ciMinutesSaver = false } = context;
  const decisions = hooks.decisions instanceof Map ? hooks.decisions : new Map();
  const trace = hooks.trace ?? null; // #494 — run trace (null-safe: every event is a no-op when not injected)
  const workflowsDir = join(targetRoot, PATHS.workflowsDir);
  // Install-time reference point (#557) — null if missing, and classify falls back to the old 2-way check.
  const baseline = readBaseline(targetRoot);
  const projectTypesDir = join(tempDir, PATHS.workflowsDir, PATHS.projectTypesDir);
  if (!exists(projectTypesDir)) throw new Error(t("copy.templateStructureError"));

  const counters = { copied: 0, skipped: 0, templateAdded: 0, optionalCopied: 0, copiedFiles: [],
    replacedBak: [], // #673 — files replaced after a .bak backup without knowing whether they were edited (no reference point)
    skippedConflicts: [] }; // #654 — { filename, incoming, added, removed } per kept user-edited file
  const deployValues = new Map(); // Map<type, Map<key,value>> — ask values for the deploy block
  counters.deployValues = deployValues;
  // Branch strategy (#477) — with the standard (main/develop), substitution and virtual comparison are both no-ops
  const branches = { defaultBranch: branch || "main", deployBranch: deployBranch || "develop", deployTriggerBranch: deployTriggerBranch || "", ciMinutesSaver: !!ciMinutesSaver };
  // values/useDefaults matter only on the substitution path (isUnchanged forces useDefaults:true internally — virtual comparison intact)
  const envOptsFor = (type) => ({ type, projectPath: paths.get(type) || ".", repoName, resolvers, values: envValues, useDefaults: envUseDefaults, branches });
  // Branch names old and new (#1248) — basis for spotting kept workflows that differ only in branch names
  const branchNames = collectBranchNames(branches, readPreviousVersionYml(targetRoot));
  const branchSynced = []; // Files applied because only branch names differed (original kept as .bak)
  Object.defineProperty(counters, "branchSynced", { value: branchSynced, enumerable: false });
  Object.defineProperty(counters, "isBranchOnly", {
    value: (srcDir, filename, type) => isBranchOnlyConflict({
      srcDir, filename, workflowsDir, envOpts: type === "common" ? null : envOptsFor(type), branches, branchNames }),
    enumerable: false,
  });

  // New files not to install (#810) — the ones that came back on every install.
  //   excluded        : files the user listed in version.yml options.excluded_workflows
  //   deleted-by-user : we have an install record (baseline) but the file is gone = the user deleted it (.bak files are our own cleanup, so excluded)
  //   no-dev-branch   : workflows that run only on the development branch when it is definitely missing on the remote
  const notInstalled = [];
  Object.defineProperty(counters, "notInstalled", { value: notInstalled, enumerable: false });
  const excludedSet = new Set(context.excludedWorkflows || []);
  const devName = branches.deployBranch;
  let devMissing = null; // Query the remote only once, when needed
  const isDevMissing = () => {
    if (devMissing === null) {
      const st = devName === branches.defaultBranch ? null : branchStatus(targetRoot, devName);
      devMissing = !!(st && st.isRepo && !st.local && st.remote === false);
    }
    return devMissing;
  };
  const skipNew = (srcDir, filename, group) => {
    const dst = join(workflowsDir, filename);
    if (existsSync(dst)) return false;
    let reason = null;
    if (excludedSet.has(filename)) reason = "excluded";
    else if (baseline?.files?.[filename] && !existsSync(dst + ".bak")) reason = "deleted-by-user";
    else if (onlyTriggersOnDevelop(readFileSync(join(srcDir, filename), "utf8")) && isDevMissing()) reason = "no-dev-branch";
    if (!reason) return false;
    const info = { filename, reason, incoming: "" };
    try {
      // Leave the render in incoming so a change of mind can restore it with one cp
      const rendered = substituteBranches(substituteEnv(readFileSync(join(srcDir, filename), "utf8"),
        { ...envOptsFor(group.split("/")[0]), useDefaults: true }), branches, filename);
      info.incoming = saveIncoming(targetRoot, filename, rendered);
    } catch { /* Only the notice is lost */ }
    notInstalled.push(info);
    trace?.event("copy", "not-installed", filename, { group, reason });
    return true;
  };
  Object.defineProperty(counters, "skipNew", { value: skipNew, enumerable: false });

  // When keeping a user-edited file, leave a copy of the new template in incoming (#654).
  // Failures shrink to one warning line — the merge notice must not kill the whole copy.
  const onSkip = (srcDir, filename, type) => {
    const info = { filename, incoming: "", added: null, removed: null, branchLineCount: 0 };
    try {
      // Must go through the same render as install (default substitution + branch substitution) so the diff shows only "real differences"
      const rendered = substituteBranches(
        substituteEnv(readFileSync(join(srcDir, filename), "utf8"), { ...envOptsFor(type), useDefaults: true }), branches, filename);
      info.incoming = saveIncoming(targetRoot, filename, rendered);
      const installed = readFileSync(join(workflowsDir, filename), "utf8");
      const d = lineDiffCounts(installed, rendered);
      info.added = d.added; info.removed = d.removed;
      // Lines still naming the old branch (#1248) — the run summary lists the typed branch as not applied in this file
      const againstInstalled = renderAgainstInstalled(srcDir, filename, type === "common" ? null : envOptsFor(type), branches, installed);
      info.branchLineCount = compareBranchLines(installed, againstInstalled, branchNames).branchLineCount;
    } catch (e) {
      trace?.event("copy", "incoming-failed", filename, { message: e?.message || String(e) });
      console.error(t("copy.incomingSaveFailed", { file: filename, error: e?.message || e }));
    }
    counters.skippedConflicts.push(info);
    return info;
  };
  // Do not add enumerable fields to the returned object (existing callers and tests rely on the counters shape)
  Object.defineProperty(counters, "onSkip", { value: onSkip, enumerable: false });

  // (1) common — gets the same checks and protection as per-type files (#560).
  // Workflows like the release pipeline, where each project appends different steps, get edited by users even in common.
  // So edited files are not blindly overwritten; they go through the same conflict check and backup as per-type files.
  const commonDir = join(projectTypesDir, "common");
  if (exists(commonDir)) {
    const commonEnv = envOptsFor("common");
    const commonClass = classify(commonDir, workflowsDir, commonEnv, baseline);
    for (const filename of listYamlFiles(commonDir)) {
      // #491 — copy the util sync workflow only to repos that have (or will have) util modules
      if (filename === UTIL_VERSION_SYNC && !utilSyncApplies(tempDir, targetRoot, types)) {
        trace?.event("copy", "excluded", filename, { reason: "util-modules-absent" });
        continue;
      }
      if (commonClass.unchanged.includes(filename)) {
        counters.skipped++;
        trace?.event("copy", "skipped-unchanged", filename, { group: "common" });
        continue;
      }
      // Never touched by the user, only the template changed — bring it up to date without asking (as before).
      if (commonClass.newFiles.includes(filename) && skipNew(commonDir, filename, "common")) continue;
      if (commonClass.newFiles.includes(filename) || commonClass.upstream.includes(filename)) {
        copyFileSync(join(commonDir, filename), join(workflowsDir, filename));
        counters.copied++;
        counters.copiedFiles.push(filename);
        trace?.event("copy", commonClass.upstream.includes(filename) ? "upstream-updated" : "copied",
                     filename, { group: "common" });
        continue;
      }
      // From here on, changed — "current template render ≠ installed copy". It splits two ways.
      const dst = join(workflowsDir, filename);
      const modified = isUserModified(baseline, filename, readFileSync(dst, "utf8"));
      if (modified === null) {
        // Cannot decide (no reference point = existing integrated repo). common's old contract is "always update to latest",
        // so skipping here would leave existing repos without updates forever. Keep the contract but leave a way
        // back — a .bak before overwriting. (#560: even common/deploy left a .bak, only the main body did not)
        renameSync(dst, dst + ".bak");
        copyFileSync(join(commonDir, filename), dst);
        counters.copied++;
        counters.copiedFiles.push(filename);
        trace?.event("copy", "replaced-bak", filename, { group: "common", reason: "baseline-absent" });
        counters.replacedBak.push(filename);   // #673 — show on screen that a possibly edited file was replaced
        continue;
      }
      // A file confirmed as touched by the user — handled by the decision (kept if unset).
      applyDecision(decisions.get(filename), commonDir, workflowsDir, filename, counters, trace, "common");
    }
  }

  // (2~4) per type
  for (const type of types) {
    const asks = new Map();
    copyWorkflowsForType(type, projectTypesDir, workflowsDir, { deployTarget, publishTargets, ...context, envOptsFor, collectAsks: asks, decisions, trace, baseline }, counters);
    if (asks.size) deployValues.set(type, asks);
  }

  // (4.5~5) optional folders under common/ — deploy/<target>, pr-summary, projects-sync, secret-backup.
  // Which folders are on is decided in one place, workflow-groups.js (#851). Orphan detection uses the same table.
  //   bak-replace: skip if identical to the template, else keep a .bak and replace.
  //   new-only   : leave alone if it exists. Fill in the repo name only on a fresh install (#729 — with a fixed value,
  //                every project would overwrite secrets in the same server folder).
  for (const group of commonOptionalGroups(commonDir, { includeSecretBackup, aiPrSummary, projectsSync, deployTarget })) {
    const groupDir = join(commonDir, group.dir);
    if (!group.enabled || !exists(groupDir)) continue;
    for (const filename of listYamlFiles(groupDir)) {
      const src = join(groupDir, filename);
      const dst = join(workflowsDir, filename);
      if (group.policy === "new-only") {
        if (existsSync(dst)) continue;
        if (skipNew(groupDir, filename, group.copyLabel)) continue;
        copyFileSync(src, dst);
        const raw = readFileSync(dst, "utf8");
        const filled = resolveGlobalTokens(raw, repoName || "my-project");
        if (filled !== raw) writeFileSync(dst, filled);
        counters.optionalCopied++;
        counters.copied++;
        counters.copiedFiles.push(filename);
        trace?.event("copy", "copied", filename, { group: group.copyLabel });
        continue;
      }
      if (existsSync(dst) && isUnchanged(readFileSync(src, "utf8"), readFileSync(dst, "utf8"), { ...envOptsFor("common"), filename })) {
        counters.skipped++;
        trace?.event("copy", "skipped-unchanged", filename, { group: group.copyLabel });
        continue;
      }
      if (skipNew(groupDir, filename, group.copyLabel)) continue;
      const backedUp = existsSync(dst);
      if (backedUp) renameSync(dst, dst + ".bak");
      copyFileSync(src, dst);
      counters.optionalCopied++;
      counters.copied++;
      counters.copiedFiles.push(filename);
      trace?.event("copy", backedUp ? "replaced-bak" : "copied", filename, { group: group.copyLabel });
      if (backedUp) counters.replacedBak.push(filename);   // #673
    }
  }

  // (6) Branch substitution post-pass (#477) — applied to copied files only for a non-standard branch strategy or the CI minutes saver (#1114).
  // The isUnchanged virtual comparison uses the same branches, so the next update has no recopy churn.
  if (branches.defaultBranch !== "main" || branches.deployBranch !== "develop" || branches.deployTriggerBranch || branches.ciMinutesSaver) {
    for (const f of counters.copiedFiles) {
      const p = join(workflowsDir, f);
      if (!existsSync(p)) continue;
      const before = readFileSync(p, "utf8");
      const after = substituteBranches(before, branches, f);
      if (after !== before) {
        writeFileSync(p, after);
        trace?.event("env", "branch-substituted", f, { defaultBranch: branches.defaultBranch, deployBranch: branches.deployBranch, deployTriggerBranch: branches.deployTriggerBranch, ciMinutesSaver: branches.ciMinutesSaver });
      }
    }
  }

  // (7) Record the reference point (#557) — the basis for the next update to tell "who changed it".
  //     Update installed only for files actually written this time. Recording kept (skipped) files as if we wrote them
  //     would silently overwrite user edits on the next update.
  recordBaseline(workflowsDir, targetRoot, counters, baseline, context.templateVersion, context.now, trace);

  return counters;
}

// Keep the disk content right after install as the reference point. Failure does not block the integration —
// without a reference point, the next update just falls back to the old 2-way check.
function recordBaseline(workflowsDir, targetRoot, counters, previous, templateVersion, now, trace = null) {
  try {
    const entries = new Map();
    for (const f of counters.copiedFiles || []) {
      const p = join(workflowsDir, f);
      if (!existsSync(p)) continue;
      const content = readFileSync(p, "utf8");
      // The final disk content after substitution is both what we wrote and the render result at this point.
      entries.set(f, { installed: sha256(content), rendered: sha256(content) });
    }
    if (entries.size === 0 && previous) return; // Nothing newly written — leave the existing reference point alone
    trace?.event("baseline", "recorded", "", { files: entries.size, hadPrevious: !!previous });
    writeBaseline(targetRoot, {
      templateVersion: templateVersion || "unknown",
      installedAt: now || "",
      entries,
      previous,
    });
  } catch (e) {
    // Failing to record the reference point is not an integration failure
    trace?.event("baseline", "baseline-failed", "", { message: e?.message || String(e) });
  }
}

// Handle one changed file (exists and content changed) by decision (3 choices: backup and replace, template copy, keep).
// 'skip' (default): keep existing. 'backup': existing → .bak then replace. 'template': keep existing + new version as .template.yaml.
// carry(filename, installedContent): keeps the installed env values for re-substitution (per-type files only)
function applyDecision(decision, srcDir, workflowsDir, filename, counters, trace = null, type = "", carry = null) {
  const src = join(srcDir, filename);
  const dst = join(workflowsDir, filename);
  // Only branch names differ (#1248): apply the configured branches instead of keeping the old ones (.bak kept)
  if (decision !== "backup" && decision !== "template" && counters.isBranchOnly?.(srcDir, filename, type)) {
    carry?.(filename, readFileSync(dst, "utf8"));
    renameSync(dst, dst + ".bak");
    copyFileSync(src, dst);
    counters.copied++;
    counters.copiedFiles?.push(filename);
    counters.branchSynced?.push(filename);
    trace?.event("copy", "branch-synced", filename, {
      decision: decision ?? "skip", note: "only branch names differed — applied the configured branches, original kept as .bak",
    });
    return;
  }
  if (decision === "backup") {
    // Backup and replace: back up the existing file as .bak, then replace with the new version
    renameSync(dst, dst + ".bak");
    copyFileSync(src, dst);
    counters.copied++;
    counters.copiedFiles?.push(filename);
    trace?.event("copy", "replaced-bak", filename, { decision });
    return;
  }
  if (decision === "template") {
    // Template copy: `<name>.template.yaml` — strips only .yaml (.yml stays and the suffix is appended)
    const templateName = (filename.endsWith(".yaml") ? filename.slice(0, -".yaml".length) : filename) + ".template.yaml";
    copyFileSync(src, join(workflowsDir, templateName)); // Overwrites an existing .template.yaml
    counters.templateAdded++;
    trace?.event("copy", "template-added", templateName, { original: filename });
    return;
  }
  counters.skipped++; // 'skip'/unset/ESC → keep existing (force default)
  // #654 — leave the new template in incoming and record diff line counts in detail
  const inc = counters.onSkip?.(srcDir, filename, type) ?? {};
  trace?.event("copy", "skipped-conflict", filename, {
    decision: decision ?? "skip", note: "kept the user-modified file — candidate for merge review",
    incoming: inc.incoming || null, added: inc.added ?? null, removed: inc.removed ?? null,
  });
}

// List only changed (conflict) files in the target workflow directory — used by the wizard (commands/interactive.js).
// Must use the same classify rules as copyWorkflows so the decision Map matches the real targets 1:1.
export function listWorkflowConflicts(context, tempDir, targetRoot = ".") {
  const { types = [], paths = new Map(), deployTarget = "docker-ssh", repoName = "", resolvers = {}, branch = "", deployBranch = "", deployTriggerBranch = "", ciMinutesSaver = false } = context;
  const workflowsDir = join(targetRoot, PATHS.workflowsDir);
  // Install-time reference point (#557) — null if missing, and classify falls back to the old 2-way check.
  const baseline = readBaseline(targetRoot);
  const projectTypesDir = join(tempDir, PATHS.workflowsDir, PATHS.projectTypesDir);
  const conflicts = []; // [{ filename, type }] — same order as the engine (common → type loop → server-deploy)
  const branches = { defaultBranch: branch || "main", deployBranch: deployBranch || "develop", deployTriggerBranch: deployTriggerBranch || "", ciMinutesSaver: !!ciMinutesSaver }; // #477 — same rules as the engine
  // Branch-only differences are applied by the engine without asking (#1248), so they are not listed
  const branchNames = collectBranchNames(branches, readPreviousVersionYml(targetRoot));
  const isAsked = (srcDir, filename, envOpts) => !isBranchOnlyConflict({ srcDir, filename, workflowsDir, envOpts, branches, branchNames });

  // common (#560) — only files "confirmed" as touched by the user are asked about.
  // Files that cannot be decided (no reference point) are not asked; the engine leaves a .bak and overwrites them.
  const commonDir = join(projectTypesDir, "common");
  if (exists(commonDir)) {
    const commonEnv = { type: "common", projectPath: ".", repoName, resolvers, branches };
    for (const f of classify(commonDir, workflowsDir, commonEnv, baseline).changed) {
      const dst = join(workflowsDir, f);
      if (!existsSync(dst)) continue;
      if (isUserModified(baseline, f, readFileSync(dst, "utf8")) !== true) continue;
      if (!isAsked(commonDir, f, null)) continue;
      conflicts.push({ filename: f, type: "common" });
    }
  }

  for (const type of types) {
    const envOpts = { type, projectPath: paths.get(type) || ".", repoName, resolvers, branches };
    const typeDir = join(projectTypesDir, type);
    if (exists(typeDir)) {
      for (const f of classify(typeDir, workflowsDir, envOpts, baseline).changed) if (isAsked(typeDir, f, envOpts)) conflicts.push({ filename: f, type });
    }
    const serverDeployDir = join(typeDir, SERVER_DEPLOY_DIR);
    if (exists(serverDeployDir) && serverDeployEnabled(deployTarget)) {
      for (const f of classify(serverDeployDir, workflowsDir, envOpts, baseline).changed) if (isAsked(serverDeployDir, f, envOpts)) conflicts.push({ filename: f, type });
    }
  }
  return conflicts;
}
function copyWorkflowsForType(type, projectTypesDir, workflowsDir, ctx, counters) {
  const { deployTarget = "docker-ssh", publishTargets = [], force = false, paths = new Map(), repoName = "", resolvers = {}, envOptsFor, collectAsks = null, decisions = new Map(), trace = null, baseline = null } = ctx;
  const typeDir = join(projectTypesDir, type);
  const envOpts = envOptsFor(type);
  let unchangedNames = [];
  // Env values of the installed copy before the upstream update (found while investigating #810). When reinstalling a file where only the template changed,
  // it was re-substituted with defaults, silently turning user choices (JAVA_VERSION 17, etc.) back to 21.
  const carried = new Map(); // Map<filename, Map<key,value>>
  const upstreamCopy = (srcDir, f, group) => {
    const dst = join(workflowsDir, f);
    try { carried.set(f, extractEnvValues(readFileSync(dst, "utf8"))); } catch { /* Read failed — use defaults */ }
    copyFileSync(join(srcDir, f), dst);
    counters.copied++; counters.copiedFiles.push(f);
    trace?.event("copy", "upstream-updated", f, { group, reason: "baseline-match", carried: carried.get(f)?.size ?? 0 });
  };
  // Branch-only sync (#1248) keeps the installed env values the same way
  const carryEnv = (f, installed) => { try { carried.set(f, extractEnvValues(installed)); } catch { /* Use defaults */ } };

  // Per-type workflows (direct children)
  if (exists(typeDir)) {
    const { newFiles, unchanged, changed, upstream } = classify(typeDir, workflowsDir, envOpts, baseline);
    unchangedNames = unchanged.slice();
    for (const f of unchanged) { counters.skipped++; trace?.event("copy", "skipped-unchanged", f, { group: type }); }
    for (const f of newFiles) { if (counters.skipNew(typeDir, f, type)) continue; copyFileSync(join(typeDir, f), join(workflowsDir, f)); counters.copied++; counters.copiedFiles.push(f); trace?.event("copy", "copied", f, { group: type }); }
    // upstream (#557): not touched by the user, only the template changed — bring it up to date without asking.
    for (const f of upstream) upstreamCopy(typeDir, f, type);
    // changed: handled by the decision Map (unset = skip → same as the current force behavior)
    for (const f of changed) applyDecision(decisions.get(f), typeDir, workflowsDir, f, counters, trace, type, carryEnv);
  }

  // server-deploy — included only with deploy=docker-ssh (#439)
  const serverDeployDir = join(typeDir, SERVER_DEPLOY_DIR);
  if (exists(serverDeployDir) && serverDeployEnabled(deployTarget)) {
    const { newFiles, unchanged, changed, upstream } = classify(serverDeployDir, workflowsDir, envOpts, baseline);
    for (const f of unchanged) { counters.skipped++; trace?.event("copy", "skipped-unchanged", f, { group: `${type}/server-deploy` }); }
    for (const f of newFiles) { if (counters.skipNew(serverDeployDir, f, `${type}/server-deploy`)) continue; copyFileSync(join(serverDeployDir, f), join(workflowsDir, f)); counters.copied++; counters.copiedFiles.push(f); trace?.event("copy", "copied", f, { group: `${type}/server-deploy` }); }
    for (const f of upstream) upstreamCopy(serverDeployDir, f, `${type}/server-deploy`);
    for (const f of changed) applyDecision(decisions.get(f), serverDeployDir, workflowsDir, f, counters, trace, type, carryEnv);
  }

  // publish/<target> (opt-in — #439 publish axis. The type is only the file location, not a gate)
  const pubDirs = [];
  for (const target of PUBLISH_TARGETS) {
    const pubDir = join(typeDir, "publish", target);
    pubDirs.push(pubDir);
    if (!exists(pubDir) || !publishTargets.includes(target)) continue;
    for (const filename of listYamlFiles(pubDir)) {
      const src = join(pubDir, filename);
      const dst = join(workflowsDir, filename);
      if (existsSync(dst) && isUnchanged(readFileSync(src, "utf8"), readFileSync(dst, "utf8"), { ...envOpts, filename })) {
        counters.skipped++;
        trace?.event("copy", "skipped-unchanged", filename, { group: `${type}/publish/${target}` });
        continue;
      }
      if (counters.skipNew(pubDir, filename, `${type}/publish/${target}`)) continue;
      const backedUp = existsSync(dst);
      if (backedUp) renameSync(dst, dst + ".bak");
      copyFileSync(src, dst);
      counters.optionalCopied++;
      counters.copied++;
      counters.copiedFiles.push(filename);
      trace?.event("copy", backedUp ? "replaced-bak" : "copied", filename, { group: `${type}/publish/${target}` });
      if (backedUp) counters.replacedBak.push(filename);   // #673
    }
  }

  // env substitution — only files copied from this type's source directories that exist and are not unchanged
  for (const srcDir of [typeDir, serverDeployDir, ...pubDirs]) {
    if (!exists(srcDir)) continue;
    for (const filename of listYamlFiles(srcDir)) {
      const target = join(workflowsDir, filename);
      if (!existsSync(target)) continue;            // Skip skipped files
      if (unchangedNames.includes(filename)) continue; // Skip unchanged
      const prev = carried.get(filename);
      if (prev && prev.size) {
        // Overlay values explicitly chosen in this run on top of carried-over values (explicit choice wins)
        const values = new Map([...prev, ...(envOpts.useDefaults ? [] : envOpts.values)]);
        configureEnv(target, filename, { ...envOpts, values, useDefaults: false, collectAsks, trace });
      } else {
        configureEnv(target, filename, { ...envOpts, collectAsks, trace }); // includes env plan values/useDefaults
      }
    }
  }
}
