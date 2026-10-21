"""이슈·PR 댓글 서브커맨드: 추가·목록·수정·삭제."""
from __future__ import annotations

from pathlib import Path

from common.emit import emit
from common.gh_client import GitHubAPIError
from pro_github.registry import Command
from pro_github.responses import api_error, missing_pat


def cmd_add_comment(args, api) -> int:
    body_file = args.body_file or args.body_file_option
    if not body_file:
        return emit({"ok": False, "code": "missing_argument", "error": "본문 파일 필요",
                     "usage": "add-comment <owner> <repo> <number> <body_file> (또는 --body-file <파일>)"})
    pat = api.get_github_pat(args.owner, args.repo)
    if not pat:
        return missing_pat()
    body_path = Path(body_file)
    if not body_path.exists():
        return emit({"ok": False, "code": "body_file_not_found", "error": f"{body_file} 없음"})
    body = body_path.read_text(encoding="utf-8")
    try:
        result = api.add_comment(args.owner, args.repo, args.number, body, pat)
        return emit({**result, "summary": f"#{args.number}에 댓글 추가 완료"})
    except GitHubAPIError as e:
        return api_error(e)


def cmd_list_comments(args, api) -> int:
    pat = api.get_github_pat(args.owner, args.repo)
    if not pat:
        return missing_pat()
    try:
        comments = api.get_issue_comments(args.owner, args.repo, args.number, pat)
        return emit({
            "count": len(comments),
            "comments": comments,
            "summary": f"#{args.number} 댓글 {len(comments)}개",
        })
    except GitHubAPIError as e:
        return api_error(e)


def cmd_edit_comment(args, api) -> int:
    pat = api.get_github_pat(args.owner, args.repo)
    if not pat:
        return missing_pat()
    body_path = Path(args.body_file)
    if not body_path.exists():
        return emit({"ok": False, "code": "body_file_not_found", "error": f"{args.body_file} 없음"})
    body = body_path.read_text(encoding="utf-8")
    try:
        result = api.update_comment(args.owner, args.repo, args.comment_id, body, pat)
        return emit({**result, "summary": f"댓글 {args.comment_id} 수정 완료"})
    except GitHubAPIError as e:
        return api_error(e)


def cmd_delete_comment(args, api) -> int:
    pat = api.get_github_pat(args.owner, args.repo)
    if not pat:
        return missing_pat()
    try:
        result = api.delete_comment(args.owner, args.repo, args.comment_id, pat)
        return emit({**result, "summary": f"댓글 {args.comment_id} 삭제 완료"})
    except GitHubAPIError as e:
        return api_error(e)


# ── 인자 ──

def _configure_add_comment(parser) -> None:
    parser.add_argument("owner")
    parser.add_argument("repo")
    parser.add_argument("number", type=int)
    # 위치 인자와 --body-file 둘 다 받는다 (update-issue 와 같은 모양)
    parser.add_argument("body_file", nargs="?")
    parser.add_argument("--body-file", dest="body_file_option", default=None, help="본문 파일 경로")


def _configure_list_comments(parser) -> None:
    parser.add_argument("owner")
    parser.add_argument("repo")
    parser.add_argument("number", type=int)


def _configure_edit_comment(parser) -> None:
    parser.add_argument("owner")
    parser.add_argument("repo")
    parser.add_argument("comment_id", type=int)
    parser.add_argument("body_file")


def _configure_delete_comment(parser) -> None:
    parser.add_argument("owner")
    parser.add_argument("repo")
    parser.add_argument("comment_id", type=int)


COMMANDS = [
    Command(name="add-comment", help="이슈 댓글 추가", run=cmd_add_comment,
            configure=_configure_add_comment),
    Command(name="list-comments", help="이슈/PR 댓글 목록", run=cmd_list_comments,
            configure=_configure_list_comments),
    Command(name="edit-comment", help="댓글 수정", run=cmd_edit_comment,
            configure=_configure_edit_comment),
    Command(name="delete-comment", help="댓글 삭제", run=cmd_delete_comment,
            configure=_configure_delete_comment),
]
