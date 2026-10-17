"""Actions 진단 서브커맨드: actions (show-run|joblog|list-failed|resolve-pr|resolve-branch)."""
from __future__ import annotations

from common.emit import emit
from common.gh_client import GitHubAPIError
from pro_github.registry import Command
from pro_github.responses import api_error, missing_pat


def read_numeric_argument(args, name: str):
    """위치 인자를 숫자로 읽는다. 없거나 숫자가 아니면 그 사실을 말해 준다.

    파서에서 `type=int` 로 걸면 argparse 가 무엇이 잘못됐는지 못 알려준 채
    죽는다 (#622 에서 `invalid int value: 'develop'` 이 그랬다).
    """
    raw = args.arg
    if raw is None:
        return None, emit({"ok": False, "code": "missing_argument",
                           "error": f"{name} 필요",
                           "hint": f"actions {args.sub} {args.owner} {args.repo} <{name}>"})
    try:
        return int(raw), None
    except (TypeError, ValueError):
        return None, emit({"ok": False, "code": "bad_argument",
                           "error": f"{name} 는 숫자여야 합니다: {raw!r}",
                           "hint": f"actions {args.sub} {args.owner} {args.repo} <{name}>"})


def cmd_actions(args, api) -> int:
    pat = api.get_github_pat(args.owner, args.repo)
    if not pat:
        return missing_pat()
    try:
        if args.sub == "show-run":
            run_id, err = read_numeric_argument(args, "run_id")
            if err is not None:
                return err
            result = api.get_run(args.owner, args.repo, run_id, pat)
            return emit({
                **result,
                "summary": f"Run {run_id} 상태: {result.get('status')} / {result.get('conclusion')}",
                "next": f"actions joblog {args.owner} {args.repo} {result['failed_job_ids'][0]}" if result.get("failed_job_ids") else None
            })
        elif args.sub == "joblog":
            job_id, err = read_numeric_argument(args, "job_id")
            if err is not None:
                return err
            result = api.get_job_log(args.owner, args.repo, job_id, pat, grep=args.grep, tail=args.tail)
            return emit({
                **result,
                "summary": f"Job {job_id} 로그 {result.get('matched_count')}건 검색됨"
            })
        elif args.sub == "list-failed":
            result = api.list_failed_runs(args.owner, args.repo, pat, limit=args.limit)
            return emit({
                "runs": result,
                "count": len(result),
                "summary": f"최근 실패한 run {len(result)}개"
            })
        elif args.sub == "resolve-pr":
            pr_number, err = read_numeric_argument(args, "pr_number")
            if err is not None:
                return err
            result = api.resolve_pr_runs(args.owner, args.repo, pr_number, pat)
            return emit({
                **result,
                "summary": f"PR #{pr_number}에 연결된 run {len(result.get('runs', []))}개 조회됨",
                "next": f"actions show-run {args.owner} {args.repo} {result['runs'][0]['run_id']}" if result.get("runs") else None
            })
        elif args.sub == "resolve-branch":
            if not args.arg:
                return emit({"ok": False, "code": "missing_argument", "error": "branch 필요",
                             "hint": f"actions resolve-branch {args.owner} {args.repo} <branch>"})
            result = api.resolve_branch_runs(args.owner, args.repo, args.arg, pat, limit=args.limit)
            return emit({
                "runs": result,
                "count": len(result),
                "summary": f"브랜치 {args.arg}의 run {len(result)}개",
                "next": f"actions show-run {args.owner} {args.repo} {result[0]['run_id']}" if result else None
            })
        return emit({"ok": False, "code": "unknown_subcommand", "error": f"알 수 없음: {args.sub}"})
    except GitHubAPIError as e:
        return api_error(e)


# ── 인자 ──

def _configure_actions(parser) -> None:
    parser.add_argument("sub", choices=["show-run", "joblog", "list-failed", "resolve-pr", "resolve-branch"])
    parser.add_argument("owner")
    parser.add_argument("repo")
    # ⚠️ 위치 인자는 **하나**여야 한다 (#622). argparse 는 값을 **왼쪽부터** 채우므로
    # run_id·job_id·pr_number·branch 를 각자 선택 인자로 두면 어떤 서브커맨드든 첫 값이 run_id 가 된다.
    parser.add_argument("arg", nargs="?",
                      help="서브커맨드에 따라 run_id · job_id · pr_number · branch")
    parser.add_argument("--grep", default="error", help="Filter logs")
    parser.add_argument("--tail", type=int, default=30, help="Log line count")
    parser.add_argument("--limit", type=int, default=10, help="Run count limit")


COMMANDS = [
    Command(name="actions", help="GitHub Actions 로그 관리", run=cmd_actions,
            configure=_configure_actions),
]
