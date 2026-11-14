"""Passing an ssh password: sshpass -e if sshpass exists, otherwise OpenSSH SSH_ASKPASS (#987)
The password passes only through env vars > never left on the command line, in files or in logs
"""
from __future__ import annotations

import contextlib
import os
import shutil
import stat
import sys
import tempfile
from typing import Iterator

# Env var the askpass script reads (the password value is never written to a file)
ASKPASS_PASSWORD_ENV = "PROJECTOPS_SSH_ASKPASS_PASSWORD"
# Avoid account lockout from repeated wrong passwords > 1 attempt
SINGLE_PASSWORD_PROMPT_OPTIONS = ["-o", "NumberOfPasswordPrompts=1"]

_POSIX_ASKPASS_SCRIPT = '#!/bin/sh\nprintf \'%s\\n\' "$' + ASKPASS_PASSWORD_ENV + '"\n'


def _windows_askpass_script() -> str:
    """Windows .cmd: Python prints the env var so the password never goes through cmd parsing"""
    return ('@"%s" -I -c "import os,sys;sys.stdout.write(os.environ.get(\'%s\',\'\')+chr(10))"\r\n'
            % (sys.executable, ASKPASS_PASSWORD_ENV))


def _write_askpass_script(directory: str) -> str:
    """Create the askpass script in a 0700 temp folder > path"""
    is_windows = os.name == "nt"
    script_path = os.path.join(directory, "askpass.cmd" if is_windows else "askpass.sh")
    with open(script_path, "w", encoding="utf-8", newline="") as handle:
        handle.write(_windows_askpass_script() if is_windows else _POSIX_ASKPASS_SCRIPT)
    os.chmod(script_path, stat.S_IRWXU)
    return script_path


@contextlib.contextmanager
def password_transport(password: str, env: dict) -> Iterator[tuple[list[str], dict]]:
    """(argv to prefix ssh, extra subprocess kwargs). env is updated in place; the askpass file is deleted at the end (success·failure alike)"""
    env_password_key = "SSHPASS" if shutil.which("sshpass") else ASKPASS_PASSWORD_ENV
    env[env_password_key] = str(password)
    if env_password_key == "SSHPASS":
        yield ["sshpass", "-e"], {}
        return
    askpass_directory = tempfile.mkdtemp(prefix="projectops-askpass-")   # mkdtemp is 0700
    try:
        env["SSH_ASKPASS"] = _write_askpass_script(askpass_directory)
        env["SSH_ASKPASS_REQUIRE"] = "force"                 # OpenSSH 8.4+: use askpass even with a terminal
        env.setdefault("DISPLAY", "projectops:0")             # before 8.4: askpass needs DISPLAY
        # before 8.4: with a controlling terminal it asks via tty > detach into a new session (POSIX only)
        popen_options = {} if os.name == "nt" else {"start_new_session": True}
        yield [], popen_options
    finally:
        shutil.rmtree(askpass_directory, ignore_errors=True)
