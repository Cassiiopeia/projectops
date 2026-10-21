"""네트워크 없는 서브커맨드: 이슈 문서 경로, 제목 정규화, 브랜치명, 커밋 틀."""
from __future__ import annotations

from common.emit import emit
from pro_github.registry import Command


def _commit_type_arg(value: str) -> str:
    from common.gh_branch import commit_type_arg
    return commit_type_arg(value)


def _date_arg(value: str) -> str:
    from common.gh_branch import date_arg
    return date_arg(value)


def cmd_get_output_path(args, api) -> int:
    # 경로 규칙은 common/paths.py 단일 소유 (#525·#623) — 이슈 문서도 직접 조립하지 않는다 (#822).
    # 새 이슈는 아직 번호가 없으므로 현재 브랜치의 이슈 번호를 빌려 쓰지 않고 일련번호를 붙인다.
    from common.gh_branch import strip_issue_decorations
    from common.paths import resolve_output_path
    # 파일명에는 이모지·[태그]를 넣지 않는다 — 태그가 제목에 붙어 `BugSkills_...` 가 되는 것을 막는다
    title = strip_issue_decorations(args.title) if args.title else None
    return emit(resolve_output_path("issue", title, use_issue_number=False, root=args.root))


def cmd_normalize_title(args, api) -> int:
    from common.title import normalize
    result = normalize(" ".join(args.title))
    return emit({"normalized": result, "summary": result})


def read_branch_name_values(values: list[str]) -> tuple:
    """[제목, 번호] · [번호, 제목] · [owner, repo, 제목, 번호] > (제목, 번호) | None (다른 명령처럼 owner repo 를 앞에 둬도 받는다)"""
    if len(values) == 4 and values[3].isdigit():
        return values[2], int(values[3])
    if len(values) == 2 and values[1].isdigit():
        return values[0], int(values[1])
    if len(values) == 2 and values[0].isdigit():
        return values[1], int(values[0])
    return None


def cmd_create_branch_name(args, api) -> int:
    from common.gh_branch import create_branch_name
    parsed = read_branch_name_values(args.values)
    if parsed is None:
        return emit({"ok": False, "code": "bad_args", "error": f"could not read a title and issue number: {args.values}",
                     "usage": "create-branch-name <title> <number> (or <owner> <repo> <title> <number>)"})
    issue_title, issue_number = parsed
    name = create_branch_name(issue_title, issue_number, args.date)
    return emit({"branch": name, "issue_number": issue_number, "summary": name})


def cmd_get_commit_template(args, api) -> int:
    # 커밋 스킬과 같은 해석 경로를 쓴다 — 이슈 생성 직후 보여주는 틀이 커밋 때와 갈라지지 않게
    from common.commit_style import render_for_issue, resolve_for_repo
    _, style = resolve_for_repo(getattr(args, "repo_root", None))
    template = render_for_issue(style, issue_title=args.issue_title, issue_url=args.issue_url,
                                commit_type=getattr(args, "commit_type", None),
                                scope=getattr(args, "scope", None) or "")
    return emit({"template": template, "source": style["source"], "warnings": style["warnings"],
                 "summary": template})


# ── 인자 ──

def _configure_get_output_path(parser) -> None:
    parser.add_argument("skill_id", nargs="?", default="issue", choices=["issue"])
    parser.add_argument("--title", help="issue title (emoji and tags allowed; it is normalized)")
    from common.paths import add_root_and_issue_args
    add_root_and_issue_args(parser, with_issue=False)


def _configure_normalize_title(parser) -> None:
    parser.add_argument("title", nargs="+")


def _configure_create_branch_name(parser) -> None:
    parser.add_argument("values", nargs="+", metavar="value",
                        help="<title> <number> or <owner> <repo> <title> <number>")
    parser.add_argument("--date", type=_date_arg, help="YYYYMMDD")


def _configure_get_commit_template(parser) -> None:
    parser.add_argument("issue_title")
    parser.add_argument("issue_url")
    # 생략하면 제목 태그에서 유도한다. 이슈는 기능인데 실제 작업이 버그 수정인
    # 경우처럼 태그와 내용이 다를 때만 직접 지정한다.
    parser.add_argument("--type", dest="commit_type", default=None, type=_commit_type_arg,
                       help="commit type (fix, docs, chore, ...). Default: inferred from the title tag")
    parser.add_argument("--scope", default=None, help="value for the {scope} placeholder")
    parser.add_argument("--repo-root", dest="repo_root", default=None,
                       help="repo root to read the format from (default: git root of the cwd, or the cwd outside git)")


COMMANDS = [
    Command(name="get-output-path", help="where to save the issue document (sequence number before the issue exists)", run=cmd_get_output_path,
            configure=_configure_get_output_path),
    Command(name="normalize-title", help="normalize a title", run=cmd_normalize_title,
            configure=_configure_normalize_title),
    Command(name="create-branch-name", help="build a branch name", run=cmd_create_branch_name,
            configure=_configure_create_branch_name),
    Command(name="get-commit-template", help="commit message template", run=cmd_get_commit_template,
            configure=_configure_get_commit_template),
]
