"""Claude Code PreToolUse(Bash) hook: blocks raw commands that create, delete or wipe virtual devices and redirects to launch_cli commands (#954).

Blocked patterns are read from one place, the pro-launch device backend declarations (raw_command_patterns).
Commands without any related word pass without loading anything (runs on every Bash call, so it must be fast).
Bypass: commands containing PRO_LAUNCH_ALLOW_RAW=1 pass (when the user really wants it). Any error always passes.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

PLUGIN_ROOT = Path(os.environ.get("CLAUDE_PLUGIN_ROOT") or Path(__file__).resolve().parents[1])
LAUNCH_SCRIPTS = PLUGIN_ROOT / "skills" / "pro-launch" / "scripts"
# If none of these words appear, the patterns are not loaded
TRIGGER_WORDS = ("simctl", "avdmanager", "wipe-data", "emu kill", "emu  kill")
BYPASS_MARKER = "PRO_LAUNCH_ALLOW_RAW=1"
# Only inspect when the first word of an actually executed command is one of these tools (text searches like grep "simctl create" are not blocked)
DEVICE_TOOL_NAMES = ("xcrun", "simctl", "avdmanager", "emulator", "adb")
_SEGMENT_SEPARATOR_PATTERN = re.compile(r"&&|\|\||[;|\n()]")
_ENV_ASSIGNMENT_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=\S*$")


def device_tool_segments(command: str) -> list[str]:
    """Split the command on ; && || | and newlines, keeping only pieces whose first word (after env assignments and sudo) is a device tool."""
    segments = []
    for segment in _SEGMENT_SEPARATOR_PATTERN.split(command):
        words = segment.split()
        while words and (_ENV_ASSIGNMENT_PATTERN.match(words[0]) or words[0] in ("sudo", "env", "exec", "time")):
            words.pop(0)
        if words and Path(words[0].strip("\"'")).name.removesuffix(".exe") in DEVICE_TOOL_NAMES:
            segments.append(" ".join(words))
    return segments


def blocked_pattern(command: str):
    """One pattern to block > RawCommandPattern or None."""
    if BYPASS_MARKER in command or not any(word in command for word in TRIGGER_WORDS):
        return None
    for path in (str(PLUGIN_ROOT / "scripts"), str(LAUNCH_SCRIPTS)):
        if path not in sys.path:
            sys.path.insert(0, path)
    segments = device_tool_segments(command)
    if not segments:
        return None
    from pro_launch.runtime.device_backends import raw_command_patterns
    return next((pattern for pattern in raw_command_patterns() for segment in segments
                 if re.search(pattern.pattern, segment)), None)


def deny_response(command: str, pattern) -> dict:
    reason = (f"pro-launch: do not create or delete virtual devices with raw commands; several sessions share "
              f"the devices on this machine. Instead: {pattern.instead}  (to borrow one, use device acquire). "
              f"If the user explicitly wants the raw command, prefix it with {BYPASS_MARKER}.")
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": reason}}


def main(stdin_text: str) -> int:
    try:
        payload = json.loads(stdin_text or "{}")
        if payload.get("tool_name") != "Bash":
            return 0
        command = str((payload.get("tool_input") or {}).get("command") or "")
        pattern = blocked_pattern(command)
    except Exception:   # noqa: BLE001 — a hook error must not block the user's command
        return 0
    if pattern is not None:
        print(json.dumps(deny_response(command, pattern), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.stdin.read() if not sys.stdin.isatty() else ""))
