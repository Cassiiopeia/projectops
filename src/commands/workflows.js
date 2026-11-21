// workflows mode (installs workflows only).
// Order: copy_workflows → update_version_yml_deploy (only if version.yml exists) → scripts → config → util (per type) → setup_guide.
// (Does not generate version.yml — adds the deploy block only when a version.yml already exists.)
import { join } from "node:path";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { PATHS } from "../core/paths.js";
import { copyWorkflows } from "../core/copy/workflows.js";
import { applyLabelStyle } from "../core/label-style.js";
import { copyScripts, copyConfigFolder, copySetupGuide } from "../core/copy/simple.js";
import { copyUtilModules } from "../core/copy/util.js";
import { convertLegacySingularType, mergeDeployValues, commentsFor, upsertBranchKeys } from "../core/version-yml.js";
import { installAgentGuide } from "../core/agent-guide.js";
import { verifyInstall } from "../core/verify.js";

export function runWorkflows(context, tempDir, targetRoot = ".", hooks = {}) {
  const { types = [], force = true, labelStyle } = context;   // labelStyle is decided by resolveOptions
  const wf = copyWorkflows(context, tempDir, targetRoot, hooks);

  const vy = join(targetRoot, PATHS.versionFile);

  // Minimal conversion of the pre-v4.1.0 singular project_type (#471) — the new version_manager copied here
  // rejects the singular key, so without converting, every version workflow fails in a broken state.
  if (existsSync(vy)) {
    const converted = convertLegacySingularType(readFileSync(vy, "utf8"));
    if (converted !== null) writeFileSync(vy, converted);
  }

  // update_version_yml_deploy: update the deploy block only when a version.yml exists and there are ask values
  if (existsSync(vy) && wf.deployValues && wf.deployValues.size) {
    const cur = readFileSync(vy, "utf8");
    writeFileSync(vy, upsertDeployBlock(cur, mergeDeployValues(cur, wf.deployValues), context.language));   // Existing values first (#670)
  }

  // Branch keys (#1248) — workflows mode does not regenerate version.yml, so the typed branches are written here
  // (same result as full mode). Without a version.yml there is nowhere to record them: the run summary says so.
  const isBranchRecorded = writeBranchKeys(vy, context, hooks.trace);

  copyScripts(tempDir, targetRoot);
  copyConfigFolder(tempDir, targetRoot);
  applyLabelStyle(targetRoot, labelStyle); // #776 — aligns workflows (QA bot) and label definitions to the same style
  for (const t of types) copyUtilModules(tempDir, t, { force }, targetRoot);
  copySetupGuide(tempDir, targetRoot);
  installAgentGuide(targetRoot, context.templateVersion);

  // Post-install verification (#549) — all the more needed in a mode that installs only workflows.
  const verification = verifyInstall(targetRoot);
  // Mind the detail key names: the run-trace sensitive value guard filters pat|token|secret|password|credential
  // out of keys (#494). These values are not secrets but "substitution placeholder names" and
  // "key names that need registering", so names that do not trip the guard are used — the guard itself is not bypassed.
  hooks.trace?.event("verify", "scan", "", {
    unresolved: verification.unresolved.length,
    requiredKeys: verification.secrets.size,
  });
  // Unreplaced values are spots that will fail at deploy time — log which file and line.
  for (const u of verification.unresolved) {
    hooks.trace?.event("verify", "unresolved", u.filename, { line: u.line, placeholder: u.token });
  }
  for (const [name, users] of verification.secrets) {
    hooks.trace?.event("verify", "required-key", name, { workflows: users });
  }

  return { workflows: wf, verification, isBranchRecorded };
}

/**
 * Typed branches > existing version.yml (development_branch, deploy_trigger_branch)
 * Returns true = written or nothing to write, false = values given but no version.yml
 */
function writeBranchKeys(versionYmlPath, context, trace = null) {
  const deployBranch = context.deployBranch || "";
  const deployTriggerBranch = context.deployTriggerBranch || "";
  if (!existsSync(versionYmlPath)) {
    const hasBranchValues = !!(deployBranch || deployTriggerBranch);
    if (hasBranchValues) trace?.event("branch", "not-recorded", "version.yml", { deployBranch, deployTriggerBranch, reason: "version-yml-missing" });
    return !hasBranchValues;
  }
  const current = readFileSync(versionYmlPath, "utf8");
  const updated = upsertBranchKeys(current, { deployBranch, deployTriggerBranch, language: context.language });
  if (updated !== current) {
    writeFileSync(versionYmlPath, updated);
    trace?.event("branch", "recorded", "version.yml", { deployBranch: deployBranch || null, deployTriggerBranch: deployTriggerBranch || null });
  }
  return true;
}

// Remove the deploy: block from the existing version.yml and append a new one (idempotent).
// language: resolved repo text language (en | ko), picks the deploy: line comment (#1214)
export function upsertDeployBlock(content, deployValues, language) {
  // Remove the existing deploy: block (from the deploy: line up to the next top-level key)
  const lines = content.split(/\r?\n/);
  const out = [];
  let inDeploy = false;
  for (const line of lines) {
    if (/^deploy:/.test(line)) { inDeploy = true; continue; }
    if (inDeploy) {
      // Broken structure made by 4.28.0: a 2-space `template:` under deploy is a child of metadata, not deploy content (#670)
      if (/^ {2}template:/.test(line)) inDeploy = false;
      else if (/^\s/.test(line) || line === "") continue; // Indented/blank line = inside deploy
      else inDeploy = false;
    }
    out.push(line);
  }
  let text = out.join("\n").replace(/\n+$/, "\n");
  // Append the new deploy block
  const deployTypes = [...deployValues.keys()].filter((t) => deployValues.get(t)?.size);
  if (deployTypes.length) {
    text += `\ndeploy:                          # ${commentsFor(language).deploy}\n`;
    for (const t of deployTypes) {
      text += `  ${t}:\n`;
      for (const [k, v] of deployValues.get(t)) text += `    ${k}: "${v}"\n`;
    }
  }
  return text;
}
