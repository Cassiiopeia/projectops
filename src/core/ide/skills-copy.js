// 스킬 폴더 복사 공용 (Cursor·Copilot): skills/ > 홈 아래 스킬 폴더, 테스트 제외, 폐기 스킬 정리, 메타 기록
// 마켓플레이스 없이 SKILL.md 폴더를 그대로 읽는 IDE 가 같은 규칙을 쓰도록 한 곳에 둔다.
import { join } from "node:path";
import { existsSync, readFileSync, mkdirSync, cpSync, rmSync, writeFileSync, readdirSync } from "node:fs";
import { TEMPLATE_REPO_WEB_URL } from "../paths.js";

// 스킬을 쓰는 사람에게 필요 없는 것. projectops 자신을 검사하는 테스트다.
// skills/ 는 통째로 복사되므로 여기서 걸러내지 않으면 사용자 홈에 그대로 쌓인다.
export const SKIP_IN_COPY = new Set(["conftest.py", "pytest.ini"]);
export const TEST_PATH = /(^|[\\/])(tests?|__pycache__)([\\/]|$)/;
// 우리 스킬 접두사: pro- 현행, suh- 옛 이름
const OWNED_SKILL_NAME = /^(pro|suh)-/;

// 스킬 소스: 다운로드된 템플릿(TEMP)/skills 우선, 없으면 로컬 skills/
export function resolveSkillsSrc(ctx = {}) {
  const cands = [ctx.sourceSkillsDir, ctx.tempDir && join(ctx.tempDir, "skills"), "skills"].filter(Boolean);
  for (const c of cands) if (existsSync(c)) return c;
  return "";
}

// 메타 파일 > {installed, version} (손상된 메타는 설치됐다고 봄)
export function readSkillsMeta(metaFile) {
  if (!existsSync(metaFile)) return { installed: false, version: null };
  try {
    return { installed: true, version: JSON.parse(readFileSync(metaFile, "utf8")).version || null };
  } catch { return { installed: true, version: null }; }
}

/**
 * 스킬 복사: 소스 > dest (테스트 제외) > 소스에서 사라진 우리 스킬 제거
 * 폐기한 스킬 이름 목록 반환. 복사 실패는 예외로 올린다 (호출부가 로그·false 처리).
 */
export function copySkillsTree(src, dest, metaFileName) {
  mkdirSync(dest, { recursive: true });
  for (const e of readdirSync(src, { withFileTypes: true })) {
    if (SKIP_IN_COPY.has(e.name)) continue;
    cpSync(join(src, e.name), join(dest, e.name), {
      recursive: true,
      // 이 저장소 자기 코드를 검사하는 테스트는 남의 컴퓨터로 나갈 이유가 없다 (#591).
      filter: (p) => !TEST_PATH.test(p),
    });
  }
  // 복사는 overlay 라 덮어쓰기만 하면 **폐기한 스킬이 남의 컴퓨터에 영영 남아** 계속 잡힌다 (#500).
  // 남의 스킬은 접두사로 걸러 건드리지 않는다.
  const srcNames = new Set(readdirSync(src));
  const obsoleteNames = [];
  for (const name of readdirSync(dest)) {
    if (srcNames.has(name) || name === metaFileName) continue;
    if (!OWNED_SKILL_NAME.test(name)) continue;
    try {
      rmSync(join(dest, name), { recursive: true, force: true });
      obsoleteNames.push(name);
    } catch { /* 무시 — 지우지 못해도 설치는 계속한다 */ }
  }
  return obsoleteNames;
}

// projectops 가 이 폴더에 설치했다고 볼 항목: 소스 폴더명 ∪ pro-/suh- 접두사 ∪ 메타 파일
// 접두어 없는 폴더(somansa-tools 등 남의 스킬)는 제외 → 보존
export function ownedEntries(dir, ctx, metaFileName) {
  if (!existsSync(dir)) return [];
  let srcNames = new Set();
  const src = resolveSkillsSrc(ctx);
  if (src && existsSync(src)) srcNames = new Set(readdirSync(src));
  // 폐기한 스킬은 소스에 없으므로 srcNames 로는 잡히지 않는다 (#619).
  return readdirSync(dir).filter((name) => srcNames.has(name) || OWNED_SKILL_NAME.test(name) || name === metaFileName);
}

// 우리 항목만 삭제 > 폴더가 비면 폴더도 삭제 (남의 스킬이 있으면 유지). 실패는 예외로 올린다.
export function removeOwnedEntries(dir, ctx, metaFileName) {
  for (const name of ownedEntries(dir, ctx, metaFileName)) rmSync(join(dir, name), { recursive: true, force: true });
  if (existsSync(dir) && readdirSync(dir).length === 0) rmSync(dir, { recursive: true, force: true });
}

// 메타 기록: 버전 추적용 (installedAt 은 첫 설치 시각 유지)
export function writeSkillsMeta(destDir, metaFileName, templateVersion) {
  const version = templateVersion || "unknown";
  const now = new Date().toISOString().replace(/\.\d+Z$/, "Z");
  const file = join(destDir, metaFileName);
  let installedAt = now;
  if (existsSync(file)) { try { installedAt = JSON.parse(readFileSync(file, "utf8")).installedAt || now; } catch { /* 무해 */ } }
  const meta = {
    name: "projectops", version, scope: "user",
    source: TEMPLATE_REPO_WEB_URL,
    installPath: destDir, installedAt, lastUpdated: now,
  };
  mkdirSync(destDir, { recursive: true });
  writeFileSync(file, JSON.stringify(meta, null, 2) + "\n");
}
