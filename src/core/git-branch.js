// Branch existence check and creation helpers (#477) — used by the wizard's offer to create the development branch.
// Every function quietly returns false/null on failure (so the wizard survives no git, no repo, or no remote).
import { execFileSync } from "node:child_process";

function git(root, args, env = undefined) {
  try {
    return execFileSync("git", args, { cwd: root, encoding: "utf8", stdio: ["ignore", "pipe", "ignore"], env }).trim();
  } catch { return null; }
}

/**
 * Environment for non-interactive remote access (#988): block credential prompts > fail at once > show manual command
 * 4 blocks: terminal prompt, askpass (GIT_/SSH_), Git Credential Manager window, ssh password prompt
 * ssh is forced to BatchMode only when there is no user-set command (GIT_SSH_COMMAND, GIT_SSH, core.sshCommand)
 */
export function nonInteractiveGitEnv(baseEnv = process.env, { hasCustomSshCommand = false } = {}) {
  const env = { ...baseEnv, GIT_TERMINAL_PROMPT: "0", GIT_ASKPASS: "", SSH_ASKPASS: "", GCM_INTERACTIVE: "never" };
  if (!hasCustomSshCommand && !baseEnv.GIT_SSH_COMMAND && !baseEnv.GIT_SSH) env.GIT_SSH_COMMAND = "ssh -o BatchMode=yes";
  return env;
}

// Remote command env: interactive inherits (undefined), non-interactive blocks prompts
function remoteEnv(root, isNonInteractive) {
  if (!isNonInteractive) return undefined;
  const hasCustomSshCommand = Boolean(git(root, ["config", "--get", "core.sshCommand"]));
  return nonInteractiveGitEnv(process.env, { hasCustomSshCommand });
}

// Branch existence state. remote is null (unknown) when the origin lookup fails (no remote, network).
export function branchStatus(root, name, { isNonInteractive = false } = {}) {
  const isRepo = git(root, ["rev-parse", "--git-dir"]) !== null;
  if (!isRepo || !name) return { isRepo, local: false, remote: null };
  const local = git(root, ["show-ref", "--verify", `refs/heads/${name}`]) !== null;
  const ls = git(root, ["ls-remote", "--heads", "origin", name], remoteEnv(root, isNonInteractive));
  const remote = ls === null ? null : ls.length > 0;
  return { isRepo, local, remote };
}

// Create a local branch from fromBranch (the default branch) — no checkout.
// If fromBranch is not local, fall back to origin/fromBranch → HEAD in that order.
export function createBranch(root, name, fromBranch = "") {
  if (fromBranch) {
    if (git(root, ["branch", name, fromBranch]) !== null) return true;
    if (git(root, ["branch", name, `origin/${fromBranch}`]) !== null) return true;
  }
  return git(root, ["branch", name]) !== null;
}

// Push a branch to the remote (origin) with -u. false on credential/network failure.
// Non-interactive fails right away without asking for credentials (#988 — asking stalls an unattended run)
export function pushBranch(root, name, { isNonInteractive = false } = {}) {
  return git(root, ["push", "-u", "origin", name], remoteEnv(root, isNonInteractive)) !== null;
}
