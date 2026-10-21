"""`logs` — 서버 로그를 본다."""
from __future__ import annotations

import os
import re
import subprocess

from common.access import load_access

import credentials

from pro_launch.registry import Command
from pro_launch.runtime.context import project_root, state_home
from pro_launch.runtime.creds import cred_name_for, load_cred
from pro_launch.runtime.output import out, set_area, use_access


def cmd_logs(args) -> int:
    """서버 로그를 본다. **보는 방법은 적어 둔 것을 쓴다** — 맞히려 들지 않는다."""
    set_area("server", project_root(args))
    root = project_root(args)
    state_home(root)
    command = args.command
    saved = None
    if not command:
        saved = load_access(root).get(args.profile or "logs")
        command = saved.get("command") if isinstance(saved, dict) else saved
        if command:
            use_access(root, args.profile or "logs")
    cred, err = load_cred(cred_name_for(args, saved))
    if err:
        return out(err)
    cred_env = credentials.env_for(cred) if cred else {}
    if not command:
        return out({"ok": False, "code": "no_log_command",
                    "error": "Do not know how to read the logs",
                    "hint": ('Read the code to find out, then record it. e.g. '
                             'access set --key logs --json \'{"command":"ssh u@h \\"docker logs --tail 200 app\\""}\'')})
    # tail·grep 은 파이프로 잇지 않고 파이썬에서 건다 (#704). 파이프 끝 종료코드만 보면
    # 앞 명령의 실패(없는 명령·ssh 접속 거부)가 가려져 "로그 0줄 성공"으로 보고된다.
    try:
        r = subprocess.run(["bash", "-lc", command], capture_output=True, text=True,
                           timeout=args.timeout, env=dict(os.environ, **cred_env))
    except subprocess.TimeoutExpired:
        return out({"ok": False, "code": "logs_timeout", "error": f"No response ({args.timeout}s)"})
    if cred:                                  # 서버가 비밀번호를 되풀이해 찍어도 기록에 남지 않게
        r.stdout = credentials.mask(r.stdout, cred)
        r.stderr = credentials.mask(r.stderr, cred)
    err = (r.stderr or "").strip()
    # 저장된 명령 안에 grep 이 있으면 매치 0건이 종료코드 1 이다 — 출력·오류가 모두 비면 성공으로 본다
    failed = r.returncode != 0 and not (r.returncode == 1 and not err and not (r.stdout or "").strip())
    if failed:
        resp = {"ok": False, "code": "logs_failed", "exit_code": r.returncode,
                "lines": [], "error": err[:500] or f"exit code {r.returncode}",
                "summary": f"Log command failed (exit code {r.returncode}) — this does not mean there are no logs",
                "next": "Fix the connection or command from error (access show --key logs)"}
        return out(resp)
    lines = (r.stdout or "").splitlines()
    if args.grep:
        try:
            pat = re.compile(args.grep, re.IGNORECASE)
        except re.error:
            pat = re.compile(re.escape(args.grep), re.IGNORECASE)   # 정규식이 아니면 글자 그대로
        lines = [l for l in lines if pat.search(l)]
    if args.tail:
        lines = lines[-int(args.tail):]
    return out({"ok": True, "code": "ok", "lines": lines,
                "error": err[:500] or None, "summary": f"{len(lines)} lines"})


def configure_logs(p) -> None:
    p.add_argument("--root", default=".")
    p.add_argument("--profile", default=None, help="Which access key to use (default logs)")
    p.add_argument("--command", default=None, help="Ad hoc command to run")
    p.add_argument("--cred", default=None,
                   help="Pass a saved credential as CRED_HOST · CRED_USER · SSHPASS etc. environment variables (cred list)")
    p.add_argument("--tail", type=int, default=200)
    p.add_argument("--grep", default=None)
    p.add_argument("--timeout", type=int, default=60)


COMMANDS = [
    Command(name="logs", help="Read server logs (record how in access)", run=cmd_logs,
            configure=configure_logs),
]
