// Branch-only diff check (#1248) — tells "the user edited this workflow" apart from "only the branch names changed".
// A kept user-modified workflow whose sole difference from the incoming render is branch names would leave the
// release pipeline on the old branch (e.g. head.ref == 'main'), so the copy engine applies those files instead of skipping.
import { readDevelopmentBranch } from "./version-yml.js";

const BRANCH_PLACEHOLDER = "__PJOPS_BRANCH__";
// Branch name boundaries: letters, digits, `_`, `.`, `-` glue a name to its neighbors; `/` may precede it (refs/heads/main)
const NAME_BEFORE = "(?<![A-Za-z0-9_.-])";
const NAME_AFTER = "(?![A-Za-z0-9_/-])";

const escapeRegExp = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/**
 * Branch names a workflow line may mention: standard pair + this run's values + values recorded before this run
 * previousYml: version.yml text before this run (old default/development/deploy trigger branch)
 */
export function collectBranchNames(branches = {}, previousYml = "") {
  const names = new Set(["main", "develop"]);
  for (const v of [branches.defaultBranch, branches.deployBranch, branches.deployTriggerBranch]) if (v) names.add(v);
  const text = String(previousYml || "");
  const defaultMatch = text.match(/^\s*default_branch:\s*"([^"]+)"/m);
  if (defaultMatch) names.add(defaultMatch[1]);
  const developmentBranch = readDevelopmentBranch(text);
  if (developmentBranch) names.add(developmentBranch);
  const triggerMatch = text.match(/^\s*deploy_trigger_branch:\s*"([^"]+)"/m);
  if (triggerMatch) names.add(triggerMatch[1]);
  return [...names];
}

// One line with every branch name masked (longest first, so `main-v2` is not split into `main` + `-v2`)
function maskBranchNames(line, branchNames) {
  let out = line;
  for (const name of [...branchNames].sort((a, b) => b.length - a.length)) {
    out = out.replace(new RegExp(`${NAME_BEFORE}${escapeRegExp(name)}${NAME_AFTER}`, "g"), BRANCH_PLACEHOLDER);
  }
  return out;
}

/**
 * installed <-> incoming line comparison with branch names masked
 * Returns { isBranchOnly, branchLineCount }
 *   isBranchOnly    : same line count, at least one differing line, every differing line equal once masked
 *   branchLineCount : incoming lines absent from installed whose masked form exists in installed (= same line, other branch)
 */
export function compareBranchLines(installed, incoming, branchNames) {
  const installedLines = String(installed).split(/\r?\n/);
  const incomingLines = String(incoming).split(/\r?\n/);

  // Lines the typed branch did not reach (any line count — counted by masked lookup)
  const installedSet = new Set(installedLines);
  const installedMasked = new Set(installedLines.map((l) => maskBranchNames(l, branchNames)));
  let branchLineCount = 0;
  for (const line of incomingLines) {
    if (installedSet.has(line)) continue;
    if (installedMasked.has(maskBranchNames(line, branchNames))) branchLineCount++;
  }

  // Branch-only: aligned line pairs, every difference disappears once masked
  let isBranchOnly = installedLines.length === incomingLines.length;
  let differingLineCount = 0;
  for (let i = 0; isBranchOnly && i < incomingLines.length; i++) {
    if (installedLines[i] === incomingLines[i]) continue;
    differingLineCount++;
    if (maskBranchNames(installedLines[i], branchNames) !== maskBranchNames(incomingLines[i], branchNames)) isBranchOnly = false;
  }
  return { isBranchOnly: isBranchOnly && differingLineCount > 0, branchLineCount };
}
