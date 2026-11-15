"""`ssh` — run a remote command."""
from __future__ import annotations

import contextlib
import os
import subprocess
from pathlib import Path

import credentials
import knowledge

from pro_launch.registry import Command
from pro_launch.runtime.context import project_root
from pro_launch.runtime.creds import load_cred
from pro_launch.runtime.output import out, set_area, set_target
from pro_launch.runtime.ssh_askpass import SINGLE_PASSWORD_PROMPT_OPTIONS, password_transport
from pro_launch.runtime.ssh_failure import classify_ssh_failure


def _server_prefix(name: str) -> str:
    return f"server.{knowledge.norm_key(name)}."


# Server fact probe: meaningful only when the shell is POSIX and uname exists (Windows is silently skipped).
_PROBE = ("uname -s 2>/dev/null; "
          "[ -x /var/packages/ContainerManager/target/usr/bin/docker ] && echo SYNO_DOCKER; true")


_SYNO_DOCKER = "/var/packages/ContainerManager/target/usr/bin/docker"


_KNOWN_OS = ("Linux", "Darwin", "FreeBSD")

# Remote output decode order: UTF-8 > CP949 (Korean Windows cmd) > UTF-8 with replacement (#933)
_STRICT_ENCODINGS = ("utf-8", "cp949")
_FALLBACK_ENCODING = "utf-8-replace"


def decode_remote_output(raw: bytes | None) -> tuple[str, str]:
    """Remote output bytes > (text, encoding used). So a decode failure never loses the command result"""
    raw = raw or b""
    for encoding in _STRICT_ENCODINGS:
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace"), _FALLBACK_ENCODING


def _record_server_facts(name: str, base_cmd: list[str], env: dict, popen_options: dict) -> None:
    """Keep only facts confirmed on the first successful connection (OS · Synology docker absolute path) in this computer's scope.

    If the OS is already known, no extra connection is made. Host, account and secrets are never written to how.
    No failure here may spoil the main command result.
    """
    try:
        if not knowledge.base_dir().is_absolute():
            return
        prefix = _server_prefix(name)
        if any(e["key"] == prefix + "os" for e in knowledge.load(knowledge.store_path("machine", Path(".")))
               if e["area"] == "server"):
            return
        r = subprocess.run(base_cmd + [_PROBE], env=env, capture_output=True, text=True, errors="replace",
                           timeout=15, **popen_options)
        lines = [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]
        if r.returncode != 0 or not lines or lines[0] not in _KNOWN_OS:
            return
        knowledge.auto_record("server", prefix + "os", f"OS {lines[0]} (checked with uname -s)")
        if "SYNO_DOCKER" in lines:
            knowledge.auto_record("server", prefix + "docker",
                                  f"docker is not on PATH — call it by absolute path {_SYNO_DOCKER} "
                                  "(use wget if the container has no curl)")
    except Exception:   # noqa: BLE001 — memory is auxiliary
        pass


def cmd_ssh(args) -> int:
    """Run a remote command — on a saved server (--cred) or with connection info passed directly without saving (--host …).

    With --sudo, `SUDO <command>` can be used remotely (sudo needing a password, /usr/local/bin in PATH).
    Directly passed values (--host · --port · --user · --password · --password-env · --key-path) are not saved;
    given together with --cred they take precedence over saved values. Passwords in the output are masked.
    """
    # Include only this server's memories — key is server.<credential name>.* (memory principle 1). Unsaved connections are not remembered
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
                        "error": f"Environment variable {args.password_env} is empty"})
        adhoc["password"] = os.environ[args.password_env]
    elif args.password:
        adhoc["password"] = args.password
    if adhoc:
        # A directly passed password keeps the saved key_path out; a directly passed key keeps the saved password out
        base = dict(cred or {})
        if "password" in adhoc:
            base.pop("key_path", None)
        if "key_path" in adhoc:
            base.pop("password", None)
        cred = {**base, **adhoc, "name": (cred or {}).get("name") or "(not saved)"}
    if cred and cred.get("host"):
        # Put the harness (guide) matching this server in the response — also for an unsaved --host (projectops#1023)
        set_target(host=str(cred["host"]), root=project_root(args), area="server")
    if not cred:
        return out({"ok": False, "code": "cred_required",
                    "error": "A saved server (--cred) or connection details (--host --user …) are required",
                    "next": "cred list  # or ssh --host <host> --port <port> --user <account> "
                            "--password-env <variable> | --key-path <key file> --command '…'"})
    if not args.command:
        return out({"ok": False, "code": "command_required", "error": "--command is required"})
    host, user = cred.get("host"), cred.get("user")
    label = args.cred or host or "(not saved)"
    if not host:
        return out({"ok": False, "code": "host_missing",
                    "error": f"'{label}' has no host (give --host, or record host and user with cred set)"})
    password = cred.get("password")
    key_path = cred.get("key_path")
    dest = f"{user}@{host}" if user else host
    ssh = ["ssh", "-o", "StrictHostKeyChecking=accept-new", "-o", "ConnectTimeout=20"]
    if cred.get("port"):
        ssh += ["-p", str(cred["port"])]
    env = dict(os.environ)
    if key_path:
        ssh += ["-i", os.path.expanduser(str(key_path)), "-o", "BatchMode=yes"]
    elif password:
        ssh += SINGLE_PASSWORD_PROMPT_OPTIONS
    # Otherwise: leave it to the agent key / default key

    remote = args.command
    stdin = None
    if args.sudo:
        if not password:
            return out({"ok": False, "code": "sudo_password_missing",
                        "error": "--sudo needs a saved password"})
        # The password goes only via stdin — never on the remote command line (ps)
        remote = ('export PATH=$PATH:/usr/local/bin; IFS= read -r PW; '
                  'SUDO() { echo "$PW" | sudo -S -p "" "$@"; }; ' + args.command)
        stdin = str(password) + "\n"
    # Password delivery (sshpass > SSH_ASKPASS) — nothing attached for key / default-key logins (#987)
    with (password_transport(password, env) if password and not key_path
          else contextlib.nullcontext(([], {}))) as (argv_prefix, popen_options):
        try:
            # Taken as bytes — the remote may not be UTF-8 (CP949 Windows cmd)
            r = subprocess.run(argv_prefix + ssh + [dest, remote], input=stdin.encode("utf-8") if stdin else None,
                               env=env, capture_output=True, timeout=args.timeout, **popen_options)
        except subprocess.TimeoutExpired:
            return out({"ok": False, "code": "ssh_timeout", "error": f"No response ({args.timeout}s)",
                        "next": "A long command: raise --timeout. No answer at all: check the host, port and that the server is up"})
        ok = r.returncode == 0
        if ok and args.cred and not adhoc:
            _record_server_facts(args.cred, argv_prefix + ssh + [dest], env, popen_options)
    stdout_text, stdout_encoding = decode_remote_output(r.stdout)
    stderr_text, _stderr_encoding = decode_remote_output(r.stderr)
    stdout = credentials.mask(stdout_text, cred)
    stderr = credentials.mask(stderr_text, cred)
    code, hint = ("ok", None) if ok else classify_ssh_failure(r.returncode, stderr_text)
    if ok and adhoc and not args.cred:
        hint = ("For a server you use often, save it with cred set --name <name> --json "
                "'{\"kind\":\"ssh\",\"host\":…,\"port\":…,\"user\":…,\"use_when\":…}' and use just the name next time")
    return out({"ok": ok, "code": code, "exit_code": r.returncode,
                "stdout": stdout[:args.max_output], "stdout_encoding": stdout_encoding,
                # stderr is always a string — None would break the caller's slicing (#933)
                "stderr": stderr.strip()[:1000],
                "truncated": len(stdout) > args.max_output,
                "summary": f"{label}: " + ("succeeded" if ok else f"{code} (exit code {r.returncode})"),
                "next": hint if (not ok or adhoc) else None})


def configure_ssh(p) -> None:
    p.add_argument("--cred", default=None, help="Saved server credential name (cred list)")
    p.add_argument("--host", default=None, help="Direct connection without saving: host (overrides the saved value when given with --cred)")
    p.add_argument("--port", type=int, default=None, help="SSH port")
    p.add_argument("--user", default=None, help="Account")
    p.add_argument("--password", default=None, help="Password (only where it may appear in logs; otherwise --password-env)")
    p.add_argument("--password-env", dest="password_env", default=None, help="Name of the environment variable holding the password")
    p.add_argument("--key-path", dest="key_path", default=None, help="Private key (PEM) file path — instead of a password")
    p.add_argument("--command", default=None, help="Command to run on the remote host")
    p.add_argument("--sudo", action="store_true", help="Allow SUDO <command> on the remote host (password sudo)")
    p.add_argument("--timeout", type=int, default=60)
    p.add_argument("--max-output", dest="max_output", type=int, default=20000)


COMMANDS = [
    Command(name="ssh", help="Run a remote command (saved server via --cred, or directly via --host without saving)", run=cmd_ssh,
            configure=configure_ssh),
]
