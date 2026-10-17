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
    return emit(resolve_output_path("issue", title, use_issue_number=False))


def cmd_normalize_title(args, api) -> int:
    from common.title import normalize
    result = normalize(" ".join(args.title))
    return emit({"normalized": result, "summary": result})


def cmd_create_branch_name(args, api) -> int:
    from common.gh_branch import create_branch_name
    name = create_branch_name(args.issue_title, args.issue_number, args.date)
    return emit({"branch": name, "summary": name})


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
    parser.add_argument("--title", help="이슈 제목 (이모지·태그 포함 가능, 정규화된다)")


def _configure_normalize_title(parser) -> None:
    parser.add_argument("title", nargs="+")


def _configure_create_branch_name(parser) -> None:
    parser.add_argument("issue_title")
    parser.add_argument("issue_number", type=int)
    parser.add_argument("--date", type=_date_arg, help="YYYYMMDD")


def _configure_get_commit_template(parser) -> None:
    parser.add_argument("issue_title")
    parser.add_argument("issue_url")
    # 생략하면 제목 태그에서 유도한다. 이슈는 기능인데 실제 작업이 버그 수정인
    # 경우처럼 태그와 내용이 다를 때만 직접 지정한다.
    parser.add_argument("--type", dest="commit_type", default=None, type=_commit_type_arg,
                       help="커밋 타입 (fix·docs·chore 등). 생략하면 제목 태그에서 유도")
    parser.add_argument("--scope", default=None, help="{scope} 자리표시자에 넣을 값")
    parser.add_argument("--repo-root", dest="repo_root", default=None,
                       help="형식을 찾을 레포 루트 (생략하면 cwd 의 git 루트, git 이 아니면 cwd)")


COMMANDS = [
    Command(name="get-output-path", help="이슈 문서 저장 경로 (등록 전 일련번호)", run=cmd_get_output_path,
            configure=_configure_get_output_path),
    Command(name="normalize-title", help="제목 정규화", run=cmd_normalize_title,
            configure=_configure_normalize_title),
    Command(name="create-branch-name", help="브랜치명 생성", run=cmd_create_branch_name,
            configure=_configure_create_branch_name),
    Command(name="get-commit-template", help="커밋 메시지 템플릿", run=cmd_get_commit_template,
            configure=_configure_get_commit_template),
]
