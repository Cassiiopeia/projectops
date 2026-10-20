"""Claude Code PreToolUse(Bash) 훅: 가상 기기를 만들고·지우고·초기화하는 raw 명령을 막고 launch_cli 명령으로 돌린다 (#954).

막는 패턴은 pro-launch 기기 백엔드 선언 한 곳(raw_command_patterns)에서 읽는다.
관련 단어가 없는 명령은 아무것도 불러오지 않고 통과 (모든 Bash 호출에 끼므로 빨라야 한다).
우회: 명령에 PRO_LAUNCH_ALLOW_RAW=1 이 있으면 통과 (사용자가 직접 원할 때). 오류가 나면 언제나 통과.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

PLUGIN_ROOT = Path(os.environ.get("CLAUDE_PLUGIN_ROOT") or Path(__file__).resolve().parents[1])
LAUNCH_SCRIPTS = PLUGIN_ROOT / "skills" / "pro-launch" / "scripts"
# 이 단어가 하나도 없으면 패턴을 읽지 않는다
TRIGGER_WORDS = ("simctl", "avdmanager", "wipe-data", "emu kill", "emu  kill")
BYPASS_MARKER = "PRO_LAUNCH_ALLOW_RAW=1"
# 실제로 실행되는 명령의 첫 단어가 이 도구일 때만 본다 (grep "simctl create" 같은 글자 검색은 막지 않는다)
DEVICE_TOOL_NAMES = ("xcrun", "simctl", "avdmanager", "emulator", "adb")
_SEGMENT_SEPARATOR_PATTERN = re.compile(r"&&|\|\||[;|\n()]")
_ENV_ASSIGNMENT_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=\S*$")


def device_tool_segments(command: str) -> list[str]:
    """명령을 ; && || | 줄바꿈으로 나눠, 첫 단어(환경변수 대입·sudo 제외)가 기기 도구인 조각만."""
    segments = []
    for segment in _SEGMENT_SEPARATOR_PATTERN.split(command):
        words = segment.split()
        while words and (_ENV_ASSIGNMENT_PATTERN.match(words[0]) or words[0] in ("sudo", "env", "exec", "time")):
            words.pop(0)
        if words and Path(words[0].strip("\"'")).name.removesuffix(".exe") in DEVICE_TOOL_NAMES:
            segments.append(" ".join(words))
    return segments


def blocked_pattern(command: str):
    """막을 패턴 하나 > RawCommandPattern 또는 None."""
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
    reason = (f"pro-launch: 가상 기기를 raw 명령으로 만들거나 지우지 않는다 — 여러 세션이 한 컴퓨터의 기기를 나눠 쓴다. "
              f"대신: {pattern.instead}  (빌리기는 device acquire). "
              f"사용자가 직접 원하면 명령 앞에 {BYPASS_MARKER} 를 붙인다.")
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": reason}}


def main(stdin_text: str) -> int:
    try:
        payload = json.loads(stdin_text or "{}")
        if payload.get("tool_name") != "Bash":
            return 0
        command = str((payload.get("tool_input") or {}).get("command") or "")
        pattern = blocked_pattern(command)
    except Exception:   # noqa: BLE001 — 훅 오류가 사용자 명령을 막으면 안 된다
        return 0
    if pattern is not None:
        print(json.dumps(deny_response(command, pattern), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.stdin.read() if not sys.stdin.isatty() else ""))
