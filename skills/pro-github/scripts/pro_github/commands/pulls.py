"""PR 서브커맨드: 생성·목록·수정·상세 판정·댓글·닫기·다시 열기·머지."""
from __future__ import annotations

from pathlib import Path

from common.emit import emit
from common.gh_client import GitHubAPIError
from pro_github.registry import Command
from pro_github.responses import api_error, missing_pat


def _preflight_head_branch(args, api, pat) -> int | None:
    """head 브랜치 사전 점검: 글자 깨짐 > origin 존재. 문제 있으면 응답 코드, 없으면 None (#938)"""
    owner, _, branch = args.head.rpartition(":")
    if "\ufffd" in branch:
        return emit({
            "ok": False,
            "code": "head_branch_truncated",
            "error": f"head 브랜치명이 글자 중간에서 잘렸습니다: {branch}",
            "next": "git branch --show-current 로 브랜치명을 다시 읽어 head 로 넘긴다",
        })
    # 포크(다른 owner)의 브랜치는 이 레포 API 로 볼 수 없으니 점검하지 않는다
    if owner and owner != args.owner:
        return None
    try:
        sha = api.get_branch_head(args.owner, args.repo, branch, pat)
    except GitHubAPIError:
        return None
    if sha is None:
        return emit({
            "ok": False,
            "code": "head_branch_not_on_origin",
            "error": f"origin 에 head 브랜치가 없습니다: {branch}",
            "next": f"git push -u origin {branch} 후 다시 부른다",
        })
    return None


def _resolve_head_and_base(args) -> int | None:
    """위치 인자·--head/--base 를 하나로 > args.head·args.base. 문제 있으면 응답 코드, 없으면 None"""
    args.head = args.head_option or args.head_positional
    args.base = args.base_option or args.base_positional
    usage = "create-pr <owner> <repo> <title> <body_file> --head <브랜치> --base <브랜치>"
    if not args.head or not args.base:
        return emit({"ok": False, "code": "missing_argument", "error": "head·base 브랜치 필요", "usage": usage})
    # 브랜치명에는 공백이 없다: 공백이 있으면 제목이 head 자리에 들어간 순서 오류
    if any(character.isspace() for character in args.head + args.base):
        return emit({"ok": False, "code": "argument_order",
                     "error": f"head/base 에 공백이 있다 — 인자 순서가 틀렸다 (head={args.head!r}, base={args.base!r})",
                     "usage": usage, "next": "제목은 셋째, 본문 파일은 넷째 자리. 브랜치는 --head·--base 로 준다"})
    return None


def cmd_create_pr(args, api) -> int:
    invalid = _resolve_head_and_base(args)
    if invalid is not None:
        return invalid
    pat = api.get_github_pat(args.owner, args.repo)
    if not pat:
        return missing_pat()
    blocked = _preflight_head_branch(args, api, pat)
    if blocked is not None:
        return blocked
    body_path = Path(args.body_file)
    body = body_path.read_text(encoding="utf-8") if body_path.exists() else ""
    try:
        result = api.create_pull_request(args.owner, args.repo, args.title, body, args.head, args.base, pat)
        return emit({
            **result,
            "summary": f"PR #{result.get('number')} 생성 완료",
            "next": f"list-prs {args.owner} {args.repo}",
        })
    except GitHubAPIError as e:
        return api_error(e)


def cmd_list_prs(args, api) -> int:
    pat = api.get_github_pat(args.owner, args.repo)
    if not pat:
        return missing_pat()
    try:
        result = api.list_pulls(args.owner, args.repo, pat, args.state)
        return emit({
            "count": len(result),
            "prs": result,
            "summary": f"{args.owner}/{args.repo} PR {len(result)}개 ({args.state})",
        })
    except GitHubAPIError as e:
        return api_error(e)


def cmd_update_pr(args, api) -> int:
    pat = api.get_github_pat(args.owner, args.repo)
    if not pat:
        return missing_pat()
    body = None
    if args.body_file:
        body_path = Path(args.body_file)
        body = body_path.read_text(encoding="utf-8") if body_path.exists() else None
        if body is None:
            return emit({
                "ok": False,
                "code": "body_file_not_found",
                "error": f"수정용 본문 파일이 존재하지 않습니다: {args.body_file}",
                "path_attempted": str(body_path.resolve()),
            })
    # 바꿀 값이 없으면 PATCH 하지 않는다 (#699)
    if args.title is None and body is None and args.state is None:
        return emit({
            "ok": False,
            "code": "nothing_to_update",
            "error": "바꿀 값이 없습니다 (--title/--body-file/--state 중 하나 필요)",
        })
    try:
        result = api.update_pull_request(
            args.owner, args.repo, args.number, pat,
            title=args.title, body=body, state=args.state,
        )
        return emit({**result, "summary": f"PR #{args.number} 수정 완료"})
    except GitHubAPIError as e:
        return api_error(e)


def cmd_get_pr(args, api) -> int:
    pat = api.get_github_pat(args.owner, args.repo)
    if not pat:
        return missing_pat()
    try:
        pr = api.get_pull_detail(args.owner, args.repo, args.number, pat)
        # mergeable_state가 아직 계산 전이면 unknown/None — agent가 재조회 판단
        state = pr.get("mergeable_state")
        if pr.get("merged"):
            verdict = "merged"
        elif pr.get("state") == "closed":
            verdict = "closed"
        elif state in (None, "unknown"):
            verdict = "computing"
        elif state in ("clean", "unstable", "has_hooks"):
            verdict = "mergeable"
        else:  # dirty, blocked, behind, draft
            verdict = "blocked"
        return emit({
            "pr": pr,
            "verdict": verdict,
            "summary": f"PR #{args.number} {pr.get('state')} / mergeable_state={state} → {verdict}",
        })
    except GitHubAPIError as e:
        return api_error(e)


def cmd_add_pr_comment(args, api) -> int:
    pat = api.get_github_pat(args.owner, args.repo)
    if not pat:
        return missing_pat()
    body_path = Path(args.body_file)
    if not body_path.exists():
        return emit({"ok": False, "code": "body_file_not_found", "error": f"{args.body_file} 없음"})
    body = body_path.read_text(encoding="utf-8")
    try:
        # PR도 GitHub API에선 issue이므로 issues/{n}/comments로 댓글 추가
        result = api.add_comment(args.owner, args.repo, args.number, body, pat)
        return emit({**result, "summary": f"PR #{args.number}에 댓글 추가 완료"})
    except GitHubAPIError as e:
        return api_error(e)


def cmd_close_pr(args, api) -> int:
    pat = api.get_github_pat(args.owner, args.repo)
    if not pat:
        return missing_pat()
    try:
        result = api.update_pull_request(args.owner, args.repo, args.number, pat, state="closed")
        return emit({**result, "summary": f"PR #{args.number} 닫음"})
    except GitHubAPIError as e:
        return api_error(e)


def cmd_reopen_pr(args, api) -> int:
    pat = api.get_github_pat(args.owner, args.repo)
    if not pat:
        return missing_pat()
    try:
        result = api.update_pull_request(args.owner, args.repo, args.number, pat, state="open")
        return emit({**result, "summary": f"PR #{args.number} 다시 열음"})
    except GitHubAPIError as e:
        return api_error(e)


def cmd_merge_pr(args, api) -> int:
    pat = api.get_github_pat(args.owner, args.repo)
    if not pat:
        return missing_pat()
    try:
        result = api.merge_pull_request(
            args.owner, args.repo, args.number, pat,
            merge_method=args.method, commit_title=args.title, commit_message=args.message,
        )
        return emit({
            **result,
            "verdict": "merged" if result.get("merged") else "not_merged",
            "summary": f"PR #{args.number} 머지 완료 ({args.method})",
        })
    except GitHubAPIError as e:
        # 405: 머지 불가(충돌/체크 실패/드래프트), 409: sha 불일치, 422: rebase 불허
        verdict = {405: "not_mergeable", 409: "sha_mismatch", 422: "method_not_allowed"}.get(
            e.status_code, "error"
        )
        return emit({
            "ok": False,
            "code": f"github_api_{e.status_code}",
            "verdict": verdict,
            "error": str(e),
            "summary": f"PR #{args.number} 머지 실패: {verdict}",
        })


# ── 인자 ──

def _configure_create_pr(parser) -> None:
    parser.add_argument("owner")
    parser.add_argument("repo")
    parser.add_argument("title")
    parser.add_argument("body_file")
    # 위치 인자 6개 순서가 자주 틀려 플래그로도 받는다 (플래그가 우선)
    parser.add_argument("head_positional", nargs="?", metavar="head")
    parser.add_argument("base_positional", nargs="?", metavar="base")
    parser.add_argument("--head", dest="head_option", default=None, metavar="BRANCH", help="head 브랜치 (포크면 owner:branch)")
    parser.add_argument("--base", dest="base_option", default=None, metavar="BRANCH", help="base 브랜치")


def _configure_list_prs(parser) -> None:
    parser.add_argument("owner")
    parser.add_argument("repo")
    parser.add_argument("--state", choices=["open", "closed", "all"], default="open")


def _configure_update_pr(parser) -> None:
    parser.add_argument("owner")
    parser.add_argument("repo")
    parser.add_argument("number", type=int)
    parser.add_argument("body_file", nargs="?")
    parser.add_argument("--title")
    parser.add_argument("--state", choices=["open", "closed"])


def _configure_get_pr(parser) -> None:
    parser.add_argument("owner")
    parser.add_argument("repo")
    parser.add_argument("number", type=int)


def _configure_add_pr_comment(parser) -> None:
    parser.add_argument("owner")
    parser.add_argument("repo")
    parser.add_argument("number", type=int)
    parser.add_argument("body_file")


def _configure_close_pr(parser) -> None:
    parser.add_argument("owner")
    parser.add_argument("repo")
    parser.add_argument("number", type=int)


def _configure_reopen_pr(parser) -> None:
    parser.add_argument("owner")
    parser.add_argument("repo")
    parser.add_argument("number", type=int)


def _configure_merge_pr(parser) -> None:
    parser.add_argument("owner")
    parser.add_argument("repo")
    parser.add_argument("number", type=int)
    parser.add_argument("--method", choices=["merge", "squash", "rebase"], default="merge")
    parser.add_argument("--title", help="머지 커밋 제목")
    parser.add_argument("--message", help="머지 커밋 본문")


COMMANDS = [
    Command(name="create-pr", help="PR 생성", run=cmd_create_pr,
            configure=_configure_create_pr),
    Command(name="list-prs", help="PR 목록", run=cmd_list_prs,
            configure=_configure_list_prs),
    Command(name="update-pr", help="PR 수정", run=cmd_update_pr,
            configure=_configure_update_pr),
    Command(name="get-pr", help="PR 상세 (mergeable_state 등)", run=cmd_get_pr,
            configure=_configure_get_pr),
    Command(name="add-pr-comment", help="PR에 댓글 추가", run=cmd_add_pr_comment,
            configure=_configure_add_pr_comment),
    Command(name="close-pr", help="PR 닫기", run=cmd_close_pr,
            configure=_configure_close_pr),
    Command(name="reopen-pr", help="PR 다시 열기", run=cmd_reopen_pr,
            configure=_configure_reopen_pr),
    Command(name="merge-pr", help="PR 머지", run=cmd_merge_pr,
            configure=_configure_merge_pr),
]
