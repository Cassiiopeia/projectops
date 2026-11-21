"""GitHub Actions step results: key=value lines in $GITHUB_OUTPUT + one JSON line on stdout
Shared by build_number.py, ios_release.py and expo_app.py (stdlib only)."""
from __future__ import annotations

import json
import os
import re

# Terminal color codes (xcodebuild and fastlane logs)
_ANSI_COLOR = re.compile(r"\x1b\[[0-9;]*m")


def to_one_line(value) -> str:
    """Value > one line without color codes (a newline would start another key in GITHUB_OUTPUT)"""
    return " ".join(_ANSI_COLOR.sub("", str(value)).split())


def write_github_output(pairs: dict) -> None:
    """Append key=value per pair; no-op outside Actions (GITHUB_OUTPUT unset). None > empty value"""
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as handle:
        for key, value in pairs.items():
            handle.write(f"{key}={'' if value is None else to_one_line(value)}\n")


def emit_json(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False))
