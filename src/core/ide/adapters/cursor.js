// Cursor 어댑터 (.sh _manage_cursor_section / _do_cursor_skills_copy /
// _write_cursor_skills_meta / _remove_cursor_section 등가).
// 마켓플레이스 없음 → ~/.cursor/skills/ 에 skills/ 폴더를 복사하고 meta.json으로 버전 추적.
import { join } from "node:path";
import { existsSync, readFileSync, mkdirSync, cpSync, rmSync, writeFileSync, readdirSync } from "node:fs";
import { migrateConfigRoot, isLegacyVersion } from "../legacy.js";

const LEGACY_NAMES = ["cassiiopeia", "suh-devops-template"];
const LEGACY_MAX_VERSION = "4.2.4";

// 스킬을 쓰는 사람에게 필요 없는 것. projectops 자신을 검사하는 테스트다.
// skills/ 는 통째로 복사되므로 여기서 걸러내지 않으면 사용자 홈에 그대로 쌓인다.
const SKIP_IN_COPY = new Set(["conftest.py", "pytest.ini"]);
const TEST_PATH = /(^|[\\/])(tests?|__pycache__)([\\/]|$)/;

function metaPath(io) { return join(io.home(), ".cursor/skills/cursor-skills-meta.json"); }

function detect(io) {
  const mp = metaPath(io);
  if (!existsSync(mp)) return { installed: false, version: null, cliMissing: false };
  let version = null;
  try {
    const m = JSON.parse(readFileSync(mp, "utf8"));
    version = m.version || null;
  } catch { /* meta 손상 → 설치는 됐다고 봄 */ }
  return { installed: true, version, cliMissing: false };
}

function apply(io, ctx = {}) {
  migrateLegacy(io, ctx);   // 옛 이름/버전 감지 시 projectops 소유 항목 선별 삭제
  migrateConfigRoot(io);    // 공용 config 루트 이관
  const src = resolveSkillsSrc(ctx);
  if (!src) { io.log("  설치할 스킬 소스를 찾지 못했습니다 (skills/ 폴더 필요)."); return false; }
  const dest = join(io.home(), ".cursor/skills");
  io.log("Cursor Skills 복사 중...");
  try {
    mkdirSync(dest, { recursive: true });
    for (const e of readdirSync(src, { withFileTypes: true })) {
      if (SKIP_IN_COPY.has(e.name)) continue;
      cpSync(join(src, e.name), join(dest, e.name), {
        recursive: true,
        // 이 저장소 자기 코드를 검사하는 테스트는 남의 컴퓨터로 나갈 이유가 없다 (#591).
        filter: (p) => !TEST_PATH.test(p),
      });
    }
    writeMeta(io, dest, ctx.templateVersion);
    io.log(`  Cursor Skills 설치 완료 (${dest}/, v${ctx.templateVersion || "unknown"})`);
    return true;
  } catch {
    io.log("  Cursor Skills 복사 실패 — skills/ 폴더를 확인하세요.");
    return false;
  }
}

function remove(io, ctx = {}) {
  const dir = join(io.home(), ".cursor/skills");
  if (!existsSync(join(dir, "cursor-skills-meta.json"))) { io.log("  설치된 Cursor Skills가 없어 건너뜁니다"); return true; }
  try {
    for (const name of ownedEntries(io, ctx)) rmSync(join(dir, name), { recursive: true, force: true });
    // 폴더가 비면 폴더 자체 제거, 타 스킬(somansa-tools 등) 남으면 유지
    if (existsSync(dir) && readdirSync(dir).length === 0) rmSync(dir, { recursive: true, force: true });
    io.log(`  Cursor Skills 제거 완료 (projectops 소유만, ${dir}/)`);
    return true;
  } catch { io.log(`  Cursor Skills 제거 실패 — 수동 확인: ${dir}`); return false; }
}

// projectops가 이 폴더에 설치했다고 볼 항목만 골라낸다.
// 소스 skills/ 폴더명(pro-*, references, config.json.example) ∪ /^suh-/ ∪ meta 파일.
// 접두어 없는 폴더(analyze·gitlab 등 somansa-tools)는 제외 → 보존.
function ownedEntries(io, ctx) {
  const dir = join(io.home(), ".cursor/skills");
  if (!existsSync(dir)) return [];
  let srcNames = new Set();
  const src = resolveSkillsSrc(ctx);
  if (src && existsSync(src)) srcNames = new Set(readdirSync(src));
  const EXTRA = new Set(["cursor-skills-meta.json"]);
  return readdirSync(dir).filter((name) => srcNames.has(name) || /^suh-/.test(name) || EXTRA.has(name));
}

// 옛 이름/버전 meta면 projectops 소유 항목만 선별 삭제 → apply가 신규 재설치.
function migrateLegacy(io, ctx) {
  const mp = metaPath(io);
  if (!existsSync(mp)) return;
  let meta = {};
  try { meta = JSON.parse(readFileSync(mp, "utf8")); } catch { return; }
  const oldName = meta.name && LEGACY_NAMES.includes(String(meta.name).toLowerCase());
  const oldVer = isLegacyVersion(meta.version, LEGACY_MAX_VERSION);
  if (!(oldName || oldVer)) return;
  for (const name of ownedEntries(io, ctx)) {
    try { rmSync(join(io.home(), ".cursor/skills", name), { recursive: true, force: true }); } catch { /* 무시 */ }
  }
  io.log(`  레거시 Cursor Skills 정리(선별): name=${meta.name}, v=${meta.version} → 재설치`);
}

function manualHint() {
  return "  💡 Cursor: skills/ 폴더를 ~/.cursor/skills/ 로 복사하면 됩니다.";
}

// ── 헬퍼 ──
// 스킬 소스: 다운로드된 템플릿(TEMP)/skills 우선, 없으면 로컬 skills/.
function resolveSkillsSrc(ctx) {
  const cands = [ctx.sourceSkillsDir, ctx.tempDir && join(ctx.tempDir, "skills"), "skills"].filter(Boolean);
  for (const c of cands) if (existsSync(c)) return c;
  return "";
}

function writeMeta(io, destDir, templateVersion) {
  const version = templateVersion || "unknown";
  const now = new Date().toISOString().replace(/\.\d+Z$/, "Z");
  const file = join(destDir, "cursor-skills-meta.json");
  let installedAt = now;
  if (existsSync(file)) { try { installedAt = JSON.parse(readFileSync(file, "utf8")).installedAt || now; } catch { /* 무해 */ } }
  const meta = {
    name: "projectops", version, scope: "user",
    source: "https://github.com/Cassiiopeia/projectops",
    installPath: destDir, installedAt, lastUpdated: now,
  };
  mkdirSync(destDir, { recursive: true });
  writeFileSync(file, JSON.stringify(meta, null, 2) + "\n");
}

export const cursorAdapter = {
  id: "cursor", label: "Cursor", order: 20,
  detect, apply, remove, manualHint,
};
