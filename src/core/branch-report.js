// Typed branch values the run could not apply (#1248) — the run summary lists each with its reason instead of
// silently keeping the old branch. Reasons 4: version-yml-missing, missing-on-remote, not-pushed, kept-user-modified
import { branchStatus } from "./git-branch.js";

// notInstalled reason for workflows that run only on the development branch (copy/workflows.js skipNew)
const DEVELOPMENT_ONLY_REASON = "no-dev-branch";

/**
 * Typed branches (development, deploy trigger) > entries not applied in this run
 * workflowsResult: copyWorkflows counters (skippedConflicts, notInstalled)
 * isBranchRecorded: false = values given but version.yml missing (workflows mode)
 * Returns [{ kind: development|deploy-trigger|workflow-files, branch, reason, files[] }]
 */
export function listUnappliedBranchValues({
  targetRoot = ".", defaultBranch = "", deployBranch = "", deployTriggerBranch = "",
  workflowsResult = null, isBranchRecorded = true, isNonInteractive = false, trace = null,
}) {
  const typedBranches = [];
  if (deployBranch && deployBranch !== defaultBranch) typedBranches.push({ kind: "development", branch: deployBranch });
  if (deployTriggerBranch && deployTriggerBranch !== defaultBranch) typedBranches.push({ kind: "deploy-trigger", branch: deployTriggerBranch });
  const entries = [];

  // Nowhere to record (workflows mode without version.yml)
  if (!isBranchRecorded) {
    for (const typed of typedBranches) entries.push({ ...typed, reason: "version-yml-missing", files: [] });
  }

  // Branch missing on origin (remote null = could not check > not reported)
  for (const typed of typedBranches) {
    const status = branchStatus(targetRoot, typed.branch, { isNonInteractive });
    if (!status.isRepo || status.remote !== false) continue;
    const files = typed.kind === "development"
      ? (workflowsResult?.notInstalled ?? []).filter((n) => n.reason === DEVELOPMENT_ONLY_REASON).map((n) => n.filename)
      : [];
    entries.push({ ...typed, reason: status.local ? "not-pushed" : "missing-on-remote", files });
  }

  // Kept user-modified workflows that still name the old branch
  const keptFiles = (workflowsResult?.skippedConflicts ?? []).filter((k) => k.branchLineCount > 0).map((k) => k.filename);
  if (keptFiles.length) {
    const branch = [deployBranch, deployTriggerBranch].filter(Boolean).join(", ") || defaultBranch;
    entries.push({ kind: "workflow-files", branch, reason: "kept-user-modified", files: keptFiles });
  }

  for (const entry of entries) {
    trace?.event("branch", "not-applied", entry.branch, { kind: entry.kind, reason: entry.reason, files: entry.files });
  }
  return entries;
}
