// workflow 카테고리 규칙 (#470) — .github/workflows/의 구 템플릿 워크플로우를 .bak으로 무해화.
// GitHub Actions는 .yaml/.yml만 실행하므로 .bak 리네임 = 즉시 무해화 + 복원 가능.
import { existsSync, readFileSync, renameSync, rmSync } from "node:fs";
import { join } from "node:path";
import { EXTRACTORS } from "./settings-extractors.js";

const WF_DIR = join(".github", "workflows");

function target(targetRoot, entry) {
  return join(targetRoot, WF_DIR, entry.file);
}

export function detect(targetRoot, entry) {
  const p = target(targetRoot, entry);
  if (!existsSync(p)) return false;
  if (entry.contentMarker) {
    try { return readFileSync(p, "utf8").includes(entry.contentMarker); }
    catch { return false; }
  }
  return true;
}

export function apply(targetRoot, entry) {
  // 무해화 전 설정 이관 (실패해도 무해화는 진행 — 부분 실패 허용 원칙)
  let carried = [];
  let carryFailed = null;
  if (entry.settingsExtractor && EXTRACTORS[entry.settingsExtractor]) {
    try { carried = EXTRACTORS[entry.settingsExtractor](targetRoot, entry).carried; }
    catch (error) { carried = []; carryFailed = error?.message || String(error); }
  }
  const src = target(targetRoot, entry);
  const bak = `${src}.bak`;
  if (existsSync(bak)) rmSync(bak, { force: true }); // Windows rename은 대상 존재 시 실패
  renameSync(src, bak);
  const result = { action: "bak", from: entry.file, to: `${entry.file}.bak` };
  if (carried.length > 0) result.carried = carried;
  if (carryFailed) result.carryFailed = carryFailed;
  return result;
}
