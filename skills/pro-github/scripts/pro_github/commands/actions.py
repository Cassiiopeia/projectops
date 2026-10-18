"""Actions 서브커맨드: actions (진단: show-run|joblog|list-failed|resolve-pr|resolve-branch, 실행: runs|dispatch|rerun|wait)."""
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


# 한 번 호출로 기다릴 수 있는 최대 시간 (하네스의 명령 시간 상한 안에서 끝나게)
_WAIT_MAX_SECONDS = 540


def _parse_inputs(pairs):
    """["a=1", "b=x=y"] > ({"a": "1", "b": "x=y"}, None). 형식이 틀리면 (None, 틀린 값)"""
    parsed = {}
    for pair in pairs or []:
        key, separator, value = pair.partition("=")
        if not separator or not key:
            return None, pair
        parsed[key] = value
    return parsed, None


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
            try:
                result = api.get_job_log(args.owner, args.repo, job_id, pat, grep=args.grep, tail=args.tail,
                                         save_to=args.out)
            except GitHubAPIError as e:
                if e.status_code in (404, 410):
                    return emit({"ok": False, "code": "log_expired",
                                 "error": f"Job {job_id} 로그가 없거나 보존 기간이 지났다 ({e.status_code})",
                                 "next": f"actions show-run {args.owner} {args.repo} <run_id>  # 실패 step 이름은 남아 있다"})
                raise
            return emit({
                **result,
                "summary": f"Job {job_id} 로그 {result.get('matched_count')}건 검색됨",
                "next": None if result.get("matched_count") else "일치가 없다 — --grep 을 바꾸거나 --out 파일로 전체를 받아 직접 본다",
            })
        elif args.sub == "runs":
            result = api.list_runs(args.owner, args.repo, pat, workflow=args.arg, branch=args.branch,
                                   status=args.status, limit=args.limit)
            return emit({"runs": result, "count": len(result),
                         "summary": f"run {len(result)}개" + (f" ({args.arg})" if args.arg else ""),
                         "next": f"actions wait {args.owner} {args.repo} {result[0]['run_id']}" if result else None})
        elif args.sub == "dispatch":
            if not args.arg:
                return emit({"ok": False, "code": "missing_argument", "error": "workflow 파일명 필요",
                             "hint": f"actions dispatch {args.owner} {args.repo} <workflow.yaml> --ref <브랜치> [--input k=v]"})
            inputs, bad = _parse_inputs(args.input)
            if bad:
                return emit({"ok": False, "code": "bad_argument", "error": f"--input 은 key=value 형식이다: {bad}"})
            result = api.dispatch_workflow(args.owner, args.repo, args.arg, args.ref, inputs, pat)
            return emit({**result, "summary": f"{args.arg} 실행 요청 ({args.ref})",
                         "next": f"actions runs {args.owner} {args.repo} {args.arg} --branch {args.ref}  # 새 run 이 보일 때까지 몇 초"})
        elif args.sub == "rerun":
            run_id, err = read_numeric_argument(args, "run_id")
            if err is not None:
                return err
            result = api.rerun_run(args.owner, args.repo, run_id, pat, failed_only=args.failed_only)
            return emit({**result, "summary": f"Run {run_id} 재실행 요청",
                         "next": f"actions wait {args.owner} {args.repo} {run_id}"})
        elif args.sub == "wait":
            run_id, err = read_numeric_argument(args, "run_id")
            if err is not None:
                return err
            result = api.wait_for_run(args.owner, args.repo, run_id, pat, min(max(args.timeout, 0), _WAIT_MAX_SECONDS))
            return emit({
                **result,
                "summary": (f"Run {run_id} {result.get('conclusion')}" if result["finished"]
                            else f"Run {run_id} 아직 {result.get('status')} ({result['waited_seconds']}초 기다림)"),
                "next": (f"actions joblog {args.owner} {args.repo} {result['failed_job_ids'][0]}"
                         if result.get("failed_job_ids") else None) if result["finished"]
                        else f"actions wait {args.owner} {args.repo} {run_id}",
            })
        elif args.sub == "list-failed":
            result = api.list_failed_runs(args.owner, args.repo, pat, limit=args.limit)
            if args.workflow:
                result = [run for run in result if (run.get("path") or "").endswith(args.workflow)]
            return emit({
                "runs": result,
                "count": len(result),
                "summary": f"최근 실패한 run {len(result)}개" + (f" ({args.workflow})" if args.workflow else ""),
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
    parser.add_argument("sub", choices=["show-run", "joblog", "list-failed", "resolve-pr", "resolve-branch",
                                        "runs", "dispatch", "rerun", "wait"])
    parser.add_argument("owner")
    parser.add_argument("repo")
    # ⚠️ 위치 인자는 **하나**여야 한다 (#622). argparse 는 값을 **왼쪽부터** 채우므로
    # run_id·job_id·pr_number·branch 를 각자 선택 인자로 두면 어떤 서브커맨드든 첫 값이 run_id 가 된다.
    parser.add_argument("arg", nargs="?",
                      help="서브커맨드에 따라 run_id · job_id · pr_number · branch")
    parser.add_argument("--grep", default="error", help="Filter logs (정규식 가능: 'error|failed', 대소문자 무시)")
    parser.add_argument("--out", default=None, help="joblog: 전체 로그를 이 파일에 저장")
    parser.add_argument("--workflow", default=None, help="list-failed: 이 워크플로우 파일의 run 만")
    parser.add_argument("--branch", default=None, help="runs: 이 브랜치의 run 만")
    parser.add_argument("--status", default=None, help="runs: queued · in_progress · completed · failure ...")
    parser.add_argument("--ref", default="develop", help="dispatch: 실행할 브랜치/태그")
    parser.add_argument("--input", action="append", default=None, metavar="KEY=VALUE", help="dispatch: workflow 입력 (여러 번 가능)")
    parser.add_argument("--failed-only", dest="failed_only", action="store_true", help="rerun: 실패한 job 만")
    parser.add_argument("--timeout", type=int, default=300, help="wait: 최대 대기 초 (최대 540)")
    parser.add_argument("--tail", type=int, default=30, help="Log line count")
    parser.add_argument("--limit", type=int, default=10, help="Run count limit")


COMMANDS = [
    Command(name="actions", help="GitHub Actions 로그 관리", run=cmd_actions,
            configure=_configure_actions),
]
