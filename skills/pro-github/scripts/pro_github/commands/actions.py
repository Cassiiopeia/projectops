"""Actions 서브커맨드: actions (진단: show-run|joblog|list-failed|resolve-pr|resolve-branch, 실행: runs|dispatch|rerun|wait|cancel)."""
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
                           "error": f"{name} is required",
                           "hint": f"actions {args.sub} {args.owner} {args.repo} <{name}>"})
    try:
        return int(raw), None
    except (TypeError, ValueError):
        return None, emit({"ok": False, "code": "bad_argument",
                           "error": f"{name} must be a number: {raw!r}",
                           "hint": f"actions {args.sub} {args.owner} {args.repo} <{name}>"})


# 한 번 호출로 기다릴 수 있는 최대 시간 (하네스의 명령 시간 상한 안에서 끝나게)
_WAIT_MAX_SECONDS = 540

# actions 의 동작 이름 (첫 위치 인자)
ACTIONS_SUBCOMMANDS = ("show-run", "joblog", "list-failed", "resolve-pr", "resolve-branch",
                       "runs", "dispatch", "rerun", "wait", "cancel")


def _misplaced_subcommand_response(args) -> int:
    """첫 인자가 동작 이름이 아님 > 뒤에 동작 이름이 있으면 올바른 순서 안내, 없으면 목록 안내"""
    import difflib
    given = [args.sub, args.owner, args.repo, args.arg, *args.extra_values]
    given = [value for value in given if value is not None]
    found = next((value for value in given[1:] if value in ACTIONS_SUBCOMMANDS), None)
    if found:
        rest = [value for value in given if value != found]
        return emit({"ok": False, "code": "bad_args",
                     "error": f"the action name goes right after actions: {found}",
                     "usage": "actions <action> <owner> <repo> [value]",
                     "next": "actions " + " ".join([found, *rest])})
    return emit({"ok": False, "code": "bad_args",
                 "error": f"unknown action: {args.sub}",
                 "usage": "actions <action> <owner> <repo> [value]",
                 "did_you_mean": difflib.get_close_matches(args.sub, ACTIONS_SUBCOMMANDS, n=3, cutoff=0.5),
                 "available_subcommands": list(ACTIONS_SUBCOMMANDS),
                 "next": f"put the action name first, e.g. actions show-run {args.owner} {args.repo} <run_id>"})


def _read_run_ids(args) -> tuple:
    """wait 대상 run id 여러 개 > ([정수], None) / (None, 오류 응답)"""
    first_run_id, err = read_numeric_argument(args, "run_id")
    if err is not None:
        return None, err
    run_ids = [first_run_id]
    for raw in args.extra_values:
        if not str(raw).isdigit():
            return None, emit({"ok": False, "code": "bad_argument", "error": f"run_id must be a number: {raw!r}",
                               "hint": f"actions wait {args.owner} {args.repo} <run_id> [run_id …]"})
        run_ids.append(int(raw))
    return run_ids, None


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
    # 인자 순서 오류는 PAT 없이도 알려 준다
    if args.sub not in ACTIONS_SUBCOMMANDS:
        return _misplaced_subcommand_response(args)
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
                "summary": f"Run {run_id} status: {result.get('status')} / {result.get('conclusion')}",
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
                if e.status_code == 404 and _is_run_id(api, args, job_id, pat):
                    return emit({"ok": False, "code": "run_id_given",
                                 "error": f"{job_id} is a run id, not a job id",
                                 "next": f"actions show-run {args.owner} {args.repo} {job_id}  # returns the failed job ids"})
                if e.status_code in (404, 410):
                    return emit({"ok": False, "code": "log_expired",
                                 "error": f"Job {job_id} log is missing or past its retention period ({e.status_code})",
                                 "next": f"actions show-run {args.owner} {args.repo} <run_id>  # failed step names are still available"})
                raise
            return emit({
                **result,
                "summary": f"Job {job_id} log: {result.get('matched_count')} match(es) ({result.get('mode')})",
                "next": None if result.get("matched_count") else "no matches; pass --grep, or save the full log with --out and read it",
            })
        elif args.sub == "runs":
            result = api.list_runs(args.owner, args.repo, pat, workflow=args.arg, branch=args.on_branch,
                                   status=args.status, limit=args.limit)
            return emit({"runs": result, "count": len(result),
                         "summary": f"{len(result)} run(s)" + (f" ({args.arg})" if args.arg else ""),
                         "next": f"actions wait {args.owner} {args.repo} {result[0]['run_id']}" if result else None})
        elif args.sub == "dispatch":
            if not args.arg:
                return emit({"ok": False, "code": "missing_argument", "error": "workflow file name is required",
                             "hint": f"actions dispatch {args.owner} {args.repo} <workflow.yaml> --ref <branch> [--input k=v]"})
            inputs, bad = _parse_inputs(args.input)
            if bad:
                return emit({"ok": False, "code": "bad_argument", "error": f"--input must be key=value: {bad}"})
            result = api.dispatch_workflow(args.owner, args.repo, args.arg, args.ref, inputs, pat)
            return emit({**result, "summary": f"requested a run of {args.arg} ({args.ref})",
                         "next": f"actions runs {args.owner} {args.repo} {args.arg} --on-branch {args.ref}  # the new run shows up after a few seconds"})
        elif args.sub == "rerun":
            run_id, err = read_numeric_argument(args, "run_id")
            if err is not None:
                return err
            result = api.rerun_run(args.owner, args.repo, run_id, pat, failed_only=args.failed_only)
            return emit({**result, "summary": f"requested a rerun of Run {run_id}",
                         "next": f"actions wait {args.owner} {args.repo} {run_id}"})
        elif args.sub == "wait":
            run_ids, err = _read_run_ids(args)
            if err is not None:
                return err
            timeout_seconds = min(max(args.timeout, 0), _WAIT_MAX_SECONDS)
            if len(run_ids) > 1:
                return _emit_wait_many(args, api, run_ids, pat, timeout_seconds)
            run_id = run_ids[0]
            result = api.wait_for_run(args.owner, args.repo, run_id, pat, timeout_seconds)
            return emit({
                **result,
                "summary": (f"Run {run_id} {result.get('conclusion')}" if result["finished"]
                            else f"Run {run_id} still {result.get('status')} (waited {result['waited_seconds']}s)"),
                "next": (f"actions joblog {args.owner} {args.repo} {result['failed_job_ids'][0]}"
                         if result.get("failed_job_ids") else None) if result["finished"]
                        else f"actions wait {args.owner} {args.repo} {run_id}",
            })
        elif args.sub == "cancel":
            run_id, err = read_numeric_argument(args, "run_id")
            if err is not None:
                return err
            result = api.cancel_run(args.owner, args.repo, run_id, pat, force=args.force)
            return emit({**result, "summary": f"requested {'a forced ' if args.force else ''}cancel of Run {run_id}",
                         "next": f"actions wait {args.owner} {args.repo} {run_id}  # confirm the cancel took effect"})
        elif args.sub == "list-failed":
            if args.arg is not None:
                return _emit_failed_jobs_of_run(args, api, pat)
            result = api.list_failed_runs(args.owner, args.repo, pat, limit=args.limit)
            if args.workflow:
                result = [run for run in result if (run.get("path") or "").endswith(args.workflow)]
            return emit({
                "runs": result,
                "count": len(result),
                "summary": f"{len(result)} recently failed run(s)" + (f" ({args.workflow})" if args.workflow else ""),
            })
        elif args.sub == "resolve-pr":
            pr_number, err = read_numeric_argument(args, "pr_number")
            if err is not None:
                return err
            result = api.resolve_pr_runs(args.owner, args.repo, pr_number, pat)
            return emit({
                **result,
                "summary": f"found {len(result.get('runs', []))} run(s) linked to PR #{pr_number}",
                "next": f"actions show-run {args.owner} {args.repo} {result['runs'][0]['run_id']}" if result.get("runs") else None
            })
        elif args.sub == "resolve-branch":
            if not args.arg:
                return emit({"ok": False, "code": "missing_argument", "error": "branch is required",
                             "hint": f"actions resolve-branch {args.owner} {args.repo} <branch>"})
            result = api.resolve_branch_runs(args.owner, args.repo, args.arg, pat, limit=args.limit)
            return emit({
                "runs": result,
                "count": len(result),
                "summary": f"{len(result)} run(s) on branch {args.arg}",
                "next": f"actions show-run {args.owner} {args.repo} {result[0]['run_id']}" if result else None
            })
        return emit({"ok": False, "code": "unknown_subcommand", "error": f"unknown: {args.sub}"})
    except GitHubAPIError as e:
        return api_error(e)


def _is_run_id(api, args, value: int, pat: str) -> bool:
    """job 로그 404 일 때: 그 숫자가 run id 인지 (run 조회가 되면 run id)"""
    try:
        api.get_run(args.owner, args.repo, value, pat)
        return True
    except GitHubAPIError:
        return False


def _emit_failed_jobs_of_run(args, api, pat: str) -> int:
    """list-failed <run_id>: 그 run 의 실패 job 만"""
    run_id, err = read_numeric_argument(args, "run_id")
    if err is not None:
        return err
    run = api.get_run(args.owner, args.repo, run_id, pat)
    failed_jobs = [job for job in run.get("jobs", []) if job.get("conclusion") == "failure"]
    return emit({
        "run_id": run_id, "status": run.get("status"), "conclusion": run.get("conclusion"), "url": run.get("url"),
        "jobs": failed_jobs, "count": len(failed_jobs),
        "summary": f"Run {run_id}: {len(failed_jobs)} failed job(s)",
        "next": f"actions joblog {args.owner} {args.repo} {failed_jobs[0]['job_id']}" if failed_jobs else None,
    })


def _emit_wait_many(args, api, run_ids: list, pat: str, timeout_seconds: int) -> int:
    """여러 run 을 모두 끝날 때까지 기다린 결과"""
    result = api.wait_for_runs(args.owner, args.repo, run_ids, pat, timeout_seconds)
    failed_job_ids = [job_id for run in result["runs"] for job_id in run.get("failed_job_ids", [])]
    if not result["finished"]:
        next_step = f"actions wait {args.owner} {args.repo} " + " ".join(map(str, result["pending_run_ids"]))
    elif failed_job_ids:
        next_step = f"actions joblog {args.owner} {args.repo} {failed_job_ids[0]}"
    else:
        next_step = None
    conclusions = ", ".join(f"{run.get('run_id')} {run.get('conclusion') or run.get('status')}" for run in result["runs"])
    return emit({**result, "failed_job_ids": failed_job_ids,
                 "summary": (f"all {len(run_ids)} run(s) finished: {conclusions}" if result["finished"]
                             else f"{len(result['pending_run_ids'])} run(s) still running (waited {result['waited_seconds']}s)"),
                 "next": next_step})


# ── 인자 ──

def _configure_actions(parser) -> None:
    # choices 를 걸지 않는다: 인자 순서를 바꿔 부른 경우 argparse 대신 핸들러가 올바른 순서를 안내한다
    parser.add_argument("sub", metavar="{" + ",".join(ACTIONS_SUBCOMMANDS) + "}")
    parser.add_argument("owner")
    parser.add_argument("repo")
    # ⚠️ 위치 인자는 **하나**여야 한다 (#622). argparse 는 값을 **왼쪽부터** 채우므로
    # run_id·job_id·pr_number·branch 를 각자 선택 인자로 두면 어떤 서브커맨드든 첫 값이 run_id 가 된다.
    parser.add_argument("arg", nargs="?",
                      help="run_id, job_id, pr_number or branch, depending on the action")
    # wait 에 run id 를 더 줄 때만 쓰는 뒤쪽 값 (첫 값은 언제나 arg)
    parser.add_argument("extra_values", nargs="*", help="wait: more run_ids to wait for together")
    parser.add_argument("--grep", default=None,
                        help="joblog search regex (case-insensitive). Default: ##[error] lines and the output lines before them (script source excluded)")
    parser.add_argument("--out", default=None, help="joblog: save the full log to this file")
    parser.add_argument("--workflow", default=None, help="list-failed: only runs of this workflow file")
    parser.add_argument("--on-branch", "--branch", dest="on_branch", default=None, help="runs: only runs on this branch")
    parser.add_argument("--status", default=None, help="runs: queued · in_progress · completed · failure ...")
    parser.add_argument("--ref", default="develop", help="dispatch: branch or tag to run on")
    parser.add_argument("--input", action="append", default=None, metavar="KEY=VALUE", help="dispatch: workflow input (repeatable)")
    parser.add_argument("--failed-only", dest="failed_only", action="store_true", help="rerun: failed jobs only")
    parser.add_argument("--force", action="store_true", help="cancel: force cancel (also stops always() steps)")
    parser.add_argument("--timeout", type=int, default=300, help="wait: max seconds to wait (up to 540)")
    parser.add_argument("--tail", type=int, default=30, help="Log line count")
    parser.add_argument("--limit", type=int, default=10, help="Run count limit")


COMMANDS = [
    Command(name="actions", help="GitHub Actions diagnosis and runs (show-run, joblog, list-failed, runs, wait, cancel, ...)", run=cmd_actions,
            configure=_configure_actions),
]
