"""create-pr: 릴리스 노트를 본문에 담아 deploy PR 생성.

순서: 본문 파일 확인 > 앱 심사 승인 게이트 > 기존 PR 확인 > 커밋 차이 확인 > 생성 > 본문 재주입 가드
"""
from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_SCRIPTS_ROOT = _PROJECT_ROOT / "scripts"
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from common.config import get_github_pat  # noqa: E402
from common.emit import emit  # noqa: E402
from common.gh_client import (  # noqa: E402
    GitHubAPIError, update_pull_request, create_pull_request, get_pull_detail, get_ahead_by,
    find_open_pr_by_base,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from release_context import APP_SIGNAL_HINTS, collect_app_signals, load_config, read_app_release  # noqa: E402
from release_tools import wrap_release_notes  # noqa: E402

# 422 원문 > 의미 있는 code (#970)
_NO_COMMITS_MESSAGE = "No commits between"
_PR_EXISTS_MESSAGE = "pull request already exists"


def _resolve_body_file(body_file: str | None) -> Path | None:
    """본문 파일 경로 해석 — 절대 경로면 그대로, 상대 경로면 여러 위치를 순서대로 탐색.

    SKILL.md 절차는 `~/.projectops/tmp/{owner}__{repo}__release_notes.md`(홈, 절대경로)에
    저장하고 cli에 그 절대경로를 넘긴다. 다만 누군가 파일명만(상대경로) 넘겨도 찾을 수 있도록
    홈 tmp → PROJECT_ROOT/scripts(구버전 하위호환) → cwd 순으로 보강 탐색한다.
    찾지 못하면 None을 반환한다 (호출자가 본문 없음을 판단).
    """
    if not body_file:
        return None
    raw = Path(body_file)
    if raw.is_absolute():
        return raw if raw.exists() else None
    for candidate in (
        raw,
        Path.home() / ".projectops" / "tmp" / raw.name,
        Path.home() / ".suh-template" / "tmp" / raw.name,  # 구 경로 과도기 폴백(#459 이주)
        _PROJECT_ROOT / "scripts" / raw.name,
        Path.cwd() / raw,
    ):
        if candidate.exists():
            return candidate
    return None


def _git_root_or_cwd() -> Path:
    """cwd 가 하위 폴더여도 레포 루트에서 앱 신호를 읽는다"""
    import subprocess
    try:
        top = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True,
                             timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        top = ""
    return Path(top) if top else Path.cwd()


def _needs_app_release_approval(args) -> dict | None:
    """앱 심사 레포인데 --user-approved 가 없으면 거절 응답, 아니면 None (#970)

    조건: app_release 기록 true, 또는 앱 신호(strong_app·app_release_likely)가 있고 기록이 false 가 아님
    """
    if args.user_approved:
        return None
    project_root = Path(args.project_root).resolve() if args.project_root else _git_root_or_cwd()
    signals, hint = collect_app_signals(project_root)
    app_release = read_app_release(load_config(None), args.owner, args.repo)
    # unknown(version.yml·workflows 둘 다 못 읽음) = 루트를 잘못 짚은 것 — 기록이 없으면 막는 쪽으로 (fail-closed)
    is_app_release = app_release is True or (
        (hint in APP_SIGNAL_HINTS or hint == "unknown") and app_release is not False)
    if not is_app_release:
        return None
    return {
        "ok": False, "code": "needs_user_approval",
        "summary": "this deploy leads to app store review; no PR without user approval",
        "error": "an app review repo needs user approval every time, even in auto mode (it goes straight to store review)",
        "hint": hint, "app_release": app_release, "signals": signals,
        "next": ("show the user the review warning banner and the release notes and get approval > "
                 "once approved, run the same create-pr command again with --user-approved"),
    }


def _pr_exists_response(args, pr_number, pr_url) -> dict:
    """같은 head > base 로 열린 PR 이 이미 있을 때의 응답 (#970)"""
    return {
        "ok": False, "code": "pr_exists", "number": pr_number, "url": pr_url,
        "summary": f"PR #{pr_number} is already open for {args.head} > {args.base}",
        "hint": "reuse it without closing; to change the notes, update only the body with update-pr",
        "next": f"deploy-status {args.owner} {args.repo} --pr {pr_number}",
    }


def _nothing_to_deploy_response(args) -> dict:
    """릴리스할 커밋이 없을 때의 응답"""
    return {
        "ok": False, "code": "nothing_to_deploy",
        "summary": f"nothing to deploy: {args.head} has no commits ahead of {args.base}",
        "error": f"{args.head} has no commits ahead of {args.base}",
        "next": "check that the push went through and the branch pair is right with branches_check from detect-release-context",
    }


def _find_existing_pr(args, pat) -> dict | None:
    """head > base 로 열린 PR 상세. 조회 실패면 None (생성 시도에서 422 로 다시 잡힌다)"""
    try:
        return find_open_pr_by_base(args.owner, args.repo, args.base, pat, head=args.head)
    except GitHubAPIError:
        return None


def cmd_create_pr(args) -> int:
    """deploy PR 생성: 검증 > 승인 게이트 > 기존 PR·커밋 차이 확인 > 생성 > 본문 재주입 가드"""
    pat = get_github_pat(args.owner, args.repo)
    if not pat:
        return emit({"ok": False, "code": "missing_pat", "summary": "no PAT configured", "error": "no PAT configured"})
    body_path = _resolve_body_file(args.body_file)
    if args.body_file and not body_path:
        return emit({
            "ok": False, "code": "body_file_not_found",
            "summary": "body file not found",
            "error": (
                f"body file not found: {args.body_file} "
                f"(searched: absolute path | ~/.projectops/tmp/ | {_PROJECT_ROOT / 'scripts'} | cwd={Path.cwd()})"
            ),
        })
    body = body_path.read_text(encoding="utf-8") if body_path else ""

    # 앱 심사 승인 게이트 (API 호출 전)
    approval_refusal = _needs_app_release_approval(args)
    if approval_refusal:
        return emit(approval_refusal)

    # 이미 열린 PR 이 있으면 새로 만들지 않는다 (새로 열면 워크플로우 재트리거 > 본문 초기화 위험)
    existing_pr = _find_existing_pr(args, pat)
    if existing_pr:
        return emit(_pr_exists_response(args, existing_pr["number"], existing_pr.get("url")))

    # 릴리스할 커밋이 없으면 PR 을 만들지 않는다 (--allow-empty 로만 강행)
    try:
        ahead_by = get_ahead_by(args.owner, args.repo, args.base, args.head, pat)
    except GitHubAPIError:
        ahead_by = None
    if ahead_by == 0 and not args.allow_empty:
        return emit(_nothing_to_deploy_response(args))
    # 표식 블록은 도구가 씌운다 — 손으로 쓰면 틀려 본문이 지워진다
    body, wrapped = wrap_release_notes(body)
    try:
        result = create_pull_request(args.owner, args.repo, args.title, body, args.head, args.base, pat)
    except GitHubAPIError as e:
        # 사전 확인을 지나쳐 온 422 원문 > code 로 (#970)
        if e.status_code == 422 and _NO_COMMITS_MESSAGE.lower() in e.message.lower():
            return emit(_nothing_to_deploy_response(args))
        if e.status_code == 422 and _PR_EXISTS_MESSAGE in e.message.lower():
            existing_pr = _find_existing_pr(args, pat)
            if existing_pr:
                return emit(_pr_exists_response(args, existing_pr["number"], existing_pr.get("url")))
        return emit({"ok": False, "code": f"github_api_{e.status_code}",
                     "summary": f"PR creation failed (HTTP {e.status_code})", "error": str(e)})

    pr_number = result.get("number")
    guard_summary = _reinject_body_if_cleared(args, pat, pr_number, body)
    out = {
        **result,
        "summary": f"created PR #{pr_number}" + (f" / {guard_summary}" if guard_summary else ""),
        "next": f"deploy-status {args.owner} {args.repo} --pr {pr_number}",
    }
    if wrapped:
        out["notes_wrapped"] = True
    if guard_summary:
        out["body_guard"] = guard_summary
    return emit(out)


def _reinject_body_if_cleared(args, pat, pr_number, body) -> str | None:
    """PR 생성 직후 워크플로우가 본문을 비웠으면 다시 넣는다. 결과 요약 (본문 없으면 None)

    RELEASE-CHANGELOG step 2 는 PR opened 후 보통 3~10초 안에 본문을 초기화할 수 있다.
    15초 뒤 본문을 확인해 비었으면 update-pr 로 재주입 > step 8 폴링이 첫 시도에서 본문을 잡는다.
    """
    if not (pr_number and body):
        return None
    import time
    time.sleep(15)
    try:
        detail = get_pull_detail(args.owner, args.repo, pr_number, pat)
        if "Summary by CodeRabbit" not in (detail.get("body") or ""):
            update_pull_request(args.owner, args.repo, pr_number, pat, body=body)
            return "body re-injected (recovered from the workflow step 2 race)"
        return "body intact; no re-injection needed"
    except GitHubAPIError:
        return "could not re-check the body; continuing"
