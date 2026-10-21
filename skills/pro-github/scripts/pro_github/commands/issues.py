"""이슈 서브커맨드: 조회·여러 건 조회·생성·목록·수정·닫기·다시 열기·제목 검색."""
from __future__ import annotations

from pathlib import Path

from common.emit import emit
from common.gh_client import GitHubAPIError
from pro_github.issue_followup import build_work_start_hints, rename_body_file_to_issue_number
from pro_github.registry import Command
from pro_github.responses import api_error, missing_pat, split_csv


def cmd_get_issue(args, api) -> int:
    pat = api.get_github_pat(args.owner, args.repo)
    if not pat:
        return missing_pat()
    try:
        issue = api.get_issue(args.owner, args.repo, args.number, pat)
        comments = api.get_issue_comments(args.owner, args.repo, args.number, pat) if args.with_comments else None
        return emit({
            "issue": issue,
            "comments": comments,
            "summary": f"#{issue['number']} {issue['state']} — {issue['title']}",
            "number": issue["number"],
            "title": issue["title"],
            "url": issue["url"],
            "html_url": issue["url"],
            "state": issue["state"],
            # 라벨 교체 전에 issue.labels 를 짐작하지 않게 최상위에도 둔다
            "labels": issue.get("labels", []),
            "assignees": issue.get("assignees", []),
            "body": issue.get("body", ""),
        })
    except GitHubAPIError as e:
        return api_error(e)


def cmd_get_issues(args, api) -> int:
    pat = api.get_github_pat(args.owner, args.repo)
    if not pat:
        return missing_pat()
    issues = []
    for raw in args.numbers:
        try:
            number = int(raw)
        except ValueError:
            issues.append({"number": raw, "error": "정수 아님", "code": "invalid_argument"})
            continue
        try:
            issues.append(api.get_issue(args.owner, args.repo, number, pat))
        except GitHubAPIError as e:
            issues.append({"number": number, "error": str(e), "code": f"github_api_{e.status_code}"})
    failed = [i for i in issues if "error" in i]
    if issues and len(failed) == len(issues):
        # 전부 실패했는데 ok:true 면 호출자가 없는 이슈를 있는 것으로 오인한다 (#699)
        return emit({
            "ok": False,
            "code": "all_failed",
            "error": f"{len(issues)}개 이슈 조회가 모두 실패했습니다",
            "count": len(issues),
            "issues": issues,
        })
    summary = f"{len(issues)}개 이슈 조회 완료"
    if failed:
        summary = f"{len(issues)}개 중 {len(failed)}개 조회 실패 (성공 {len(issues) - len(failed)}개)"
    return emit({"count": len(issues), "issues": issues, "summary": summary,
                 **({"failed_count": len(failed)} if failed else {})})


def cmd_create_issue(args, api) -> int:
    # 입력을 자격증명보다 먼저 본다. 파일명 오타는 PAT 없이도 알려줄 수 있는데,
    # PAT 를 먼저 보면 "PAT 없음"만 나와 PAT 를 채운 뒤에야 오타를 알게 된다.
    body_path = Path(args.body_file)
    if not body_path.exists():
        return emit({
            "ok": False,
            "code": "body_file_not_found",
            "error": f"본문 파일이 존재하지 않습니다: {args.body_file}",
            "path_attempted": str(body_path.resolve()),
        })
    pat = api.get_github_pat(args.owner, args.repo)
    if not pat:
        return missing_pat()
    body = body_path.read_text(encoding="utf-8")
    # 위치 인자와 --labels 를 둘 다 받는다 (다른 명령이 --labels 라 그대로 부르면 실패했다)
    labels = split_csv(",".join(filter(None, (args.labels, args.labels_option))))
    assignees = split_csv(args.assignees) if args.assignees else []
    try:
        result = api.create_issue(args.owner, args.repo, args.title, body, labels, pat, assignees)
    except GitHubAPIError as e:
        return api_error(e)
    applied = result.get("assignees", [])
    missing = [a for a in assignees if a not in applied]
    out = {**result, "summary": f"이슈 #{result.get('number')} 생성 완료", "body_length": len(body)}
    skipped_labels = out.pop("skipped_labels", [])
    if skipped_labels:
        out["label_warning"] = f"레포에 없어 무시된 라벨: {', '.join(skipped_labels)}"
    if missing:
        out["assignee_warning"] = (
            f"담당자 지정 일부 실패: {', '.join(missing)} (레포 협업자/권한 확인 필요). 이슈는 정상 생성됨."
        )
    _add_created_issue_followups(out, args, body_path)
    return emit(out)


def _add_created_issue_followups(out: dict, args, body_path: Path) -> None:
    """생성 직후 할 일: 로컬 문서 번호 맞추기(--rename-body-file) > 브랜치명·커밋 틀 > next"""
    if args.rename_body_file:
        renamed, warning = rename_body_file_to_issue_number(body_path, out["number"])
        out["body_file_renamed_to"] = str(renamed) if renamed else None
        if warning:
            out["rename_warning"] = warning
    try:
        out.update(build_work_start_hints(out.get("title") or args.title, out["number"], out["url"]))
    except Exception as error:  # 이슈는 이미 생성됨: 보조 정보 실패로 생성 응답을 잃지 않는다
        out.update({"branch": None, "commit_template": None, "hints_warning": f"{type(error).__name__}: {error}"})
    # 작업중 전환은 상태 라벨만 바꾸는 finish-issue (set-labels 는 type·area 라벨까지 지운다)
    out["next"] = (f"브랜치 {out['branch'] or '(create-branch-name 으로 생성)'} 생성 > "
                   f"finish-issue {args.owner} {args.repo} {out['number']} --outcome in-progress")


def cmd_list_issues(args, api) -> int:
    pat = api.get_github_pat(args.owner, args.repo)
    if not pat:
        return missing_pat()
    try:
        issues = api.list_issues(args.owner, args.repo, pat, state=args.state, labels=args.labels, limit=args.limit)
        # label/assignee 필터는 API 재호출 없이 여기서 후처리 (list_issues에 필드 있음)
        return emit({
            "count": len(issues),
            "issues": issues,
            "summary": f"{args.owner}/{args.repo} 이슈 {len(issues)}개 ({args.state})",
        })
    except GitHubAPIError as e:
        return api_error(e)


def cmd_update_issue(args, api) -> int:
    # 입력 먼저, 자격증명 나중 (cmd_create_issue 와 같은 이유).
    body = None
    body_file = args.body_file or args.body_file_positional
    if body_file:
        body_path = Path(body_file)
        if not body_path.exists():
            return emit({
                "ok": False,
                "code": "body_file_not_found",
                "error": f"수정용 본문 파일이 존재하지 않습니다: {body_file}",
                "path_attempted": str(body_path.resolve())
            })
        body = body_path.read_text(encoding="utf-8")

    pat = api.get_github_pat(args.owner, args.repo)
    if not pat:
        return missing_pat()
    labels = split_csv(args.labels) if args.labels else None
    assignees = split_csv(args.assignees) if args.assignees else None

    # 바꿀 값이 하나도 없으면 PATCH 하지 않고 알린다 — "수정 완료" 로 오보하지 않는다 (#699)
    if all(v is None for v in (args.title, body, args.state, labels, assignees)):
        return emit({
            "ok": False,
            "code": "nothing_to_update",
            "error": "바꿀 값이 없습니다 (--title/--body-file/--state/--labels/--assignees 중 하나 필요)",
        })

    try:
        result = api.update_issue(
            args.owner, args.repo, args.number, pat,
            title=args.title, body=body, state=args.state, labels=labels, assignees=assignees,
        )
        return emit({**result, "summary": f"#{args.number} 수정 완료"})
    except GitHubAPIError as e:
        return api_error(e)


def cmd_close_issue(args, api) -> int:
    pat = api.get_github_pat(args.owner, args.repo)
    if not pat:
        return missing_pat()
    try:
        # 완료(completed)와 취소(not_planned)를 GitHub 에서도 구분해 남긴다 (#819)
        result = api.update_issue(args.owner, args.repo, args.number, pat,
                              state="closed", state_reason=args.reason)
        return emit({**result, "state_reason": args.reason,
                     "summary": f"#{args.number} 닫음 ({args.reason})"})
    except GitHubAPIError as e:
        return api_error(e)


def cmd_reopen_issue(args, api) -> int:
    pat = api.get_github_pat(args.owner, args.repo)
    if not pat:
        return missing_pat()
    try:
        result = api.update_issue(args.owner, args.repo, args.number, pat, state="open")
        return emit({**result, "summary": f"#{args.number} 다시 열음"})
    except GitHubAPIError as e:
        return api_error(e)


def cmd_search_issues(args, api) -> int:
    pat = api.get_github_pat(args.owner, args.repo)
    if not pat:
        return missing_pat()
    keyword = " ".join(args.keywords)
    try:
        result = api.search_issues(args.owner, args.repo, keyword, pat)
        return emit({
            "count": len(result),
            "items": result,
            "summary": f"\"{keyword}\" 검색 {len(result)}건",
        })
    except GitHubAPIError as e:
        return api_error(e)


# ── 인자 ──

def _configure_get_issue(parser) -> None:
    parser.add_argument("owner")
    parser.add_argument("repo")
    parser.add_argument("number", type=int)
    parser.add_argument("--with-comments", action="store_true")


def _configure_get_issues(parser) -> None:
    parser.add_argument("owner")
    parser.add_argument("repo")
    parser.add_argument("numbers", nargs="+")


def _configure_create_issue(parser) -> None:
    parser.add_argument("owner")
    parser.add_argument("repo")
    parser.add_argument("title")
    parser.add_argument("body_file")
    # 라벨을 생략해도 된다 (템플릿 기본 라벨만 붙는다): 필수 위치 인자라 빠뜨리면 bad_args 가 났다 (#940)
    parser.add_argument("labels", nargs="?", default="", help="csv")
    parser.add_argument("--labels", dest="labels_option", default="", help="csv (위치 인자 labels 와 같다)")
    parser.add_argument("--assignees", help="담당자 csv")
    parser.add_argument("--rename-body-file", dest="rename_body_file", action="store_true",
                        help="본문 파일 YYYYMMDD_NNN_제목 의 NNN 을 실제 이슈 번호로 바꾼다")


def _configure_list_issues(parser) -> None:
    parser.add_argument("owner")
    parser.add_argument("repo")
    parser.add_argument("--state", choices=["open", "closed", "all"], default="open")
    parser.add_argument("--labels", default="", help="csv, 모두 가진 이슈만")
    parser.add_argument("--limit", type=int, default=50, help="최대 개수 (0이면 전부)")


def _configure_update_issue(parser) -> None:
    parser.add_argument("owner")
    parser.add_argument("repo")
    parser.add_argument("number", type=int)
    # 본문 파일은 위치 인자로도 받는다 (add-comment 와 같은 모양)
    parser.add_argument("body_file_positional", nargs="?", metavar="body_file", help="본문 파일 경로")
    parser.add_argument("--title")
    parser.add_argument("--state", choices=["open", "closed"])
    parser.add_argument("--labels", help="csv (전체 교체)")
    parser.add_argument("--assignees", help="csv")
    parser.add_argument("--body-file", help="본문 파일 경로")


def _configure_close_issue(parser) -> None:
    parser.add_argument("owner")
    parser.add_argument("repo")
    parser.add_argument("number", type=int)
    parser.add_argument("--reason", choices=["completed", "not_planned"], default="completed",
                       help="완료=completed(기본), 취소=not_planned")


def _configure_reopen_issue(parser) -> None:
    parser.add_argument("owner")
    parser.add_argument("repo")
    parser.add_argument("number", type=int)


def _configure_search_issues(parser) -> None:
    parser.add_argument("owner")
    parser.add_argument("repo")
    parser.add_argument("keywords", nargs="+")


COMMANDS = [
    Command(name="get-issue", help="이슈 조회", run=cmd_get_issue,
            configure=_configure_get_issue),
    Command(name="get-issues", help="여러 이슈 한 번에 조회", run=cmd_get_issues,
            configure=_configure_get_issues),
    Command(name="create-issue", help="이슈 생성", run=cmd_create_issue,
            configure=_configure_create_issue),
    Command(name="list-issues", help="이슈 목록", run=cmd_list_issues,
            configure=_configure_list_issues),
    Command(name="update-issue", help="이슈 수정", run=cmd_update_issue,
            configure=_configure_update_issue),
    Command(name="close-issue", help="이슈 닫기", run=cmd_close_issue,
            configure=_configure_close_issue),
    Command(name="reopen-issue", help="이슈 다시 열기", run=cmd_reopen_issue,
            configure=_configure_reopen_issue),
    Command(name="search-issues", help="이슈 검색", run=cmd_search_issues,
            configure=_configure_search_issues),
]
