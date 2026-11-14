"""`logs` — view server logs."""
from __future__ import annotations

import os
import re
import subprocess

from common.access import load_access

import credentials

from common.proc import bash_executable
from pro_launch.registry import Command
from pro_launch.runtime.context import project_root, state_home
from pro_launch.runtime.creds import cred_name_for, load_cred
from pro_launch.runtime.output import out, set_area, use_access


def cmd_logs(args) -> int:
    """View server logs. **Uses the recorded viewing method** — never tries to guess."""
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
    # tail·grep are applied in Python, not piped (#704). Checking only the pipe's last exit code
    # hides failures of earlier commands (missing command, ssh refused) and reports "0 log lines, success".
    try:
        r = subprocess.run([bash_executable(), "-lc", command], capture_output=True, text=True, errors="replace",
                           timeout=args.timeout, env=dict(os.environ, **cred_env))
    except subprocess.TimeoutExpired:
        return out({"ok": False, "code": "logs_timeout", "error": f"No response ({args.timeout}s)"})
    if cred:                                  # keep the password out of the record even if the server echoes it
        r.stdout = credentials.mask(r.stdout, cred)
        r.stderr = credentials.mask(r.stderr, cred)
    err = (r.stderr or "").strip()
    # A grep inside the saved command exits 1 on zero matches — if both output and error are empty, treat as success
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
            pat = re.compile(re.escape(args.grep), re.IGNORECASE)   # not a regex; match literally
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
