// Non-interactive development (release source) branch creation (#715) — only when --create-development-branch is given.
// Reuses the interactive ensureDeployBranch as "yes to every question": one code path for existence check, creation and push.
// Never throws on failure — leaves a manual command instead of failing the whole integration.
import { ensureDeployBranch } from "./options-ask.js";

// ensureDeployBranch state > 3 results (created · skipped · failed)
const STATUS_BY_STATE = {
  "exists-local": "skipped",
  "exists-remote": "skipped",
  "pushed": "created",
  "push-failed": "failed",
  "create-failed": "failed",
  "not-a-repo": "failed",
  "not-checked": "failed",
};

// Manual command per failure reason (push failure: the local branch already exists, so push only)
function manualCommandFor(state, branch, base) {
  if (state === "push-failed") return `git push -u origin ${branch}`;
  if (state === "create-failed" && base) return `git branch ${branch} ${base} && git push -u origin ${branch}`;
  return `git checkout -b ${branch} && git push -u origin ${branch}`;
}

/**
 * Check the development branch > create it from the default branch if missing > push to origin
 * Returns { status, reason, branch, base, pushed, manualCommand (on failure only) }
 */
export async function createDevelopmentBranchUnattended({ targetRoot = ".", branch = "develop", defaultBranch = "", say = () => {} }) {
  const answerYes = { confirm: async () => true };
  // Unattended run: fail instead of asking for credentials, sending it to the failed path (manual command) (#988)
  const outcome = await ensureDeployBranch({ targetRoot, deployBranch: branch, defaultBranch, io: answerYes, say, isNonInteractive: true });
  const status = STATUS_BY_STATE[outcome.state] ?? "failed";
  return {
    status,
    reason: outcome.state,
    branch,
    base: defaultBranch,
    pushed: outcome.pushed === true,
    manualCommand: status === "failed" ? manualCommandFor(outcome.state, branch, defaultBranch) : null,
  };
}

/**
 * Step wrapper: check the flag > try to create > write the run trace
 * Without the flag, creates nothing and records only why. Returns result | null (no flag)
 */
export async function runDevelopmentBranchStep({ isRequested = false, targetRoot, branch, defaultBranch, trace = null, say = () => {} }) {
  const name = branch || "develop";
  if (!isRequested) {
    trace?.event("dev-branch", "not-requested", name, { flag: "--create-development-branch", note: "left as a manual step" });
    return null;
  }
  const result = await createDevelopmentBranchUnattended({ targetRoot, branch: name, defaultBranch, say });
  // action is the result — failed shows as ERROR in the log (run-trace levelOf)
  trace?.event("dev-branch", result.status, name, {
    base: defaultBranch || null, reason: result.reason, pushed: result.pushed, manualCommand: result.manualCommand,
  });
  return result;
}
