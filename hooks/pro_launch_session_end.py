"""Claude Code SessionEnd 훅: 끝난 세션이 pro-launch 로 빌린 기기를 반납한다 (#953).

입력: stdin JSON 의 session_id. 그 세션 lease 가 원장에 있을 때만 `device release --all` 을 띄운다
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


def session_has_leases(session_id: str) -> bool:
    """원장에 그 세션 lease 가 하나라도 있나 (원장 읽기는 pro-launch 원본을 쓴다). 못 읽으면 False."""
    for path in (str(PLUGIN_ROOT / "scripts"), str(LAUNCH_SCRIPTS)):
        if path not in sys.path:
            sys.path.insert(0, path)
    try:
        from pro_launch.runtime.device_ledger import read_ledger
    except ImportError:
        return False
    return any(lease.get("session") == session_id
               for entry in read_ledger()["devices"].values() for lease in entry["leases"])


def main(stdin_text: str, environ: dict) -> int:
    try:
        session_id = (json.loads(stdin_text or "{}") or {}).get("session_id")
    except (json.JSONDecodeError, AttributeError):
        return 0
    if not session_id or not session_has_leases(session_id):
        return 0
    try:
        subprocess.run([sys.executable, str(LAUNCH_CLI), "device", "release", "--all"],
                       env={**environ, "LAUNCH_SESSION": session_id, "PYTHONIOENCODING": "utf-8"},
                       capture_output=True, timeout=RELEASE_TIMEOUT_SECONDS)
    except (OSError, subprocess.SubprocessError):
        pass   # 반납 실패가 세션 종료를 막지 않는다 — 다음 acquire 가 호스트 종료로 풀린 소유를 넘겨받는다
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.stdin.read() if not sys.stdin.isatty() else "", dict(os.environ)))
