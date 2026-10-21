"""`local` — 저장된 자격증명으로 이 맥에서 sudo 명령을 실행한다."""
from __future__ import annotations

import shutil
import subprocess

import credentials

from pro_launch.registry import Command
from pro_launch.runtime.creds import load_cred
from pro_launch.runtime.output import out


def cmd_local(args) -> int:
    """저장된 자격증명으로 이 맥에서 sudo 명령을 실행한다 (#784).

    비밀번호는 `sudo -S` 의 표준입력으로만 넘긴다 — 명령줄(ps)·응답·로그에 남지 않는다.
    kind 가 local 인 자격증명만 쓴다: 서버 ssh 비밀번호로 이 맥에 sudo 를 시도하면 안 된다.
    """
    if not args.cred:
        return out({"ok": False, "code": "cred_required", "error": "--cred is required",
                    "next": "cred list  # pick one with kind local. If none, the user runs cred set --name <name> --prompt in a terminal"})
    cred, err = load_cred(args.cred)
    if err:
        return out(err)
    if cred.get("kind") != "local":
        return out({"ok": False, "code": "cred_not_local",
                    "error": f"'{args.cred}' is not for this Mac (kind: local) — a server password is never used for sudo on this Mac"})
    password = cred.get("sudo_password")
    if not password:
        return out({"ok": False, "code": "sudo_password_missing", "error": f"'{args.cred}' has no sudo_password",
                    "next": f"The user runs in a terminal: launch_cli.py cred set --name {args.cred} --prompt"})
    command = list(args.command or [])
    if not command:
        return out({"ok": False, "code": "command_required", "error": "No command to run",
                    "next": f"local sudo --cred {args.cred} -- <command> [args...]"})
    if not shutil.which("sudo"):
        return out({"ok": False, "code": "sudo_missing", "error": "sudo not found"})
    try:
        r = subprocess.run(["sudo", "-S", "-p", "", *command], input=str(password) + "\n",
                           capture_output=True, text=True, timeout=args.timeout)
    except subprocess.TimeoutExpired:
        return out({"ok": False, "code": "sudo_timeout", "error": f"No response ({args.timeout}s)"})
    stdout = credentials.mask(r.stdout, cred)
    stderr = credentials.mask(r.stderr, cred)
    ok = r.returncode == 0
    return out({"ok": ok, "code": "ok" if ok else "sudo_failed", "exit_code": r.returncode,
                "stdout": stdout[:args.max_output], "stderr": stderr.strip()[:1000] or None,
                "truncated": len(stdout) > args.max_output,
                "summary": f"{args.cred}: sudo {command[0]} " + ("succeeded" if ok else f"failed (exit code {r.returncode})"),
                "next": None if ok else "Fix the command from stderr. If the password is wrong, the user saves it again with cred set --name <name> --prompt"})


def configure_local(p) -> None:
    p.add_argument("action", choices=["sudo"])
    p.add_argument("--cred", default=None, help="Name of a credential with kind local (cred list)")
    p.add_argument("--timeout", type=int, default=300)
    p.add_argument("--max-output", dest="max_output", type=int, default=20000)
    # 실행할 명령은 `--` 뒤에 둔다. main() 이 파서 전에 잘라 args.command 로 넣는다.


COMMANDS = [
    Command(name="local", help="Run a sudo command on this Mac with a saved credential", run=cmd_local,
            configure=configure_local, tail_dest="command"),
]
