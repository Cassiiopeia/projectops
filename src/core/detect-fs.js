// 실 파일시스템 프로젝트 감지 (.sh detect_* 실행부 등가).
// SP2-A detect.js 순수 함수를 fs/git으로 구동한다.
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { join, basename } from "node:path";
import { execFileSync } from "node:child_process";
import { detectTypesFromMarkers, detectVersionFromFiles, suggestTypesByExtScan } from "./detect.js";
import { parseExisting, convertLegacySingularType } from "./version-yml.js";
import { VALID_TYPES } from "../context.js";

const hasFile = (root) => (rel) => existsSync(join(root, rel));
const readFile = (root) => (rel) => {
  try { return readFileSync(join(root, rel), "utf8"); } catch { return null; }
};

function gitOut(root, args) {
  try {
    return execFileSync("git", args, { cwd: root, encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }).trim();
  } catch { return ""; }
}

// 확장자 스캔용 파일 목록 (.sh suggest_types_by_scan find 등가 — depth≤3, vendor 폴더 프루닝).
const SCAN_PRUNE = new Set([
  "node_modules", ".git", "build", "dist", ".dart_tool",
  "android", "ios", ".gradle", "venv", ".venv", "__pycache__",
  // 템플릿이 스스로 설치하는 .github/scripts/*.py 가 python 으로 오탐되지 않게 한다 (#671)
  ".github",
]);
export function listScanFiles(root, maxDepth = 3) {
  const files = [];
  const walk = (rel, depth) => {
    if (depth > maxDepth) return;
    let entries;
    try { entries = readdirSync(join(root, rel), { withFileTypes: true }); } catch { return; }
    for (const e of entries) {
      const childRel = rel ? `${rel}/${e.name}` : e.name;
      if (e.isDirectory()) {
        if (!SCAN_PRUNE.has(e.name)) walk(childRel, depth + 1);
      } else {
        files.push(childRel);
      }
    }
  };
  walk("", 1);
  return files;
}

// 타입 감지 — version.yml의 project_types 최우선(source of truth), 없으면 마커 스캔.
// 마커도 전혀 없으면(basic 폴백) 확장자 빈도 스캔으로 2차 추천 (.sh suggest_types_by_scan 등가, #458).
export function detectTypes(root) {
  const vy = join(root, "version.yml");
  if (existsSync(vy)) {
    const { types } = parseExisting(readFileSync(vy, "utf8"));
    if (types.length) return types; // basic 포함, 명시돼 있으면 그대로
    // v4.1.0 이전 단수 project_type 키 (#718) — 마커가 없어도 명시된 값을 복원한다.
    // 안 그러면 마커 없는 저장소가 basic 으로 떨어져 기존 타입의 워크플로우가 고아가 된다.
    const legacy = (convertLegacySingularType(readFileSync(vy, "utf8")) || "").match(/^project_types: \["([a-z-]+)"\]/m);
    if (legacy && VALID_TYPES.includes(legacy[1])) return [legacy[1]];
  }
  const byMarkers = detectTypesFromMarkers({ has: hasFile(root), read: readFile(root) });
  if (byMarkers.length === 1 && byMarkers[0] === "basic") {
    const scanned = suggestTypesByExtScan(listScanFiles(root));
    if (scanned.length) return scanned; // 추천값 — 마법사 확인/수정 루프에서 사용자가 확정
  }
  return byMarkers;
}

// 버전 감지 — .sh detect_version 순서. jq 유무는 command 존재로 판정.
export function detectVersion(root, { hasJq } = {}) {
  const read = readFile(root);
  const readJson = (rel) => { const c = read(rel); try { return c ? JSON.parse(c) : null; } catch { return null; } };
  const jq = hasJq ?? hasCommand("jq");
  const gitTag = gitOut(root, ["describe", "--tags", "--abbrev=0"]);
  return detectVersionFromFiles({ read, readJson, hasJq: jq, gitTag });
}

// 기본 브랜치 감지 — symbolic-ref → remote show → main.
export function detectDefaultBranch(root) {
  let b = gitOut(root, ["symbolic-ref", "refs/remotes/origin/HEAD"]);
  if (b) return b.replace(/^refs\/remotes\/origin\//, "");
  const show = gitOut(root, ["remote", "show", "origin"]);
  const m = show.match(/HEAD branch:\s*(\S+)/);
  if (m) return m[1];
  // origin 없는 로컬 레포(#477) — 현재 HEAD 브랜치가 최선의 추정 (대화형 수정 메뉴로 교정 가능)
  const head = gitOut(root, ["branch", "--show-current"]);
  if (head) return head;
  return "main";
}

// 레포명 — git remote get-url origin 마지막 세그먼트, 실패 시 폴더명.
export function detectRepoName(root) {
  const url = gitOut(root, ["remote", "get-url", "origin"]);
  if (url) {
    const seg = url.replace(/\.git$/, "").split(/[/:]/).pop();
    if (seg) return seg;
  }
  return basename(root);
}

function hasCommand(cmd) {
  try {
    execFileSync(process.platform === "win32" ? "where" : "which", [cmd], { stdio: "ignore" });
    return true;
  } catch { return false; }
}

// Spring application*.yml 탐색 (.sh resolve_spring_app_yml_dir/path L2767~2780 등가)
// find {base} -path "*/src/main/resources/application*.yml" | head -1 의 fs 재귀 구현.
// 반환: root 기준 상대경로 (예: "server/src/main/resources/application.yml") 또는 "".
export function findSpringAppYml(root, base = ".") {
  const startRel = base === "." ? "" : base;
  const PRUNE = new Set(["node_modules", ".git", "build", ".gradle", "target", ".idea"]);
  let hit = "";
  const walk = (rel, depth) => {
    if (hit || depth > 8) return; // head -1 등가 — 첫 매치에서 중단
    let entries;
    try { entries = readdirSync(join(root, rel), { withFileTypes: true }); } catch { return; }
    // 정렬로 순회 순서 결정화 (find 순서 플랫폼 편차 제거)
    for (const e of entries.sort((a, b) => a.name.localeCompare(b.name))) {
      if (hit) return;
      const childRel = rel ? `${rel}/${e.name}` : e.name;
      if (e.isDirectory()) {
        if (PRUNE.has(e.name)) continue;
        walk(childRel, depth + 1);
      } else if (/^application.*\.yml$/.test(e.name) && childRel.includes("src/main/resources/")) {
        hit = childRel;
      }
    }
  };
  walk(startRel, 0);
  return hit;
}

// 실 resolver 세트 생성 (.sh resolve_token 4종 등가) — index/interactive 공용.
// paths: Map<type, path> (모노레포 경로).
export function makeResolvers(root, repoName, paths) {
  const springBase = (t) => paths.get(t || "spring") || paths.get("spring") || ".";
  return {
    repo: () => repoName,
    "spring-app-yml-dir": (t) => {
      const f = findSpringAppYml(root, springBase(t));
      return f ? f.split("/").slice(0, -1).join("/") : "";
    },
    "spring-app-yml-path": (t) => findSpringAppYml(root, springBase(t)) || "",
    "flutter-root": () => paths.get("flutter") || ".",
  };
}
