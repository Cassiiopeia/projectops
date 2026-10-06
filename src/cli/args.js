// CLI 인자 파싱 (.sh top-level while-case 등가) — template_integrator.sh 842~920.
import { existsSync, statSync, realpathSync } from "node:fs";
import { join, relative, isAbsolute } from "node:path";
import { VALID_TYPES } from "../context.js";
import { SUPPORTED_LANGS, t } from "../i18n/index.js";

export const DEPLOY_TARGETS = ["docker-ssh", "vercel", "none"];
export const PUBLISH_TARGETS = ["nexus", "npm", "github-packages"];
export const LABEL_STYLE_VALUES = ["en", "ko"];
export const INTENT_VALUES = ["app", "library", "both", "none", "manual"];
const SEMVER_RE = /^\d+\.\d+\.\d+$/;
// 유니코드 글자·숫자 허용 (#719) — 공백·셸 메타문자는 문자 클래스에 없어 그대로 거부된다.
const BRANCH_RE = /^[\p{L}\p{N}][\p{L}\p{N}._/-]*$/u;
// 허용 실행 모드 (#665) — 오타가 조용히 "복사 0건 성공"으로 끝나지 않게 한다.
export const MODE_VALUES = ["full", "version", "workflows", "issues", "skills", "doctor", "interactive"];

// argv(process.argv.slice(2)) → 파싱 결과. 오류 시 throw(호출부에서 exit 1).
export function parseArgs(argv) {
  const result = {
    mode: "interactive",
    version: "",             // 통합 대상 프로젝트의 초기 버전 (--project-version)
    types: [],
    primaryType: "",
    deployTarget: null,      // 배포 축 (#439): docker-ssh|vercel|none, null=미설정
    publishTargets: null,    // publish 축 (#439): 타겟 배열, null=미설정
    deployBranch: "",        // 릴리스 PR head 브랜치 (#456): --deploy-branch, 빈 값=미지정
    labelStyle: null,        // 상태 라벨 표기 (#776): --label-style en|ko
    intent: null,            // 프로젝트 성격 (#485): --intent app|library|both|none|manual, null=미설정(역추론)
    includeSecretBackup: null,
    aiPrSummary: null,   // #566 — AI 변경 요약 워크플로우 포함 여부
    projectsSync: null,  // #716 — Projects 보드 동기화 워크플로우 포함 여부 (null=미지정)
    pathsCsv: "",            // "flutter=app,react=client" 원문 (정규화는 resolve 단계)
    force: false,
    lang: null,              // --lang en|ko (null = decided by src/i18n resolveLang)
    help: false,
    showVersion: false,      // -v/--version → projectops 패키지 버전 출력 (npm 관례)
  };
  const args = [...argv];
  while (args.length > 0) {
    const a = args.shift();
    switch (a) {
      case "-m": case "--mode":
      {
        const v = (args.shift() ?? "").trim();
        if (!MODE_VALUES.includes(v)) {
          throw new CliError(t("args.mode", { values: MODE_VALUES.join(" | "), v }));
        }
        result.mode = v;
        break;
      }
      case "-v": case "--version":
        // npm 관례: -v/--version 은 패키지 버전 출력. (초기 버전 지정은 --project-version)
        result.showVersion = true; break;
      case "--project-version":
      {
        // version.yml·셸 스크립트가 그대로 읽는 값이라 x.y.z 외에는 받지 않는다 (#676)
        // 'v1.0.0'은 사용자가 흔히 쓰는 표기라 거부하지 않고 접두사만 떼어 받는다
        const v = (args.shift() ?? "").trim().replace(/^[vV](?=\d)/, "");
        if (!SEMVER_RE.test(v)) {
          throw new CliError(t("args.projectVersion", { v }));
        }
        result.version = v;
        break;
      }
      case "-t": case "--type": {
        const csv = args.shift() ?? "";
        const seen = new Set();
        const types = [];
        for (let ty of csv.split(",")) {
          ty = ty.replace(/\s/g, "");
          if (ty === "") continue;
          if (seen.has(ty)) continue;         // dedup
          if (!VALID_TYPES.includes(ty)) {
            throw new CliError(t("args.unsupportedType", { type: ty, valid: VALID_TYPES.join(" ") }));
          }
          seen.add(ty);
          types.push(ty);
        }
        if (types.length === 0) throw new CliError(t("args.typeEmpty"));
        result.types = types;
        result.primaryType = types[0];
        break;
      }
      case "--force": case "-y": case "--yes": result.force = true; break;
      case "--lang": {
        const v = (args.shift() ?? "").trim().toLowerCase();
        if (!SUPPORTED_LANGS.includes(v)) {
          throw new CliError(t("cli.langInvalid", { values: SUPPORTED_LANGS.join(" | "), value: v }));
        }
        result.lang = v;
        break;
      }
      case "--deploy": {
        const v = args.shift() ?? "";
        if (!DEPLOY_TARGETS.includes(v)) {
          throw new CliError(t("args.deploy", { values: DEPLOY_TARGETS.join(" | "), v }));
        }
        result.deployTarget = v;
        break;
      }
      case "--publish": {
        const csv = args.shift() ?? "";
        const targets = [];
        for (let pt of csv.split(",")) {
          pt = pt.replace(/\s/g, "");
          if (pt === "") continue;
          if (!PUBLISH_TARGETS.includes(pt)) {
            throw new CliError(t("args.publish", { values: PUBLISH_TARGETS.join(" | "), v: pt }));
          }
          if (!targets.includes(pt)) targets.push(pt);
        }
        result.publishTargets = targets;
        break;
      }
      case "--deploy-branch": {
        // 릴리스 PR head 브랜치 (#456). default_branch와 별개.
        const v = (args.shift() ?? "").trim();
        // 워크플로우 yaml·셸에 그대로 삽입되므로 안전한 브랜치명만 허용 (#676)
        if (v && (!BRANCH_RE.test(v) || v.includes("..") || v.endsWith("/") || v.endsWith(".lock"))) {
          throw new CliError(t("args.deployBranch", { v }));
        }
        if (v) result.deployBranch = v;
        break;
      }
      case "--intent": {
        // 프로젝트 성격 (#485). 미지정이면 --deploy/--publish에서 역추론.
        const v = (args.shift() ?? "").trim();
        if (!INTENT_VALUES.includes(v)) {
          throw new CliError(t("args.intent", { values: INTENT_VALUES.join(" | "), v }));
        }
        result.intent = v;
        break;
      }
      case "--label-style": {
        // 상태 라벨 표기 (#776). 미지정이면 version.yml 저장값 → (신규 en / 기존 ko).
        const v = (args.shift() ?? "").trim();
        if (!LABEL_STYLE_VALUES.includes(v)) {
          throw new CliError(`--label-style must be one of ${LABEL_STYLE_VALUES.join(" | ")}: '${v}'`);
        }
        result.labelStyle = v;
        break;
      }
      // ── deprecated alias (1 minor 유지 — #439) ──
      case "--nexus":
        process.stderr.write(t("args.nexusDeprecated") + "\n");
        result.publishTargets = [...new Set([...(result.publishTargets ?? []), "nexus"])];
        if (result.deployTarget === null) result.deployTarget = "none";
        break;
      case "--no-nexus":
        result.publishTargets = (result.publishTargets ?? []).filter((t) => t !== "nexus");
        break;
      case "--secret-backup": result.includeSecretBackup = true; break;
      case "--no-secret-backup": result.includeSecretBackup = false; break;
      // #566 — 비대화형에서도 켜고 끌 수 있어야 한다. 없으면 자동화 환경은 선택권이 없다.
      case "--ai-summary": result.aiPrSummary = true; break;
      case "--no-ai-summary": result.aiPrSummary = false; break;
      case "--projects-sync": result.projectsSync = true; break;
      case "--no-projects-sync": result.projectsSync = false; break;
      case "--npm-publish":
        process.stderr.write(t("args.npmPublishDeprecated") + "\n");
        result.publishTargets = [...new Set([...(result.publishTargets ?? []), "npm"])];
        break;
      case "--no-npm-publish":
        result.publishTargets = (result.publishTargets ?? []).filter((t) => t !== "npm");
        break;
      case "--paths": result.pathsCsv = args.shift() ?? ""; break;
      case "-h": case "--help": result.help = true; break;
      default:
        throw new CliError(t("args.unknownOption", { opt: a }));
    }
  }
  return result;
}

export class CliError extends Error {}

// 경로 정규화 (.sh resolve_project_paths §3.4): 앞뒤 공백·\→/·끝 /·앞 ./ 제거, 빈값→"."
export function normalizePath(p) {
  let s = String(p).trim();
  s = s.replace(/\\/g, "/");
  s = s.replace(/\/+$/, "");   // 끝 /
  s = s.replace(/^\.\//, "");  // 앞 ./
  return s === "" ? "." : s;
}

// --paths 맵 검증 (#674) — 저장소 밖 경로는 version_manager가 그 파일을 실제로 수정하므로 가장 위험하다.
//   · 절대경로·`..` 세그먼트 거부 (저장소 루트 기준 상대경로만)
//   · --type 으로 고르지 않은 타입 키 거부
//   · 존재하지 않는 폴더 거부 (심볼릭 링크로 밖을 가리키는 경우도 realpath 로 막는다)
export function validatePathsMap(map, { root, types }) {
  for (const [type, p] of map) {
    if (!types.includes(type)) {
      throw new CliError(t("args.paths.unselected", { type, types: types.join(",") || t("args.paths.none") }));
    }
    if (p.startsWith("/") || /^[A-Za-z]:/.test(p) || p.split("/").includes("..")) {
      throw new CliError(t("args.paths.relative", { type, path: p }));
    }
    const abs = join(root, p);
    if (!existsSync(abs) || !statSync(abs).isDirectory()) {
      throw new CliError(t("args.paths.missing", { type, path: p }));
    }
    const rel = relative(realpathSync(root), realpathSync(abs));
    if (rel.startsWith("..") || isAbsolute(rel)) {
      throw new CliError(t("args.paths.outside", { type, path: p }));
    }
  }
}

// "flutter=app,react=client" → Map<type, normalizedPath>. 타입 검증(무효 → throw).
export function parsePathsCsv(csv) {
  const map = new Map();
  if (!csv) return map;
  for (const pair of csv.split(",")) {
    if (pair.trim() === "") continue;
    const eq = pair.indexOf("=");
    const type = (eq >= 0 ? pair.slice(0, eq) : pair).trim();
    const rawPath = eq >= 0 ? pair.slice(eq + 1) : "";
    if (!VALID_TYPES.includes(type)) {
      throw new CliError(t("args.paths.badType", { type }));
    }
    map.set(type, normalizePath(rawPath));
  }
  return map;
}
