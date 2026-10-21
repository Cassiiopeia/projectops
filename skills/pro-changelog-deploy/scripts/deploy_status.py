"""deploy-status: deploy PR 의 automerge 상태를 verdict 하나로 판정한다 (--wait 로 도구 안에서 폴링, #945)."""
from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[3] / "scripts"
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from common.config import get_github_pat  # noqa: E402
from common.emit import emit  # noqa: E402
from common.gh_client import (  # noqa: E402
    GitHubAPIError, resolve_pr_runs, get_pull_detail, find_open_pr_by_base, get_branch_head, list_runs,
)

# automerge 대기가 이 시간을 넘으면 정상 대기가 아니라 막힌 것으로 본다 (#945)
STUCK_AFTER_SECONDS = 600
# --wait 폴링 간격과 한 번 호출의 최대 대기 (하네스의 명령 시간 상한 안에서 끝나게)
WAIT_POLL_SECONDS = 15
WAIT_MAX_SECONDS = 540
# PR 생성 직후 워크플로우가 API 에 아직 안 보일 수 있는 유예 (초)
WORKFLOW_GRACE_SECONDS = 120
# 아직 끝난 것이 아니라서 더 기다릴 가치가 있는 verdict
_STILL_WAITING_VERDICTS = ("waiting_for_automerge", "waiting_for_workflow")
# 시작 전·진행 중인 run 상태
_RUNNING_STATUSES = ("in_progress", "queued", "waiting", "requested", "pending")
# RELEASE-CHANGELOG 워크플로우 파일 (신·구 이름, #455 리네임)
_RELEASE_WORKFLOW_PATHS = ("project-common-release-changelog.yaml", "project-common-auto-changelog-control.yaml")


def _stuck_reason(pr_age_sec, workflow, workflow_running, mergeable_state):
    """automerge 대기가 임계값을 넘었을 때 왜 막혔는지. 막힌 게 아니면 None"""
    if pr_age_sec is None or pr_age_sec < STUCK_AFTER_SECONDS or workflow_running:
        return None
    if workflow is None:
        return "no_workflow_on_head"  # 이 PR 의 RELEASE-CHANGELOG run 이 head 브랜치 어디에도 없고 대기열도 비었다
    if workflow.get("conclusion") == "success":
        return "workflow_done_not_merged"  # 워크플로우는 끝났는데 PR 이 머지되지 않았다
    return None


def cmd_deploy_status(args) -> int:
    """deploy PR 상태 판정. --wait N 이면 끝날 때까지(최대 N초) 도구 안에서 폴링한다 (#945)."""
    import time
    pat = get_github_pat(args.owner, args.repo)
    if not pat:
        return emit({"ok": False, "code": "missing_pat", "error": "PAT 없음"})
    wait_seconds = min(max(args.wait or 0, 0), WAIT_MAX_SECONDS)
    started = time.monotonic()
    try:
        while True:
            payload = _deploy_status_once(args, pat)
            waited = int(time.monotonic() - started)
            if payload.get("verdict") not in _STILL_WAITING_VERDICTS or waited + WAIT_POLL_SECONDS > wait_seconds:
                break
            time.sleep(WAIT_POLL_SECONDS)
        if wait_seconds:
            payload["waited_seconds"] = waited
        return emit(payload)
    except GitHubAPIError as e:
        return emit({"ok": False, "code": f"github_api_{e.status_code}", "error": str(e)})


def _is_release_run(run: dict) -> bool:
    """RELEASE-CHANGELOG run 인지: 파일 path 우선, 이름 키워드는 옛 레포 폴백

    name 은 사람이 보는 라벨이라 바뀐다 — path 가 식별자다.
    """
    path = (run.get("path") or "").lower()
    name = (run.get("name") or "").upper()
    return path.endswith(_RELEASE_WORKFLOW_PATHS) \
        or ("CHANGELOG" in name and ("AUTO" in name or "DEPLOY" in name or "RELEASE" in name))


def _find_release_workflow(owner: str, repo: str, pr_number: int, pat: str) -> dict | None:
    """PR 의 최신 RELEASE-CHANGELOG run (현재 head SHA + head 브랜치 PR 이벤트, 최신순). 없으면 None"""
    try:
        runs = resolve_pr_runs(owner, repo, pr_number, pat).get("runs", [])
    except GitHubAPIError:
        return None
    for run in runs:
        if _is_release_run(run):
            return {
                "name": run.get("name"),
                "path": run.get("path"),
                "status": run.get("status"),
                "conclusion": run.get("conclusion"),
                "run_url": run.get("url"),
                "head_sha": run.get("head_sha"),
                # 옛 head SHA 에서 돈 run 이면 false (push 로 head 가 바뀐 뒤)
                "is_current_head": run.get("is_current_head", True),
            }
    return None


def _count_repository_queued_runs(owner: str, repo: str, pat: str) -> int:
    """레포 전체의 queued run 수 (러너 대기열 지연 판정용). 조회 실패면 0"""
    try:
        return len(list_runs(owner, repo, pat, status="queued", limit=20))
    except GitHubAPIError:
        return 0


def _deploy_status_once(args, pat) -> dict:
    """한 번 조회한 verdict 를 dict 로 돌려준다 (emit 은 호출자가)."""
    if args.pr:
        pr = get_pull_detail(args.owner, args.repo, args.pr, pat)
    else:
        pr = find_open_pr_by_base(args.owner, args.repo, args.base, pat, head=args.head)
    branch_head = get_branch_head(args.owner, args.repo, args.base, pat)
    deploy_branch = {"name": args.base, "head_sha": branch_head}

    if pr is None:
        return {
            "pr": None,
            "workflow": None,
            "deploy_branch": deploy_branch,
            "verdict": "no_pr",
            "summary": f"base={args.base}로 들어오는 open PR 없음",
        }

    workflow = _find_release_workflow(args.owner, args.repo, pr["number"], pat)

    body = pr.get("body") or ""
    has_summary = "Summary by CodeRabbit" in body
    pr_out = {
        "number": pr["number"],
        "state": pr["state"],
        "merged": pr["merged"],
        "mergeable_state": pr["mergeable_state"],
        "has_coderabbit_summary": has_summary,
        "head_sha": pr["head_sha"],
        "url": pr["url"],
        "created_at": pr.get("created_at"),
    }

    workflow_status = (workflow or {}).get("status")
    workflow_conclusion = (workflow or {}).get("conclusion")
    workflow_running = workflow_status in _RUNNING_STATUSES

    # PR 생성 후 얼마 안 지났으면 워크플로우가 막 trigger되어 아직 API에
    # 반영되지 않았을 가능성을 가드한다. workflow=null이라도 PR이 갓 만들어진 상태면
    # missing 판정 대신 대기로 양보한다.
    import datetime as _dt
    pr_age_sec = None
    if pr.get("created_at"):
        try:
            created = _dt.datetime.fromisoformat(pr["created_at"].replace("Z", "+00:00"))
            now = _dt.datetime.now(_dt.timezone.utc)
            pr_age_sec = (now - created).total_seconds()
        except Exception:
            pr_age_sec = None
    pr_young = (pr_age_sec is not None and pr_age_sec < WORKFLOW_GRACE_SECONDS)
    # 매칭 run 이 없으면 레포 대기열 확인 (러너 부족으로 run 이 아직 안 잡힌 경우, #970)
    repo_queued_count = 0
    if workflow is None and not pr_young:
        repo_queued_count = _count_repository_queued_runs(args.owner, args.repo, pat)

    next_hint = f"deploy-status {args.owner} {args.repo} --pr {pr['number']}"
    # 대기열 지연은 PR 닫기·재오픈으로 풀리지 않는다 — 다시 열면 run 만 하나 더 쌓인다 (#970)
    wait_hint = (f"deploy-status {args.owner} {args.repo} --pr {pr['number']} --wait {WAIT_MAX_SECONDS} "
                 "(PR 을 닫거나 다시 열지 않는다)")
    if pr["merged"]:
        verdict, summary = "merged", f"PR #{pr['number']} automerge 완료"
        # 머지 뒤 마무리 누락 방지 (#970)
        next_hint = (f"릴리스에 포함된 이슈마다(PR #{pr['number']} 커밋 메시지의 이슈 URL): "
                     "pro-report 로 보고서 댓글 > pro-github finish-issue 로 완료 처리")
    elif pr["mergeable_state"] == "dirty":
        verdict = "conflict"
        summary = f"PR #{pr['number']} 병합 충돌(dirty)"
    elif pr["mergeable_state"] == "behind":
        verdict = "behind"
        summary = f"PR #{pr['number']} base 보다 뒤처짐(behind) — base 를 head 에 병합해야 한다"
        next_hint = "git fetch origin && git merge origin/<base> 후 push (충돌 없이 뒤처진 것뿐)"
    elif pr["mergeable_state"] == "blocked":
        verdict = "blocked"
        summary = f"PR #{pr['number']} 머지가 막힘(blocked) — 필수 검사·리뷰·보호 규칙 대기일 수 있다"
    elif workflow and workflow_conclusion == "failure":
        # 최신 RELEASE run 이 실패 (옛 head SHA 의 run 이어도 더 새 run 이 없으면 실패로 본다)
        verdict = "workflow_failed"
        sha_note = "" if workflow.get("is_current_head") else " (이전 head SHA 의 run)"
        summary = f"RELEASE-CHANGELOG 워크플로우 실패{sha_note}: {workflow.get('run_url')}"
        next_hint = "workflow.run_url 의 실패 원인 확인 > fix 모드로 재실행"
    elif workflow_running:
        # 워크플로우 대기·진행 중이면 body·has_summary가 일시적으로 비어 보여도 정상 대기로 본다 (race 가드)
        verdict = "waiting_for_workflow"
        summary = f"PR #{pr['number']} RELEASE-CHANGELOG {workflow_status} — 워크플로우 대기"
        next_hint = wait_hint
    elif workflow is None and (pr_young or repo_queued_count):
        # 매칭 run 없음: PR 생성 직후(API 반영 지연) 또는 레포 대기열에 run 이 밀려 있음
        verdict = "waiting_for_workflow"
        reason = (f"생성 직후({int(pr_age_sec)}s)" if pr_young
                  else f"레포 대기열에 run {repo_queued_count}개")
        summary = f"PR #{pr['number']} {reason}, 워크플로우 시작 대기"
        next_hint = wait_hint
    elif not has_summary:
        # 워크플로우가 진행 중이 아니고 PR도 갓 생성된 게 아니면 진짜 body 초기화 사고로 판정
        verdict = "missing_coderabbit_summary"
        summary = f"PR #{pr['number']} 본문에 'Summary by CodeRabbit' 없음 — fix 모드로 재작성"
    else:
        verdict = "waiting_for_automerge"
        summary = f"PR #{pr['number']} open·{pr['mergeable_state']}, automerge 대기"

    # 대기가 임계값을 넘으면 무한 대기 대신 막힘으로 알린다 (#945)
    pr_out["age_seconds"] = int(pr_age_sec) if pr_age_sec is not None else None
    stuck = _stuck_reason(pr_age_sec, workflow, workflow_running, pr["mergeable_state"]) \
        if verdict == "waiting_for_automerge" else None
    if stuck:
        verdict = "stuck"
        summary = f"PR #{pr['number']} {int(pr_age_sec)}초째 automerge 안 됨 ({stuck})"
        next_hint = ("fix 모드: 기존 PR 을 닫고 새 PR 로 워크플로우를 다시 트리거한다 "
                     "(수정 push 가 opened 트리거를 다시 일으키지 못한 경우)")

    return {
        "pr": pr_out,
        "workflow": workflow,
        "deploy_branch": deploy_branch,
        "verdict": verdict,
        **({"stuck_reason": stuck} if stuck else {}),
        "summary": summary,
        "next": next_hint,
    }
