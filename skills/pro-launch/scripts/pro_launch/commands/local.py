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
        return out({"ok": False, "code": "cred_required", "error": "--cred 가 필요합니다",
                    "next": "cred list  # kind 가 local 인 것을 고른다. 없으면 사용자가 터미널에서 cred set --name 이름 --prompt"})
    cred, err = load_cred(args.cred)
    if err:
        return out(err)
    if cred.get("kind") != "local":
        return out({"ok": False, "code": "cred_not_local",
                    "error": f"'{args.cred}' 는 이 맥용(kind: local)이 아닙니다 — 서버 비밀번호로 이 맥에 sudo 를 쓰지 않습니다"})
    password = cred.get("sudo_password")
    if not password:
        return out({"ok": False, "code": "sudo_password_missing", "error": f"'{args.cred}' 에 sudo_password 가 없습니다",
                    "next": f"사용자가 터미널에서: launch_cli.py cred set --name {args.cred} --prompt"})
    command = list(args.command or [])
    if not command:
        return out({"ok": False, "code": "command_required", "error": "실행할 명령이 없습니다",
                    "next": f"local sudo --cred {args.cred} -- <명령> [인자...]"})
    if not shutil.which("sudo"):
        return out({"ok": False, "code": "sudo_missing", "error": "sudo 를 찾을 수 없습니다"})
    try:
        r = subprocess.run(["sudo", "-S", "-p", "", *command], input=str(password) + "\n",
                           capture_output=True, text=True, timeout=args.timeout)
    except subprocess.TimeoutExpired:
        return out({"ok": False, "code": "sudo_timeout", "error": f"응답 없음 ({args.timeout}초)"})
    stdout = credentials.mask(r.stdout, cred)
    stderr = credentials.mask(r.stderr, cred)
    ok = r.returncode == 0
    return out({"ok": ok, "code": "ok" if ok else "sudo_failed", "exit_code": r.returncode,
                "stdout": stdout[:args.max_output], "stderr": stderr.strip()[:1000] or None,
                "truncated": len(stdout) > args.max_output,
                "summary": f"{args.cred}: sudo {command[0]} " + ("완료" if ok else f"실패 (종료코드 {r.returncode})"),
                "next": None if ok else "stderr 를 보고 명령을 고친다. 비밀번호가 틀렸으면 사용자가 cred set --name 이름 --prompt 로 다시 저장"})


def configure_local(p) -> None:
    p.add_argument("action", choices=["sudo"])
    p.add_argument("--cred", default=None, help="kind 가 local 인 자격증명 이름 (cred list)")
    p.add_argument("--timeout", type=int, default=300)
    p.add_argument("--max-output", dest="max_output", type=int, default=20000)
    # 실행할 명령은 `--` 뒤에 둔다. main() 이 파서 전에 잘라 args.command 로 넣는다.


COMMANDS = [
    Command(name="local", help="저장된 자격증명으로 이 맥에서 sudo 명령을 실행한다", run=cmd_local,
            configure=configure_local, tail_dest="command"),
]
