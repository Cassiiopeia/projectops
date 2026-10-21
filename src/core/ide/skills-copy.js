// 스킬 폴더 복사 공용 (Cursor·Copilot): skills/ + 공용 파이썬 scripts/ > 홈 설치 루트, 테스트 제외, 폐기 정리, 메타 기록
// 마켓플레이스 없이 SKILL.md 폴더를 그대로 읽는 IDE 가 같은 규칙을 쓰도록 한 곳에 둔다.
// 설치 모양은 플러그인 캐시와 같다: <설치 루트>/skills/pro-*/scripts/x_cli.py + <설치 루트>/scripts/common
//   (스킬 CLI bootstrap 이 x_cli.py 기준 3단계 위의 scripts/ 를 import 경로로 쓴다)
import { dirname, join, relative } from "node:path";
import { existsSync, readFileSync, mkdirSync, cpSync, rmSync, writeFileSync, readdirSync } from "node:fs";
import { TEMPLATE_REPO_WEB_URL } from "../paths.js";

// 스킬을 쓰는 사람에게 필요 없는 것. projectops 자신을 검사하는 테스트다.
// skills/ 는 통째로 복사되므로 여기서 걸러내지 않으면 사용자 홈에 그대로 쌓인다.
export const SKIP_IN_COPY = new Set(["conftest.py", "pytest.ini"]);
export const TEST_PATH = /(^|[\\/])(tests?|__pycache__)([\\/]|$)/;
// 우리 스킬 접두사: pro- 현행, suh- 옛 이름
const OWNED_SKILL_NAME = /^(pro|suh)-/;
// 공용 파이썬 패키지 표식: scripts/common/__init__.py
const SHARED_SCRIPTS_MARKER = join("common", "__init__.py");
const SHARED_SCRIPTS_DIR_NAME = "scripts";
const PYTHON_CACHE_DIR_NAME = "__pycache__";

// 스킬 소스: 다운로드된 템플릿(TEMP)/skills 우선, 없으면 로컬 skills/
export function resolveSkillsSrc(ctx = {}) {
  const cands = [ctx.sourceSkillsDir, ctx.tempDir && join(ctx.tempDir, "skills"), "skills"].filter(Boolean);
  for (const c of cands) if (existsSync(c)) return c;
  return "";
}

// 공용 파이썬 소스: 직접 지정 > 템플릿(TEMP)/scripts > 스킬 소스 옆 scripts/ (같은 레포)
export function resolveScriptsSrc(ctx = {}, skillsSrc = "") {
  const cands = [ctx.sourceScriptsDir, ctx.tempDir && join(ctx.tempDir, SHARED_SCRIPTS_DIR_NAME),
    skillsSrc && join(dirname(skillsSrc), SHARED_SCRIPTS_DIR_NAME)].filter(Boolean);
  for (const c of cands) if (existsSync(join(c, SHARED_SCRIPTS_MARKER))) return c;
  return "";
}

// 메타 파일 > {installed, version, sharedScripts} (손상된 메타는 설치됐다고 봄)
export function readSkillsMeta(metaFile) {
  if (!existsSync(metaFile)) return { installed: false, version: null, sharedScripts: [] };
  try {
    const meta = JSON.parse(readFileSync(metaFile, "utf8"));
    return { installed: true, version: meta.version || null, sharedScripts: Array.isArray(meta.sharedScripts) ? meta.sharedScripts : [] };
  } catch { return { installed: true, version: null, sharedScripts: [] }; }
}

// 소스 최상위 항목 복사 (테스트·conftest 제외). 필터는 소스 기준 상대경로로 본다 —
// 절대경로로 보면 소스가 ~/test/... 아래에 있을 때 전부 걸러진다.
function copyEntriesWithoutTests(src, dest) {
  mkdirSync(dest, { recursive: true });
  const copiedNames = [];
  for (const e of readdirSync(src, { withFileTypes: true })) {
    if (SKIP_IN_COPY.has(e.name) || TEST_PATH.test(e.name)) continue;
    cpSync(join(src, e.name), join(dest, e.name), {
      recursive: true,
      // 이 저장소 자기 코드를 검사하는 테스트는 남의 컴퓨터로 나갈 이유가 없다 (#591).
      filter: (p) => !TEST_PATH.test(relative(src, p)),
    });
    copiedNames.push(e.name);
  }
  return copiedNames;
}

/**
 * 스킬 복사: 소스 > dest (테스트 제외) > 소스에서 사라진 우리 스킬 제거
 * 폐기한 스킬 이름 목록 반환. 복사 실패는 예외로 올린다 (호출부가 로그·false 처리).
 */
export function copySkillsTree(src, dest, metaFileName) {
  copyEntriesWithoutTests(src, dest);
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

// 공용 파이썬 교체 복사: 지난 설치 항목 제거 > 소스 전체 복사 (폐기 모듈이 남지 않게). 복사한 항목 이름 반환
function replaceSharedScripts(scriptsSrc, scriptsDest, previousNames) {
  removeNamedEntries(scriptsDest, previousNames);
  return copyEntriesWithoutTests(scriptsSrc, scriptsDest);
}

// 이름 목록 + 파이썬 실행이 만든 __pycache__ 삭제 > 폴더가 비면 폴더도 삭제
function removeNamedEntries(dir, names) {
  for (const name of [...names, PYTHON_CACHE_DIR_NAME]) {
    // 메타에서 읽은 이름이라 경로 이동(../) 차단
    if (!name || name.includes("/") || name.includes("\\") || name === "..") continue;
    rmSync(join(dir, name), { recursive: true, force: true });
  }
  if (existsSync(dir) && readdirSync(dir).length === 0) rmSync(dir, { recursive: true, force: true });
}

/**
 * 홈 설치 1회: 스킬 복사 > 공용 파이썬 교체 복사 > 메타 기록
 * {obsoleteNames, hasSharedScripts} 반환. 실패는 예외로 올린다.
 */
export function installHomeSkills({ skillsSrc, scriptsSrc, skillsDest, metaFileName, templateVersion }) {
  const metaFile = join(skillsDest, metaFileName);
  const previousSharedScripts = readSkillsMeta(metaFile).sharedScripts;
  const obsoleteNames = copySkillsTree(skillsSrc, skillsDest, metaFileName);
  const scriptsDest = join(dirname(skillsDest), SHARED_SCRIPTS_DIR_NAME);
  const sharedScripts = scriptsSrc ? replaceSharedScripts(scriptsSrc, scriptsDest, previousSharedScripts) : previousSharedScripts;
  writeSkillsMeta(skillsDest, metaFileName, templateVersion, { sharedScripts });
  return { obsoleteNames, hasSharedScripts: !!scriptsSrc };
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

// 우리 항목만 삭제 (메타에 적힌 공용 파이썬 포함) > 폴더가 비면 폴더도 삭제. 실패는 예외로 올린다.
export function removeOwnedEntries(dir, ctx, metaFileName) {
  const { sharedScripts } = readSkillsMeta(join(dir, metaFileName));
  for (const name of ownedEntries(dir, ctx, metaFileName)) rmSync(join(dir, name), { recursive: true, force: true });
  if (existsSync(dir) && readdirSync(dir).length === 0) rmSync(dir, { recursive: true, force: true });
  const scriptsDest = join(dirname(dir), SHARED_SCRIPTS_DIR_NAME);
  if (sharedScripts.length && existsSync(scriptsDest)) removeNamedEntries(scriptsDest, sharedScripts);
}

// 메타 기록: 버전 추적용 (installedAt 은 첫 설치 시각 유지). extraFields: sharedScripts 등
export function writeSkillsMeta(destDir, metaFileName, templateVersion, extraFields = {}) {
  const version = templateVersion || "unknown";
  const now = new Date().toISOString().replace(/\.\d+Z$/, "Z");
  const file = join(destDir, metaFileName);
  let installedAt = now;
  if (existsSync(file)) { try { installedAt = JSON.parse(readFileSync(file, "utf8")).installedAt || now; } catch { /* 무해 */ } }
  const meta = {
    name: "projectops", version, scope: "user",
    source: TEMPLATE_REPO_WEB_URL,
    installPath: destDir, installedAt, lastUpdated: now,
    ...extraFields,
  };
  mkdirSync(destDir, { recursive: true });
  writeFileSync(file, JSON.stringify(meta, null, 2) + "\n");
}
