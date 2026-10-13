#!/usr/bin/env node
// projectops CLI 엔트리 — argv를 src/index.js의 run()에 넘긴다.
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { pathToFileURL } from "node:url";

const [nodeMajor, nodeMinor] = process.versions.node.split(".").map(Number);
if (nodeMajor < 20 || (nodeMajor === 20 && nodeMinor < 12)) {
  console.error(`Node.js 20.12 이상이 필요합니다 (현재: ${process.versions.node})`);
  process.exit(1);
}

const here = dirname(fileURLToPath(import.meta.url));
const indexPath = join(here, "..", "src", "index.js");
const { run } = await import(pathToFileURL(indexPath).href);

const code = await run(process.argv.slice(2), { cwd: process.cwd() });
// stdout 이 파이프면 쓰기가 비동기라, 바로 exit 하면 큰 출력(--mode options --json)이 8KB 근처에서 잘린다.
// 빈 write 의 콜백은 앞선 쓰기가 모두 넘겨진 뒤에 불리므로, 거기서 종료한다.
process.stdout.write("", () => process.exit(code));
