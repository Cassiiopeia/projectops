"""Shared helpers: step errors with codes, subprocess runner, private files (mode 600/700), project key rules, paths."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

# Project key: lower case letter first, then lower case letters or digits, 2 to 20 characters (same rule as the
# reference provisioner, so a key accepted here is never refused by the server)
PROJECT_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9]{1,19}$")
# Keys a team brain must never take (the personal brain names)
RESERVED_PROJECT_KEYS = ("personal", "gbrain", "default")
COMMAND_TIMEOUT_SECONDS = 600
PRIVATE_FILE_MODE = 0o600
PRIVATE_DIRECTORY_MODE = 0o700


class StepError(Exception):
    """A failed step: stable code + message + the next thing to do (never carries a secret)"""

    def __init__(self, code: str, message: str, next_step: str | None = None, details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.next_step = next_step
        self.details = details or {}


def home() -> Path:
    # Path.home() follows HOME, so a throwaway HOME keeps dry runs away from the real registry and sync folders
    return Path.home()


def state_directory() -> Path:
    return home() / ".projectops" / "gbrain"


def default_sync_root() -> Path:
    return home() / "gbrains"


def to_project_key(raw: str | None) -> str | None:
    """Repository or registry name > project key candidate (lower case, letters and digits only), None when unusable"""
    if not raw:
        return None
    key = re.sub(r"[^a-z0-9]", "", raw.lower())
    return key if PROJECT_KEY_PATTERN.match(key) and key not in RESERVED_PROJECT_KEYS else None


def validate_project_key(key: str | None) -> str:
    if not key or not PROJECT_KEY_PATTERN.match(key):
        raise StepError("invalid_project", f"project key '{key}' must be 2-20 lower case letters or digits, starting with a letter",
                        "pass --project <key>, e.g. --project myapp")
    if key in RESERVED_PROJECT_KEYS:
        raise StepError("reserved_project", f"'{key}' is a personal brain name and cannot be a team brain key",
                        "pass another --project key")
    return key


def run(command: list[str], cwd: Path | None = None, env: dict | None = None, timeout: int = COMMAND_TIMEOUT_SECONDS,
        secrets: list[str] | None = None) -> tuple[int, str]:
    """Run a command > (exit code, combined output with every secret masked); 127 when the program is missing"""
    # Resolve against the caller's PATH (scheduled runs lack the user's Bun bin)
    if shutil.which(command[0], path=env.get("PATH") if env is not None else None) is None and not Path(command[0]).exists():
        return 127, f"{command[0]} not found"
    try:
        completed = subprocess.run(command, cwd=str(cwd) if cwd else None, env=env, capture_output=True,
                                   encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, f"{command[0]} timed out after {timeout}s"
    output = (completed.stdout or "") + (completed.stderr or "")
    return completed.returncode, mask(output, secrets)


def mask(text: str, secrets: list[str] | None) -> str:
    for secret in secrets or []:
        if secret:
            text = text.replace(secret, "<secret>")
    # Connection strings that slipped through: keep host and database, hide the password part
    return re.sub(r"(postgres(?:ql)?://[^:/\s]+:)[^@\s]+@", r"\1<secret>@", text)


def gbrain_environment(gbrain_home: Path | None = None) -> dict:
    env = dict(os.environ)
    # gbrain is usually installed by bun; launchd and cron start with a bare PATH
    env["PATH"] = os.pathsep.join([str(home() / ".bun" / "bin"), env.get("PATH", "")])
    if gbrain_home is not None:
        env["GBRAIN_HOME"] = str(gbrain_home)
    return env


def write_private_json(path: Path, data: dict) -> None:
    """JSON readable by the owner only (600), parent folder 700; written atomically"""
    ensure_private_directory(path.parent)
    temporary_path = path.with_name(f".{path.name}.tmp")
    file_descriptor = os.open(str(temporary_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, PRIVATE_FILE_MODE)
    with os.fdopen(file_descriptor, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(data, ensure_ascii=False, indent=2))
    os.chmod(temporary_path, PRIVATE_FILE_MODE)
    os.replace(temporary_path, path)


def read_json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def ensure_private_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, PRIVATE_DIRECTORY_MODE)
    except OSError:
        pass


def timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def compact_timestamp() -> str:
    return time.strftime("%Y%m%d%H%M%S")
