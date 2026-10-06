// 타입별 프로젝트 경로 감지·확정 (.sh find_type_path_candidates L1249~1311 /
// resolve_project_paths L1362~1589 등가). 모노레포에서 각 타입의 버전 파일이
// 어느 폴더에 있는지 5단계 우선순위로 확정한다.
//
// io 주입 계약(readline-engine 시그니처 그대로):
//   io.select({message, options:[{value,label}]}) → value | CANCEL(symbol)
//   io.text({message, defaultValue})              → string | CANCEL
//   io.confirm({message, initialValue})           → bool | CANCEL
//   io.log(line)                                   → 안내 출력 (없으면 stderr)
import { existsSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { t as msg } from "../i18n/index.js";
import { markerForType as baseMarkerForType, extraMarkers } from "./detect.js";
import { normalizePath } from "../cli/args.js";

// 취소(ESC/Ctrl+C)는 CANCEL 심볼 — ui를 import하지 않고 심볼 여부로만 판정 (core→ui 역참조 방지)
const isCancel = (v) => typeof v === "symbol";

// 타입의 대표 마커 파일명 (.sh marker_for_type L1220~1229 등가).
// detect.js는 미지 타입에 package.json을 기본 반환하지만 .sh는 빈 문자열 — 등가를 위해 래핑.
const KNOWN_MARKER_TYPES = new Set([
  "flutter", "react", "node", "react-native", "react-native-expo", "python", "spring",
]);
export function markerForType(type) {
  return KNOWN_MARKER_TYPES.has(type) ? baseMarkerForType(type) : "";
}

// 디렉토리에 실재하는 마커 파일명 반환 — 보조 마커 포함, 없으면 대표 마커 (표시용).
// (.sh existing_marker_in_dir L1232~1245: spring build.gradle/.kts/pom.xml, python pyproject/setup.py/requirements.txt)
export function existingMarkerInDir(type, dir) {
  const primary = markerForType(type);
  const names = primary ? [primary, ...extraMarkers(type)] : [];
  for (const n of names) {
    if (existsSync(join(dir, n))) return n;
  }
  return primary;
}

// maxdepth 3 재귀 파일 탐색 — 매치 파일의 "디렉토리" 상대경로(루트는 ".")를 수집.
// find의 maxdepth는 파일 경로 컴포넌트 수 기준(./a/b/f = depth 3)이므로 동일하게 계산.
function walkFindDirs(root, { prune, match, maxDepth = 3 }) {
  const hits = [];
  const walk = (rel, depth) => {
    let entries;
    try { entries = readdirSync(join(root, rel || "."), { withFileTypes: true }); } catch { return; }
    for (const e of entries) {
      const childDepth = depth + 1;
      const childRel = rel ? `${rel}/${e.name}` : e.name;
      if (e.isDirectory()) {
        // prune 폴더는 하위 전체 제외 (.sh find -prune 등가)
        if (prune.has(e.name)) continue;
        // 자식 파일이 depth ≤ maxDepth 안에 들어올 때만 하강
        if (childDepth < maxDepth) walk(childRel, childDepth);
        // childDepth === maxDepth-0 인 디렉토리 내부 파일은 depth maxDepth+1 → find가 안 봄
        else if (childDepth === maxDepth) { /* 파일만 maxDepth까지 — 디렉토리 하강 불필요 */ }
      } else if (childDepth <= maxDepth && match(e.name)) {
        hits.push(rel === "" ? "." : rel);
      }
    }
  };
  walk("", 0);
  return [...new Set(hits)].sort(); // sort -u 등가
}

// 타입별 마커 파일 후보 검색 (.sh find_type_path_candidates L1249~1311 등가).
// 반환: 후보 디렉토리 상대경로 배열 (루트는 ".").
export function findTypePathCandidates(root, type) {
  // ── Spring 멀티모듈: settings.gradle(.kts) 폴더 = 모듈 루트로 축약 (.sh L1255~1268) ──
  // version_manager가 그 폴더 아래 build.gradle 전부를 갱신하므로 하위 모듈을 펼치지 않는다.
  // android/ 의 settings.gradle(Flutter/RN)은 spring이 아니므로 prune.
  if (type === "spring") {
    const mm = walkFindDirs(root, {
      prune: new Set(["node_modules", ".git", "build", "dist", ".gradle", "android", "ios"]),
      match: (n) => n === "settings.gradle" || n === "settings.gradle.kts",
    });
    if (mm.length) return mm;
    // settings.gradle 없음 → 단일 모듈, 아래 build.gradle 폴백
  }

  const namesByType = {
    flutter: ["pubspec.yaml"],
    react: ["package.json"], node: ["package.json"],
    "react-native": ["package.json"],
    "react-native-expo": ["app.json"],
    python: ["pyproject.toml", "setup.py", "requirements.txt"],
    spring: ["build.gradle", "build.gradle.kts", "pom.xml"],
  };
  const names = namesByType[type];
  if (!names) return [];

  const prune = new Set([
    "node_modules", ".git", "build", "dist", ".dart_tool", "android", "ios",
    ".gradle", "venv", ".venv", "__pycache__",
  ]);
  // 우선순위 높은 마커에서 발견되면 그것만 사용 (.sh L1281~1288)
  let found = [];
  for (const n of names) {
    found = walkFindDirs(root, { prune, match: (name) => name === n });
    if (found.length) break;
  }

  return found.filter((d) => {
    if (type === "flutter") {
      // example/ 제외 + lib/ 동반 확인 — 오탐 방지 (.sh L1298~1303)
      if (d.includes("example")) return false;
      const libDir = d === "." ? join(root, "lib") : join(root, d, "lib");
      if (!existsSync(libDir)) return false;
    }
    if (type === "spring") {
      // Flutter/RN의 android/build.gradle 오탐 제외 (.sh L1304~1307)
      if (d.includes("android")) return false;
    }
    return true;
  });
}

// 선택된 모든 타입의 경로를 감지·확인하여 Map<type,path> 확정
// (.sh resolve_project_paths L1362~1589 등가 — 5단계 우선순위).
//   ① paths에 이미 있음(--paths) → 유지
//   ② 루트에 마커 존재 → "." 자동
//   ③ existingPaths(version.yml 저장값)
//   ④ 후보 스캔
//   ⑤ 분기 — 비대화형: 기존값→후보1개→루트 폴백 / 대화형: 확인·선택·직접입력
export async function resolveProjectPaths({
  root, types = [], paths = new Map(), existingPaths = new Map(),
  force = false, tty = true, io = {},
}) {
  const say = io.log || ((m) => process.stderr.write(`${m}\n`));
  const result = new Map(paths); // --paths 사전값 유지 (호출부 Map은 불변)
  const targets = types.filter((t) => t !== "basic"); // basic은 경로 불필요 (.sh L1400)
  if (targets.length === 0) return result;

  const total = targets.length;
  // ── 도입부 안내 (.sh L1407~1434 — 감지 결과 + 무엇을 할지 설명) ──
  say("");
  if (total > 1) say(msg("paths.multi", { total }));
  else say(msg("paths.single", { type: targets[0] }));
  for (const t of targets) say(`   • ${t.padEnd(8)} → ${existingMarkerInDir(t, root)}`);
  say("");
  say(msg("paths.rootDef"));
  say("");

  let idx = 0;
  for (const t of targets) {
    idx += 1;
    const prog = `[${idx}/${total}]`;

    // ① --paths 등으로 이미 지정됨 → 최우선 (.sh L1441~1446)
    if (result.get(t)) {
      say(msg("paths.byFlag", { type: t, path: result.get(t) }));
      continue;
    }

    // ② 루트에 마커 존재 → "." 자동 확정 (.sh L1449~1455, 보조 마커 포함)
    const rootMarker = existingMarkerInDir(t, root);
    if (rootMarker && existsSync(join(root, rootMarker))) {
      result.set(t, ".");
      say(msg("paths.atRoot", { type: t, marker: rootMarker }));
      continue;
    }

    // ③ 기존 version.yml 저장값 → 기본 제안값 (.sh L1458~1466)
    const existing = existingPaths.get(t) || "";

    // ④ 후보 검색 (.sh L1469~1471)
    const candidates = findTypePathCandidates(root, t);
    let chosen = "";

    // ── ⑤-a 비대화형 (--force 또는 TTY 없음, .sh L1476~1489) ──
    if (force || !tty) {
      if (existing) {
        chosen = existing;
        say(msg("paths.keptSaved", { type: t, path: chosen }));
      } else if (candidates.length === 1) {
        chosen = candidates[0];
        say(msg("paths.autoDetected", { type: t, path: chosen }));
      } else {
        chosen = ".";
        say(msg("paths.ambiguous", { type: t, count: candidates.length }));
      }
      result.set(t, chosen);
      continue;
    }

    // ── ⑤-b 대화형: 후보 개수별 분기 (.sh L1492~1525) + 타입 탈출구 (#487) ──
    const EXCLUDE = "이 타입 제외"; // 센티넬 — 한국어 value로 노출 (기존 "직접 입력" 패턴)
    let excluded = false;
    if (candidates.length === 1) {
      const cand = candidates[0];
      const candMarker = existingMarkerInDir(t, cand === "." ? root : join(root, cand));
      const candFull = cand === "." ? candMarker : `${cand}/${candMarker}`;
      say("");
      say(msg("paths.found", { prog, type: t, marker: candMarker }));
      say(msg("paths.location", { file: candFull }));
      const sel = await io.select({
        message: msg("paths.confirmPrompt", { type: t, cand }),
        options: [
          { value: cand, label: msg("paths.confirmYes", { cand, file: candFull }) },
          { value: "직접 입력", label: msg("paths.confirmManual") },
          { value: EXCLUDE, label: msg("paths.exclude", { type: t }) },
        ],
      });
      if (sel === EXCLUDE) excluded = true;
      else if (!isCancel(sel) && sel != null && sel !== "직접 입력") chosen = sel;
      // ESC/직접 입력 → 아래 직접입력 루프로
    } else if (candidates.length > 1) {
      say("");
      say(msg("paths.multiFound", { prog, type: t, count: candidates.length }));
      // 후보들 + '직접 입력'/'이 타입 제외' 메뉴 — value 자체를 한국어로 (센티넬 노출 방지, .sh L1508~1521)
      const options = candidates.map((c) => ({
        value: c,
        label: `${c} (${existingMarkerInDir(t, c === "." ? root : join(root, c))})`,
      }));
      options.push({ value: "직접 입력", label: msg("paths.manual") });
      options.push({ value: EXCLUDE, label: msg("paths.exclude", { type: t }) });
      const sel = await io.select({ message: msg("paths.selectPrompt", { type: t }), options });
      // ESC(취소)도 직접 입력으로 폴백 (.sh `|| _sel="직접 입력"`)
      if (sel === EXCLUDE) excluded = true;
      else if (!isCancel(sel) && sel != null && sel !== "직접 입력") chosen = sel;
    } else {
      say("");
      say(msg("paths.notFound", { prog, type: t }));
    }

    // ── 직접 입력 루프 (위에서 미확정 시, .sh L1528~1553) — 제외 탈출구 포함 (#487) ──
    while (!chosen && !excluded) {
      const hintMarker = existingMarkerInDir(t, root);
      let prompt = msg("paths.inputPrompt", { type: t, marker: hintMarker });
      if (existing) prompt += msg("paths.inputCurrent", { value: existing });
      prompt += "): ";
      let input = await io.text({ message: prompt, defaultValue: "" });
      if (isCancel(input) || input == null) input = ""; // ESC → 빈값 (아래 폴백)
      input = String(input).trim();
      // 빈값 → 기존값 또는 루트 (.sh L1541~1543) — normalizePath 전에 판정
      input = input === "" ? (existing || ".") : normalizePath(input);
      // 검증: 입력 경로에 마커 존재 확인 (보조 마커 포함, .sh L1544~1552)
      const m = existingMarkerInDir(t, input === "." ? root : join(root, input));
      if (m && existsSync(join(root, input === "." ? "" : input, m))) {
        chosen = input;
      } else {
        say(msg("paths.missingFile", { path: input, marker: m }));
        const act = await io.select({
          message: msg("paths.actionPrompt"),
          options: [
            { value: "retry", label: msg("paths.retry") },
            { value: "force", label: msg("paths.force", { path: input }) },
            { value: EXCLUDE, label: msg("paths.exclude", { type: t }) },
          ],
        });
        if (act === "force") chosen = input;
        else if (act === EXCLUDE) excluded = true;
        // retry/ESC → 루프 계속
      }
    }

    if (excluded) {
      say(msg("paths.excluded", { type: t }));
      continue;
    }

    result.set(t, chosen);
    say(`  ✅ ${t} → ${chosen}`);
  }

  // ── 요약 + 같은 마커 파일 중복 경고 (.sh L1559~1587) ──
  say("");
  say(msg("paths.summary"));
  const fileToTypes = new Map(); // 마커 파일 상대경로 → 그 파일을 쓰는 타입들
  for (const [pt, pp] of result) {
    const m = existingMarkerInDir(pt, pp === "." ? root : join(root, pp));
    const file = pp === "." ? m : `${pp}/${m}`;
    say(`   ${pt} → ${file}`);
    if (!fileToTypes.has(file)) fileToTypes.set(file, []);
    fileToTypes.get(file).push(pt);
  }
  for (const [file, ts] of fileToTypes) {
    if (ts.length > 1) {
      // 멱등 동작이라 막지는 않고 경고만 (.sh L1577~1586)
      say(msg("paths.duplicate", { types: ts.join(" "), file }));
      say(msg("paths.duplicateNote"));
    }
  }
  say("");
  return result;
}

// 경로 단계에서 제외된 타입 반영 (#487) — basic이 아니면서 paths에 없는 타입 제거.
// 전부 제외되면 basic 폴백 (타입 0개 상태 금지). 비대화형은 제외가 불가능하므로 no-op.
export function filterExcludedTypes(types, paths) {
  const kept = types.filter((t) => t === "basic" || paths.has(t));
  return kept.length ? kept : ["basic"];
}
