"""Save values read from the screen without printing them — `web value --save-env` / `web clipboard --save-env` (#930).

Secrets shown only inside inputs or via copy buttons (Client Secret, key hash) were read via OCR / pbpaste and left in the conversation log.
Values are written only to a 0600 file in the state folder (`export NAME='value'`); results carry only the length and first 12 chars of sha256.
`web type --text-env NAME` reads from this file when the environment variable is missing — usable directly without source.
"""
from __future__ import annotations

import hashlib
import os
import re
import shlex
from pathlib import Path

from pro_launch.runtime.context import state_home

# Name of the save file inside the state folder (user read/write only)
SAVED_VALUES_FILE = "saved-values.env"
FILE_MODE = 0o600
# Shell variable name rule
_ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
HASH_PREFIX_CHARS = 12


def saved_values_path(root: Path) -> Path:
    return state_home(root) / SAVED_VALUES_FILE


def _sh_quote(value: str) -> str:
    """Wrap in single quotes — with double quotes $ expands and the value changes"""
    return "'" + value.replace("'", "'\\''") + "'"


def read_saved_values(root: Path) -> dict[str, str]:
    """Save file > {name: value}. Empty dict if missing or unreadable"""
    try:
        lines = saved_values_path(root).read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    values = {}
    for line in lines:
        try:
            words = shlex.split(line)
        except ValueError:
            continue
        if len(words) == 2 and words[0] == "export" and "=" in words[1]:
            name, value = words[1].split("=", 1)
            values[name] = value
    return values


def is_valid_env_name(name: str) -> bool:
    return bool(_ENV_NAME.fullmatch(name or ""))


def save_value(root: Path, name: str, value: str) -> dict:
    """Save the value > summary for the result (name, file, length, hash prefix). Never returns the value itself"""
    values = read_saved_values(root)
    values[name] = value
    path = saved_values_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(f"export {key}={_sh_quote(saved)}\n" for key, saved in values.items())
    # 0600 from creation — changing permissions after writing leaves a window where it can be read
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, FILE_MODE)
    with os.fdopen(descriptor, "w", encoding="utf-8") as saved_file:
        saved_file.write(body)
    os.chmod(path, FILE_MODE)
    return {"saved_env": name, "env_file": str(path), "length": len(value),
            "sha256_prefix": hashlib.sha256(value.encode("utf-8")).hexdigest()[:HASH_PREFIX_CHARS]}


def invalid_name_failure(action: str, name: str) -> dict:
    return {"ok": False, "code": "bad_env_name", "action": action, "name": name,
            "error": f"'{name}' cannot be an environment variable name (letters, digits and _ only, not starting with a digit)",
            "next": f"web {action} --save-env CLIENT_SECRET"}


def saved_next(name: str) -> str:
    return f"web type --ref <number> --text-env {name}  # the value never appears on the command line or in output"
