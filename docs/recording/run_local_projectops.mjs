// 녹화용 projectops 실행: 작업 트리 CLI + 템플릿 스냅샷 (npm 배포·GitHub 다운로드 무관, #976)
// 사용: node run_local_projectops.mjs <템플릿 스냅샷 폴더> [projectops 인자...]
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
// bin/projectops.js 와 같은 종료 처리 (파이프 출력 잘림 방지)
process.stdout.write("", () => process.exit(exitCode));
