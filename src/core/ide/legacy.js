// IDE 어댑터 공용 레거시 유틸 — 버전 판정 + config 루트 이관.
// 리브랜딩(#459) 전 설치본(cassiiopeia/SUH-DEVOPS-TEMPLATE)을 신규(projectops)로 넘길 때 공용.
import { join } from "node:path";
import { existsSync, readFileSync } from "node:fs";
import { copyFileSync } from "../fsutil.js";
import { compareCacheName } from "./util.js";

// version <= maxLegacy 이면 레거시. null/빈문자열은 판정 불가 → false(안전).
export function isLegacyVersion(version, maxLegacy) {
  if (!version || !maxLegacy) return false;
  return compareCacheName(String(version), String(maxLegacy)) <= 0;
}

// 파일이 존재하고 JSON 파싱되며 최소 1개 키가 있으면 true.
export function hasNonEmptyJson(path) {
  if (!path || !existsSync(path)) return false;
  try {
    const o = JSON.parse(readFileSync(path, "utf8"));
    return o && typeof o === "object" && Object.keys(o).length > 0;
  } catch { return false; }
}

// config 루트 이관: 타겟(~/.projectops/config/config.json)이 비었을 때만 옛 경로에서 복사.
// 옛 파일은 삭제하지 않음(민감값 보존). idempotent.
export function migrateConfigRoot(io) {
  const target = join(io.home(), ".projectops", "config", "config.json");
  if (hasNonEmptyJson(target)) return { migrated: false, reason: "target-exists" };
  const sources = [
    join(io.home(), ".suh-template", "config", "config.json"), // 2세대 우선
    join(io.home(), ".cassiiopeia", "config.json"),            // 1세대 폴백
  ];
  const src = sources.find(hasNonEmptyJson);
  if (!src) return { migrated: false, reason: "no-source" };
  try {
    copyFileSync(src, target);
    io.log(`  config 마이그레이션 완료: ${src} → ~/.projectops/config/config.json`);
    return { migrated: true, from: src };
  } catch (e) {
    io.log(`  config 마이그레이션 실패(무시): ${e.message}`);
    return { migrated: false, reason: "error" };
  }
}
