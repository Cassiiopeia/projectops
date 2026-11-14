// Install stable entry points: ~/.projectops/bin/{projectops_cli.py, launch_cli.py} (#942·#897)
// SKILL.md calls these entry points first. The Python side installs them only after a CLI runs once, so
// home-copy installs (Cursor, Copilot) lay them down at install time so the first call finds its way (#200).
// Same rule as Python refresh_stable_entrypoint: overwrite only when the source RESOLVER_REVISION is higher than the installed one.
import { join } from "node:path";
import { existsSync, readFileSync, mkdirSync, writeFileSync, chmodSync, renameSync } from "node:fs";

const REVISION_PATTERN = /^RESOLVER_REVISION = (\d+)/m;
// Entry point permissions: directly executable (rwxr-xr-x)
const STABLE_ENTRYPOINT_MODE = 0o755;
// 2 entry points: (install name, source path computation)
const STABLE_ENTRYPOINTS = [
  { name: "projectops_cli.py", source: ({ scriptsSrc }) => scriptsSrc && join(scriptsSrc, "projectops_cli.py") },
  { name: "launch_cli.py", source: ({ skillsSrc }) => skillsSrc && join(skillsSrc, "pro-launch", "scripts", "launch_resolver.py") },
];

// File > content revision (-1 if missing or unreadable)
function readRevision(file) {
  try {
    const match = REVISION_PATTERN.exec(readFileSync(file, "utf8"));
    return match ? Number(match[1]) : -1;
  } catch { return -1; }
}

/**
 * Refresh entry points: only when source revision > installed revision: temp file > permissions > replace
 * Returns the names of replaced entry points. Failures are thrown.
 */
export function refreshStableEntrypoints(projectopsHome, sources) {
  const binDir = join(projectopsHome, "bin");
  const updatedNames = [];
  for (const entry of STABLE_ENTRYPOINTS) {
    const sourceFile = entry.source(sources);
    if (!sourceFile || !existsSync(sourceFile)) continue;
    const target = join(binDir, entry.name);
    if (readRevision(sourceFile) <= readRevision(target)) continue;
    mkdirSync(binDir, { recursive: true });
    // So another session reading at the same time never sees a half-written file
    const temporary = `${target}.${process.pid}.tmp`;
    writeFileSync(temporary, readFileSync(sourceFile, "utf8"));
    chmodSync(temporary, STABLE_ENTRYPOINT_MODE);
    renameSync(temporary, target);
    updatedNames.push(entry.name);
  }
  return updatedNames;
}

// projectops home: the io value if given (test isolation), else ~/.projectops
export function projectopsHomeOf(io) {
  return typeof io.projectopsHome === "function" ? io.projectopsHome() : join(io.home(), ".projectops");
}
