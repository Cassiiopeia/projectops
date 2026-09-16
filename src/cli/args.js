// CLI 인자 파싱 (.sh top-level while-case 등가) — template_integrator.sh 842~920.
import { VALID_TYPES } from "../context.js";

export const DEPLOY_TARGETS = ["docker-ssh", "vercel", "none"];
export const PUBLISH_TARGETS = ["nexus", "npm", "github-packages"];
export const INTENT_VALUES = ["app", "library", "both", "none", "manual"];

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
    intent: null,            // 프로젝트 성격 (#485): --intent app|library|both|none|manual, null=미설정(역추론)
    includeSecretBackup: null,
    aiPrSummary: null,   // #566 — AI 변경 요약 워크플로우 포함 여부
    pathsCsv: "",            // "flutter=app,react=client" 원문 (정규화는 resolve 단계)
    force: false,
    help: false,
    showVersion: false,      // -v/--version → projectops 패키지 버전 출력 (npm 관례)
  };
  const args = [...argv];
  while (args.length > 0) {
    const a = args.shift();
    switch (a) {
      case "-m": case "--mode":
        result.mode = args.shift() ?? ""; break;
      case "-v": case "--version":
        // npm 관례: -v/--version 은 패키지 버전 출력. (초기 버전 지정은 --project-version)
        result.showVersion = true; break;
      case "--project-version":
        result.version = args.shift() ?? ""; break;
      case "-t": case "--type": {
        const csv = args.shift() ?? "";
        const seen = new Set();
        const types = [];
        for (let t of csv.split(",")) {
          t = t.replace(/\s/g, "");
          if (t === "") continue;
          if (seen.has(t)) continue;         // dedup
          if (!VALID_TYPES.includes(t)) {
            throw new CliError(`지원하지 않는 타입: '${t}'\n지원 타입: ${VALID_TYPES.join(" ")}`);
          }
          seen.add(t);
          types.push(t);
        }
        if (types.length === 0) throw new CliError("--type 인자가 비어 있습니다");
        result.types = types;
        result.primaryType = types[0];
        break;
      }
      case "--force": result.force = true; break;
      case "--deploy": {
        const v = args.shift() ?? "";
        if (!DEPLOY_TARGETS.includes(v)) {
          throw new CliError(`--deploy 값은 ${DEPLOY_TARGETS.join(" | ")} 중 하나여야 합니다: '${v}'`);
        }
        result.deployTarget = v;
        break;
      }
      case "--publish": {
        const csv = args.shift() ?? "";
        const targets = [];
        for (let t of csv.split(",")) {
          t = t.replace(/\s/g, "");
          if (t === "") continue;
          if (!PUBLISH_TARGETS.includes(t)) {
            throw new CliError(`--publish 값은 ${PUBLISH_TARGETS.join(" | ")} csv여야 합니다: '${t}'`);
          }
          if (!targets.includes(t)) targets.push(t);
        }
        result.publishTargets = targets;
        break;
      }
      case "--deploy-branch": {
        // 릴리스 PR head 브랜치 (#456). default_branch와 별개.
        const v = (args.shift() ?? "").trim();
        if (v) result.deployBranch = v;
        break;
      }
      case "--intent": {
        // 프로젝트 성격 (#485). 미지정이면 --deploy/--publish에서 역추론.
        const v = (args.shift() ?? "").trim();
        if (!INTENT_VALUES.includes(v)) {
          throw new CliError(`--intent 값은 ${INTENT_VALUES.join(" | ")} 중 하나여야 합니다: '${v}'`);
        }
        result.intent = v;
        break;
      }
      // ── deprecated alias (1 minor 유지 — #439) ──
      case "--nexus":
        process.stderr.write("⚠️  --nexus는 deprecated입니다. --publish nexus --deploy none 을 사용하세요.\n");
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
      case "--npm-publish":
        process.stderr.write("⚠️  --npm-publish는 deprecated입니다. --publish npm 을 사용하세요.\n");
        result.publishTargets = [...new Set([...(result.publishTargets ?? []), "npm"])];
        break;
      case "--no-npm-publish":
        result.publishTargets = (result.publishTargets ?? []).filter((t) => t !== "npm");
        break;
      case "--paths": result.pathsCsv = args.shift() ?? ""; break;
      case "-h": case "--help": result.help = true; break;
      default:
        throw new CliError(`알 수 없는 옵션: ${a}`);
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
      throw new CliError(`--paths에 지원하지 않는 타입: '${type}'`);
    }
    map.set(type, normalizePath(rawPath));
  }
  return map;
}
