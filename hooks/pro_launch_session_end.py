"""Claude Code SessionEnd 훅: 끝난 세션이 빌린 기기를 반납하고(#953) 띄운 브라우저를 닫는다(#956).

입력: stdin JSON 의 session_id. 그 세션 lease · 브라우저가 있을 때만 `device release --all` · `web close --session-end` 를 띄운다
(없으면 바로 끝 — 세션 종료를 늦추지 않게). 어떤 경우에도 종료 코드 0.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

PLUGIN_ROOT = Path(os.environ.get("CLAUDE_PLUGIN_ROOT") or Path(__file__).resolve().parents[1])
LAUNCH_CLI = PLUGIN_ROOT / "skills" / "pro-launch" / "scripts" / "launch_cli.py"
LAUNCH_SCRIPTS = LAUNCH_CLI.parent
RELEASE_TIMEOUT_SECONDS = 25


def _use_launch_modules() -> None:
    """pro-launch 원본 모듈을 불러올 수 있게 경로를 잇는다."""
    for path in (str(PLUGIN_ROOT / "scripts"), str(LAUNCH_SCRIPTS)):
        if path not in sys.path:
            sys.path.insert(0, path)


def session_has_leases(session_id: str) -> bool:
    """원장에 그 세션 lease 가 하나라도 있나 (원장 읽기는 pro-launch 원본을 쓴다). 못 읽으면 False."""
    _use_launch_modules()
    try:
        from pro_launch.runtime.device_ledger import read_ledger
    except ImportError:
        return False
    return any(lease.get("session") == session_id
               for entry in read_ledger()["devices"].values() for lease in entry["leases"])


def session_has_browsers(session_id: str) -> bool:
    """이 세션이 띄운 브라우저 상태 파일이 있나 (#956)."""
    _use_launch_modules()
    try:
        from pro_launch.runtime.browser import read_state
        from pro_launch.runtime.browser_profiles import all_web_state_files
    except ImportError:
        return False
    return any(read_state(path).get("opened_by_session") == session_id for path in all_web_state_files())


def main(stdin_text: str, environ: dict) -> int:
    try:
        session_id = (json.loads(stdin_text or "{}") or {}).get("session_id")
    except (json.JSONDecodeError, AttributeError):
        return 0
    if not session_id:
        return 0
    commands = []
    if session_has_leases(session_id):
        commands.append(["device", "release", "--all"])
    if session_has_browsers(session_id):
        commands.append(["web", "close", "--session-end"])
    for command in commands:
        try:
            subprocess.run([sys.executable, str(LAUNCH_CLI), *command],
                           env={**environ, "LAUNCH_SESSION": session_id, "PYTHONIOENCODING": "utf-8"},
                           capture_output=True, timeout=RELEASE_TIMEOUT_SECONDS)
        except (OSError, subprocess.SubprocessError):
            pass   # 실패가 세션 종료를 막지 않는다 — 기기는 호스트 종료로 풀리고, 브라우저는 web close --stale 이 줍는다
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.stdin.read() if not sys.stdin.isatty() else "", dict(os.environ)))
