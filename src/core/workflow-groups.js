// The single place that decides whether optional workflow groups are on or off (#851).
//
// Copy (copy/workflows.js), the conflict list (listWorkflowConflicts) and orphan detection (orphan-workflows.js) share these conditions.
// Keeping separate copies means fixing only one, giving "turned on but not installed" or "turned off but still runs" (#567).
// Add one line here for each new conditional folder. All three places follow.
import { readdirSync } from "node:fs";
import { join } from "node:path";
import { exists } from "./fsutil.js";

// Server deploy (<type>/server-deploy/) is installed only for docker-ssh (#439)
export const SERVER_DEPLOY_DIR = "server-deploy";
export function serverDeployEnabled(deployTarget) {
  return (deployTarget || "docker-ssh") === "docker-ssh";
}

// Optional folders under common/. Order is copy order (do not change the order shown in logs and summaries).
//   policy: "bak-replace" — if different from the template, keep a .bak and replace
//           "new-only"    — leave alone if it already exists (secret-backup: users edit the server path)
//   copyLabel / orphanLabel — trace group name and orphan notice name. Keep them as in existing logs.
export function commonOptionalGroups(commonDir, opts = {}) {
  const { includeSecretBackup = false, aiPrSummary = true, projectsSync = true, deployTarget = "docker-ssh" } = opts;
  const selectedDeploy = deployTarget || "docker-ssh";
  const groups = [];

  // deploy/<target> — type-independent deploy targets (vercel, etc.). Only the chosen target folder is on.
  const deployRoot = join(commonDir, "deploy");
  const deployNames = exists(deployRoot)
    ? readdirSync(deployRoot, { withFileTypes: true }).filter((e) => e.isDirectory()).map((e) => e.name)
    : [];
  if (!deployNames.includes(selectedDeploy)) deployNames.push(selectedDeploy); // A missing folder is filtered out below by exists
  for (const name of deployNames) {
    groups.push({ dir: join("deploy", name), enabled: name === selectedDeploy, policy: "bak-replace",
      copyLabel: "common-deploy", orphanLabel: `deploy/${name}` });
  }
  groups.push(
    // #566 — AI change summary. Works with no setup
    { dir: "pr-summary", enabled: aiPrSummary === true, policy: "bak-replace", copyLabel: "pr-summary", orphanLabel: "pr-summary" },
    // #716 — Projects board sync. Needs secrets and variables, so off by default for new installs
    { dir: "projects-sync", enabled: projectsSync === true, policy: "bak-replace", copyLabel: "projects-sync", orphanLabel: "projects-sync" },
    // Secret server backup
    { dir: "secret-backup", enabled: includeSecretBackup === true, policy: "new-only", copyLabel: "secret-backup", orphanLabel: "secret-backup" },
  );
  return groups;
}
