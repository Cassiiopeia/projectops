"""`ssh` — 원격 명령을 실행한다."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import credentials
import knowledge

from pro_launch.registry import Command
from pro_launch.runtime.context import project_root
from pro_launch.runtime.creds import load_cred
from pro_launch.runtime.output import out, set_area


def _server_prefix(name: str) -> str:
    return f"server.{knowledge.norm_key(name)}."


# 서버 사실 탐침: 셸이 POSIX 이고 uname 이 있을 때만 의미가 있다 (Windows 는 조용히 건너뛴다).
_PROBE = ("uname -s 2>/dev/null; "
          "[ -x /var/packages/ContainerManager/target/usr/bin/docker ] && echo SYNO_DOCKER; true")


_SYNO_DOCKER = "/var/packages/ContainerManager/target/usr/bin/docker"


_KNOWN_OS = ("Linux", "Darwin", "FreeBSD")


def _record_server_facts(name: str, base_cmd: list[str], env: dict) -> None:
    """처음 접속 성공 때 확인된 사실(OS · 시놀로지 docker 절대경로)만 이 컴퓨터 범위에 남긴다.

    이미 OS 를 알고 있으면 추가 접속을 하지 않는다. 호스트·계정·비밀은 how 에 쓰지 않는다.
    어떤 실패도 본 명령 결과를 망치지 않는다.
    """
    try:
        if not knowledge.base_dir().is_absolute():
            return
        prefix = _server_prefix(name)
        if any(e["key"] == prefix + "os" for e in knowledge.load(knowledge.store_path("machine", Path(".")))
               if e["area"] == "server"):
            return
        r = subprocess.run(base_cmd + [_PROBE], env=env, capture_output=True, text=True, timeout=15)
        lines = [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]
        if r.returncode != 0 or not lines or lines[0] not in _KNOWN_OS:
            return
        knowledge.auto_record("server", prefix + "os", f"OS {lines[0]} (uname -s 로 확인)")
        if "SYNO_DOCKER" in lines:
            knowledge.auto_record("server", prefix + "docker",
                                  f"docker 는 PATH 에 없다 — 절대경로 {_SYNO_DOCKER} 로 부른다 "
                                  "(컨테이너 안 curl 이 없으면 wget)")
    except Exception:   # noqa: BLE001 — 기억은 보조다
        pass


def cmd_ssh(args) -> int:
    """원격 명령을 실행한다 — 저장된 서버(--cred)나, 저장 없이 직접 넘긴 접속 정보(--host …)로.

    --sudo 면 원격에서 `SUDO <명령>` 을 쓸 수 있다 (비밀번호가 필요한 sudo, PATH 에 /usr/local/bin 포함).
    직접 넘긴 값(--host · --port · --user · --password · --password-env · --key-path)은 저장하지 않고,
    --cred 와 함께 주면 그 값이 저장된 값보다 우선한다. 출력의 비밀번호는 가린다.
    """
    # 서버 기억은 이 서버 것만 싣는다 — key 는 server.<자격증명 이름>.* (기억 원칙 1). 저장 없는 접속은 기억하지 않는다
    if args.cred:
        set_area("server", project_root(args), key_prefix=_server_prefix(args.cred))
    cred, err = load_cred(args.cred)
    if err:
        return out(err)
    adhoc = {k: v for k, v in (("host", args.host), ("port", args.port), ("user", args.user),
                                ("key_path", args.key_path)) if v not in (None, "")}
    if args.password_env:
        if args.password_env not in os.environ:
            return out({"ok": False, "code": "env_not_set",
                        "error": f"환경변수 {args.password_env} 가 비어 있습니다"})
        adhoc["password"] = os.environ[args.password_env]
    elif args.password:
        adhoc["password"] = args.password
    if adhoc:
        # 직접 넘긴 비밀번호면 저장된 key_path 가, 직접 넘긴 key 면 저장된 password 가 끼어들지 않게 한다
        base = dict(cred or {})
        if "password" in adhoc:
            base.pop("key_path", None)
        if "key_path" in adhoc:
            base.pop("password", None)
        cred = {**base, **adhoc, "name": (cred or {}).get("name") or "(저장 안 함)"}
    if not cred:
        return out({"ok": False, "code": "cred_required",
                    "error": "저장된 서버(--cred) 나 접속 정보(--host --user …)가 필요합니다",
                    "next": "cred list  # 또는 ssh --host <호스트> --port <포트> --user <계정> "
                            "--password-env <변수> | --key-path <키 파일> --command '…'"})
    if not args.command:
        return out({"ok": False, "code": "command_required", "error": "--command 가 필요합니다"})
    host, user = cred.get("host"), cred.get("user")
    label = args.cred or host or "(저장 안 함)"
    if not host:
        return out({"ok": False, "code": "host_missing",
                    "error": f"'{label}' 에 host 가 없습니다 (--host 를 주거나 cred set 으로 host·user 를 적는다)"})
    password = cred.get("password")
    key_path = cred.get("key_path")
    dest = f"{user}@{host}" if user else host
    ssh = ["ssh", "-o", "StrictHostKeyChecking=accept-new", "-o", "ConnectTimeout=20"]
    if cred.get("port"):
        ssh += ["-p", str(cred["port"])]
    env = dict(os.environ)
    if key_path:
        ssh += ["-i", os.path.expanduser(str(key_path)), "-o", "BatchMode=yes"]
        argv_prefix = []
    elif password:
        if not shutil.which("sshpass"):
            return out({"ok": False, "code": "sshpass_missing", "error": "비밀번호 접속에는 sshpass 가 필요합니다",
                        "install": "brew install hudochenkov/sshpass/sshpass  (또는 key_path 로 키 접속)"})
        env["SSHPASS"] = str(password)
        argv_prefix = ["sshpass", "-e"]
    else:
        argv_prefix = []                              # 에이전트 키·기본 키에 맡긴다

    remote = args.command
    stdin = None
    if args.sudo:
        if not password:
            return out({"ok": False, "code": "sudo_password_missing",
                        "error": "--sudo 에는 저장된 password 가 필요합니다"})
        # 비밀번호는 표준입력으로만 넘긴다 — 원격 명령줄(ps)에 남지 않는다
        remote = ('export PATH=$PATH:/usr/local/bin; IFS= read -r PW; '
                  'SUDO() { echo "$PW" | sudo -S -p "" "$@"; }; ' + args.command)
        stdin = str(password) + "\n"
    try:
        r = subprocess.run(argv_prefix + ssh + [dest, remote], input=stdin, env=env,
                           capture_output=True, text=True, timeout=args.timeout)
    except subprocess.TimeoutExpired:
        return out({"ok": False, "code": "ssh_timeout", "error": f"응답 없음 ({args.timeout}초)"})
    stdout = credentials.mask(r.stdout, cred)
    stderr = credentials.mask(r.stderr, cred)
    ok = r.returncode == 0
    if ok and args.cred and not adhoc:
        _record_server_facts(args.cred, argv_prefix + ssh + [dest], env)
    hint = ("stderr 를 보고 명령·접속 정보를 고친다" + (" (cred show --name)" if args.cred else ""))
    if ok and adhoc and not args.cred:
        hint = ("자주 쓰는 서버면 cred set --name <이름> --json "
                "'{\"kind\":\"ssh\",\"host\":…,\"port\":…,\"user\":…,\"use_when\":…}' 로 저장해 두면 다음부터 이름만 쓴다")
    return out({"ok": ok, "code": "ok" if ok else "ssh_failed", "exit_code": r.returncode,
                "stdout": stdout[:args.max_output], "stderr": stderr.strip()[:1000] or None,
                "truncated": len(stdout) > args.max_output,
                "summary": f"{label}: " + ("실행 완료" if ok else f"실패 (종료코드 {r.returncode})"),
                "next": hint if (not ok or adhoc) else None})


def configure_ssh(p) -> None:
    p.add_argument("--cred", default=None, help="저장된 서버 자격증명 이름 (cred list)")
    p.add_argument("--host", default=None, help="저장 없이 직접 접속: 호스트 (--cred 와 함께 주면 그 값을 덮어쓴다)")
    p.add_argument("--port", type=int, default=None, help="SSH 포트")
    p.add_argument("--user", default=None, help="계정")
    p.add_argument("--password", default=None, help="비밀번호 (기록에 남아도 되는 환경일 때. 아니면 --password-env)")
    p.add_argument("--password-env", dest="password_env", default=None, help="비밀번호를 읽을 환경변수 이름")
    p.add_argument("--key-path", dest="key_path", default=None, help="개인키(PEM) 파일 경로 — 비밀번호 대신")
    p.add_argument("--command", default=None, help="원격에서 실행할 명령")
    p.add_argument("--sudo", action="store_true", help="원격에서 SUDO <명령> 을 쓸 수 있게 한다 (비밀번호 sudo)")
    p.add_argument("--timeout", type=int, default=60)
    p.add_argument("--max-output", dest="max_output", type=int, default=20000)


COMMANDS = [
    Command(name="ssh", help="원격 명령을 실행한다 (저장된 서버 --cred, 또는 저장 없이 --host 로 직접)", run=cmd_ssh,
            configure=configure_ssh),
]
