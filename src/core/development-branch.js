// 비대화형 개발(릴리스 소스) 브랜치 생성 (#715) — --create-development-branch 를 준 실행에서만.
// 대화형 ensureDeployBranch 를 "모든 질문에 예"로 다시 쓴다: 존재 판단·생성·push 경로를 한 벌로 유지.
// 실패해도 예외를 던지지 않는다 — 통합 전체를 실패시키지 않고 수동 명령만 남긴다.
import { ensureDeployBranch } from "./options-ask.js";

// ensureDeployBranch state > 결과 3종 (created · skipped · failed)
const STATUS_BY_STATE = {
  "exists-local": "skipped",
  "exists-remote": "skipped",
  "pushed": "created",
  "push-failed": "failed",
  "create-failed": "failed",
  "not-a-repo": "failed",
  "not-checked": "failed",
};

// 실패 사유별 수동 명령 (push 실패는 로컬 브랜치가 이미 생겼으므로 push 만)
function manualCommandFor(state, branch, base) {
  if (state === "push-failed") return `git push -u origin ${branch}`;
  if (state === "create-failed" && base) return `git branch ${branch} ${base} && git push -u origin ${branch}`;
  return `git checkout -b ${branch} && git push -u origin ${branch}`;
}

/**
 * 개발 브랜치 확인 > 없으면 기본 브랜치에서 생성 > origin push
 * 반환: { status, reason, branch, base, pushed, manualCommand(실패 시만) }
 */
export async function createDevelopmentBranchUnattended({ targetRoot = ".", branch = "develop", defaultBranch = "", say = () => {} }) {
  const answerYes = { confirm: async () => true };
  const outcome = await ensureDeployBranch({ targetRoot, deployBranch: branch, defaultBranch, io: answerYes, say });
  const status = STATUS_BY_STATE[outcome.state] ?? "failed";
  return {
    status,
    reason: outcome.state,
    branch,
    base: defaultBranch,
    pushed: outcome.pushed === true,
    manualCommand: status === "failed" ? manualCommandFor(outcome.state, branch, defaultBranch) : null,
  };
}

/**
 * 실행 단계 래퍼: 플래그 확인 > 생성 시도 > 실행 기록(trace) 남김
 * 플래그가 없으면 만들지 않고 "왜 안 만들었는지"만 기록. 반환: 결과 | null(플래그 없음)
 */
export async function runDevelopmentBranchStep({ isRequested = false, targetRoot, branch, defaultBranch, trace = null, say = () => {} }) {
  const name = branch || "develop";
  if (!isRequested) {
    trace?.event("dev-branch", "not-requested", name, { flag: "--create-development-branch", note: "left as a manual step" });
    return null;
  }
  const result = await createDevelopmentBranchUnattended({ targetRoot, branch: name, defaultBranch, say });
  // action 이 곧 결과 — failed 는 로그에서 ERROR 로 보인다 (run-trace levelOf)
  trace?.event("dev-branch", result.status, name, {
    base: defaultBranch || null, reason: result.reason, pushed: result.pushed, manualCommand: result.manualCommand,
  });
  return result;
}
