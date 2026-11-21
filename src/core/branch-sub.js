// Workflow branch substitution (#477) — when the target repo's branch strategy differs from the standard (main/develop),
// replace branch literals in the copied workflows with the configured values.
// For standard values the input is returned as is (no-op) — staying byte-identical to the template keeps
// the isUnchanged skip logic and the "standard repo stays unchanged" contract intact.
//
// Only patterns found by a full survey (#477) are substituted (no globs or blanket replace — avoids collateral damage):
//   1) inline trigger:     branches: ["main"] / [develop] / [ develop ] / ["develop"]
//   2) multi-line trigger: "  - main" / "  - develop" alone on a line (trailing comment allowed)
//   3) release guard:      == 'develop'  (RELEASE-CHANGELOG automerge head guard)
//   4) inside a step:      git fetch origin main  (RELEASE-CHANGELOG commit analysis)
//   5) deploy trigger (#1114): deploy workflow files only, main > deployTriggerBranch (DEPLOY_TRIGGER_WORKFLOWS below)
//   6) branch check in deploy scripts (#1114): [ "$BRANCH" == "main" ] (REACT-CICD allowed-branch check)
//   7) CI minutes saver (#1114): with ciMinutesSaver, ci-minutes-sub.js (before branch substitution, on the raw template)

import { substituteCiMinutesSaver } from "./ci-minutes-sub.js";
import { deployTriggerWorkflows } from "./project-types.js";

// main (default branch) substitutions
function subDefault(s, db) {
  s = s.replace(/^(\s*branches:\s*\[\s*["']?)main(["']?\s*\])/gm, `$1${db}$2`);
  s = s.replace(/^(\s*-\s*)main(\s*(?:#.*)?)$/gm, `$1${db}$2`);
  s = s.replace(/\bgit fetch origin main\b/g, `git fetch origin ${db}`);
  s = s.replace(/"\$BRANCH" == "main"/g, `"$BRANCH" == "${db}"`);
  return s;
}

// develop (development/release head branch) substitutions
function subDeploy(s, dev) {
  s = s.replace(/^(\s*branches:\s*\[\s*["']?)develop(["']?\s*\])/gm, `$1${dev}$2`);
  s = s.replace(/^(\s*-\s*)develop(\s*(?:#.*)?)$/gm, `$1${dev}$2`);
  s = s.replace(/== 'develop'/g, `== '${dev}'`);
  return s;
}

// Workflows that deploy when pushed (exact file name match). Used only in repos that split the default and deploy branches.
// Common workflows (version bump · README version · release notes · issue close) are not here: they follow the default branch.
// Type-owned files come from the registry (deploy_trigger_workflows); a missing file deploys from the default branch.
// Vercel is the only type-independent one
const TYPE_INDEPENDENT_DEPLOY_WORKFLOWS = ["PROJECT-COMMON-VERCEL-DEPLOY.yaml"];
export const DEPLOY_TRIGGER_WORKFLOWS = new Set([...deployTriggerWorkflows(), ...TYPE_INDEPENDENT_DEPLOY_WORKFLOWS]);

// Deploy trigger branch substitution: main in triggers · checkout ref · pull · run conditions
function subDeployTrigger(s, trigger) {
  s = s.replace(/^(\s*branches:\s*\[\s*["']?)main(["']?\s*\])/gm, `$1${trigger}$2`);
  s = s.replace(/^(\s*-\s*)main(\s*(?:#.*)?)$/gm, `$1${trigger}$2`);
  s = s.replace(/^(\s*ref:\s*)main(\s*(?:#.*)?)$/gm, `$1${trigger}$2`);
  s = s.replace(/\bgit pull origin main\b/g, `git pull origin ${trigger}`);
  s = s.replace(/refs\/heads\/main\b/g, `refs/heads/${trigger}`);
  s = s.replace(/"\$BRANCH" == "main"/g, `"$BRANCH" == "${trigger}"`);
  return s;
}

// Returns content with the branch settings (+ CI minutes saver) applied. Unchanged when branches is unset or standard.
// Two-stage placeholder substitution prevents value collisions (e.g. in a repo whose default branch is develop, the main→develop
// result would otherwise be caught again by the following develop→X substitution).
// filename: limits the deploy trigger substitution (#1114) to deploy workflow files. Without it, that substitution is skipped.
export function substituteBranches(content, branches = null, filename = "") {
  if (!branches) return content;
  const db = branches.defaultBranch || "main";
  const dev = branches.deployBranch || "develop";
  const trigger = branches.deployTriggerBranch || "";
  let s = String(content);
  if (branches.ciMinutesSaver) s = substituteCiMinutesSaver(s, filename);
  const T_DB = "__PJOPS_DEFAULT__";
  const T_DEV = "__PJOPS_DEPLOY__";
  const T_TRIGGER = "__PJOPS_TRIGGER__";
  // main in deploy workflows goes to the deploy trigger branch, not the default branch (moved out to a placeholder first)
  if (trigger && DEPLOY_TRIGGER_WORKFLOWS.has(filename)) s = subDeployTrigger(s, T_TRIGGER);
  if (dev !== "develop") s = subDeploy(s, T_DEV);
  if (db !== "main") s = subDefault(s, T_DB);
  return s.replaceAll(T_TRIGGER, trigger).replaceAll(T_DEV, dev).replaceAll(T_DB, db);
}
