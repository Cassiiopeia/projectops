// projectops run for recordings: working-tree CLI + template snapshot (independent of npm publish and GitHub download, #976)
// Usage: node run_local_projectops.mjs <template snapshot folder> [projectops args...]
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const repoRoot = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const [templateDir, ...projectopsArgs] = process.argv.slice(2);
if (!templateDir) {
  console.error("usage: node run_local_projectops.mjs <template-dir> [projectops args...]");
  process.exit(2);
}

const { run } = await import(pathToFileURL(join(repoRoot, "src", "index.js")).href);
const exitCode = await run(projectopsArgs, { cwd: process.cwd(), source: { type: "local", path: templateDir } });
// Same exit handling as bin/projectops.js (prevents truncated piped output)
process.stdout.write("", () => process.exit(exitCode));
