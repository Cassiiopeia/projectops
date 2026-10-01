// 템플릿 자산 획득 + 제외 적용 (.sh download_template 등가) — template_integrator.sh 2064~2141.
import { execFileSync } from "node:child_process";
import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { exists, readText, copyDirSync, remove } from "./fsutil.js";
import { DOCS_TO_REMOVE, PLUGIN_ITEMS_TO_REMOVE } from "./exclusions.js";
import { DEFAULT_VERSION } from "../context.js";
import { TEMPLATE_REPO } from "./paths.js";

// 템플릿을 tempDir로 획득한다.
// source:
//   {type:'git', repo?}   → git clone --depth 1 (기본 repo=TEMPLATE_REPO)
//   {type:'local', path}  → 로컬 트리 복사 (네트워크 없는 등가 검증용)
// 이미 tempDir/.github 있으면 스킵(.sh 중복 호출 방지). 획득 후 applyExclusions 자동 호출.
export function acquireTemplate({ tempDir, source = { type: "git" } }) {
  if (exists(join(tempDir, ".github"))) {
    applyExclusions(tempDir);
    return;
  }
  remove(tempDir);
  if (source.type === "local") {
    copyDirSync(source.path, tempDir);
  } else {
    const repo = source.repo || TEMPLATE_REPO;
    // clone 은 stdio 를 버려 실패 원인이 사라진다 — 폴더가 읽기 전용이어도 "내려받지 못했다"로 오도되므로
    // 먼저 만들어 권한 오류(EACCES/EPERM/EROFS)를 그대로 올린다 (#720). 빈 폴더에는 clone 이 가능하다.
    mkdirSync(tempDir, { recursive: true });
    execFileSync("git", ["clone", "--depth", "1", "--quiet", repo, tempDir], { stdio: "ignore" });
  }
  applyExclusions(tempDir);
}

// DOCS_TO_REMOVE + PLUGIN_ITEMS_TO_REMOVE 삭제. skills/ 는 보존(.sh 주석).
export function applyExclusions(tempDir) {
  for (const doc of DOCS_TO_REMOVE) remove(join(tempDir, doc));
  for (const item of PLUGIN_ITEMS_TO_REMOVE) remove(join(tempDir, item));
}

// tempDir/version.yml 의 ^version: 값. 없으면 DEFAULT_VERSION.
export function readTemplateVersion(tempDir) {
  const p = join(tempDir, "version.yml");
  if (!exists(p)) return DEFAULT_VERSION;
  for (const line of readText(p).split("\n")) {
    const m = line.match(/^version:\s*["']?([^"'\s]+)["']?/);
    if (m) return m[1];
  }
  return DEFAULT_VERSION;
}
