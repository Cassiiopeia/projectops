// 브랜치 존재 확인·생성 헬퍼 (#477) — 마법사의 개발 브랜치 생성 제안에 사용.
// 모든 함수는 실패 시 조용히 false/null을 반환한다 (git 미설치·비레포·원격 없음에서 마법사가 죽지 않게).
import { execFileSync } from "node:child_process";

function git(root, args, env = undefined) {
  try {
    return execFileSync("git", args, { cwd: root, encoding: "utf8", stdio: ["ignore", "pipe", "ignore"], env }).trim();
  } catch { return null; }
}

/**
 * 비대화형 원격 접근용 환경 (#988): 자격 증명 질문 차단 > 즉시 실패 > 수동 명령 안내
 * 차단 4개: 터미널 프롬프트, askpass(GIT_/SSH_), Git Credential Manager 창, ssh 비밀번호 질문
 * ssh 는 사용자 지정 명령(GIT_SSH_COMMAND·GIT_SSH·core.sshCommand)이 없을 때만 BatchMode 로 덮는다
 */
export function nonInteractiveGitEnv(baseEnv = process.env, { hasCustomSshCommand = false } = {}) {
  const env = { ...baseEnv, GIT_TERMINAL_PROMPT: "0", GIT_ASKPASS: "", SSH_ASKPASS: "", GCM_INTERACTIVE: "never" };
  if (!hasCustomSshCommand && !baseEnv.GIT_SSH_COMMAND && !baseEnv.GIT_SSH) env.GIT_SSH_COMMAND = "ssh -o BatchMode=yes";
  return env;
}

// 원격 명령 환경: 대화형은 상속(undefined), 비대화형은 질문 차단 환경
function remoteEnv(root, isNonInteractive) {
  if (!isNonInteractive) return undefined;
  const hasCustomSshCommand = Boolean(git(root, ["config", "--get", "core.sshCommand"]));
  return nonInteractiveGitEnv(process.env, { hasCustomSshCommand });
}

// 브랜치 존재 상태. remote는 origin 조회 실패(원격 없음·네트워크) 시 null(불명).
export function branchStatus(root, name, { isNonInteractive = false } = {}) {
  const isRepo = git(root, ["rev-parse", "--git-dir"]) !== null;
  if (!isRepo || !name) return { isRepo, local: false, remote: null };
  const local = git(root, ["show-ref", "--verify", `refs/heads/${name}`]) !== null;
  const ls = git(root, ["ls-remote", "--heads", "origin", name], remoteEnv(root, isNonInteractive));
  const remote = ls === null ? null : ls.length > 0;
  return { isRepo, local, remote };
}

// fromBranch(기본 브랜치)에서 로컬 브랜치 생성 — checkout하지 않는다.
// 로컬에 fromBranch가 없으면 origin/fromBranch → HEAD 순으로 폴백.
export function createBranch(root, name, fromBranch = "") {
  if (fromBranch) {
    if (git(root, ["branch", name, fromBranch]) !== null) return true;
    if (git(root, ["branch", name, `origin/${fromBranch}`]) !== null) return true;
  }
  return git(root, ["branch", name]) !== null;
}

// 원격(origin)에 브랜치 push (-u). 자격/네트워크 실패 시 false.
// 비대화형은 자격 증명을 묻지 않고 바로 실패 (#988 — 묻는 순간 무인 실행이 멈춘다)
export function pushBranch(root, name, { isNonInteractive = false } = {}) {
  return git(root, ["push", "-u", "origin", name], remoteEnv(root, isNonInteractive)) !== null;
}
