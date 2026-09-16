// 고아 타입 워크플로우 감지·정리 (#487) — 타입 변경으로 선택에서 빠진 타입의
// 템플릿 워크플로우를 감지해 .bak 무해화한다 (레거시 마이그레이션과 동일 방식).
// 안전 원칙: 템플릿 인벤토리와 "정확한 파일명 일치"만 대상 — prefix 매칭 금지
// (사용자 커스텀 워크플로우 오살 방지). common/은 타입이 아니므로 순회에서 제외.
import { existsSync, renameSync, rmSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { PATHS } from "./paths.js";
import { exists, listYamlFiles } from "./fsutil.js";

// 템플릿의 project-types/<type>/ 인벤토리 — 직하위 + server-deploy/ + publish/*/ (copy 엔진과 동일 범위)
function typeInventory(projectTypesDir, type) {
  const typeDir = join(projectTypesDir, type);
  const dirs = [typeDir, join(typeDir, "server-deploy")];
  const pubRoot = join(typeDir, "publish");
  if (exists(pubRoot)) {
    for (const e of readdirSync(pubRoot, { withFileTypes: true })) {
      if (e.isDirectory()) dirs.push(join(pubRoot, e.name));
    }
  }
  const files = new Set();
  for (const d of dirs) {
    if (!exists(d)) continue;
    for (const f of listYamlFiles(d)) files.add(f);
  }
  return files;
}

// common/ 아래 "선택했을 때만 복사되는" 폴더들 (#566).
// 켜면 복사 엔진이 넣어주지만, 끄면 이미 있던 파일이 그대로 남아 계속 실행됐다.
// 축을 끈 사용자에게는 그게 곧 "껐는데 왜 도나"가 된다 — 여기서 고아로 잡는다.
// deploy는 타겟별 폴더라 선택된 타겟만 살리고 나머지를 대상으로 삼는다.
function commonOptionalOrphans(commonDir, opts) {
  const { includeSecretBackup = false, aiPrSummary = true, deployTarget = "docker-ssh" } = opts;
  const out = [];

  const gated = [
    ["secret-backup", includeSecretBackup, "secret-backup"],
    ["pr-summary", aiPrSummary, "pr-summary"],
  ];
  for (const [dir, enabled, label] of gated) {
    if (enabled) continue;
    const d = join(commonDir, dir);
    if (!exists(d)) continue;
    for (const f of listYamlFiles(d)) out.push({ filename: f, type: label });
  }

  // deploy/<target> — 선택된 타겟 외 폴더는 전부 고아 후보
  const deployRoot = join(commonDir, "deploy");
  if (exists(deployRoot)) {
    for (const e of readdirSync(deployRoot, { withFileTypes: true })) {
      if (!e.isDirectory() || e.name === deployTarget) continue;
      for (const f of listYamlFiles(join(deployRoot, e.name))) out.push({ filename: f, type: `deploy/${e.name}` });
    }
  }
  return out;
}

// 선택 안 된 타입·옵션의 템플릿 워크플로우가 대상 레포에 실재하면 고아로 반환.
export function detectOrphanWorkflows({ tempDir, targetRoot = ".", selectedTypes = [], options = null }) {
  const projectTypesDir = join(tempDir, PATHS.workflowsDir, PATHS.projectTypesDir);
  if (!exists(projectTypesDir)) return [];
  const selected = new Set(selectedTypes);
  // 선택된 타입이 쓰는 파일명 집합 — 교차 방어 (파일명은 타입 prefix로 유일하지만 안전망)
  const keep = new Set();
  for (const t of selected) for (const f of typeInventory(projectTypesDir, t)) keep.add(f);
  const workflowsDir = join(targetRoot, PATHS.workflowsDir);
  const orphans = [];
  for (const e of readdirSync(projectTypesDir, { withFileTypes: true })) {
    if (!e.isDirectory() || e.name === "common" || selected.has(e.name)) continue;
    for (const f of typeInventory(projectTypesDir, e.name)) {
      if (keep.has(f)) continue;
      if (existsSync(join(workflowsDir, f))) orphans.push({ filename: f, type: e.name });
    }
  }
  // common의 조건부 폴더 — options를 준 호출부에서만 검사한다(구 호출부 동작 보존).
  if (options) {
    const commonDir = join(projectTypesDir, "common");
    for (const o of commonOptionalOrphans(commonDir, options)) {
      if (keep.has(o.filename)) continue;
      if (existsSync(join(workflowsDir, o.filename))) orphans.push(o);
    }
  }
  return orphans.sort((a, b) => a.filename.localeCompare(b.filename));
}

// .bak 무해화 실행기 — 부분 실패 허용 (migrations applySafeMigrations와 동일 원칙).
export function applyOrphanCleanup(targetRoot, orphans) {
  const workflowsDir = join(targetRoot, PATHS.workflowsDir);
  const results = [];
  for (const { filename } of orphans) {
    try {
      const src = join(workflowsDir, filename);
      const bak = `${src}.bak`;
      if (existsSync(bak)) rmSync(bak, { force: true }); // Windows rename은 대상 존재 시 실패
      renameSync(src, bak);
      results.push({ filename, action: "bak" });
    } catch (err) {
      results.push({ filename, action: "error", error: err.message });
    }
  }
  return results;
}
