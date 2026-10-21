"""pro-launch 넘겨주기: launch_cli.py 서브프로세스 호출, 옮긴 명령 위임"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from common.emit import emit


# =========================================================================
# pro-launch 로 옮긴 명령 — 넘겨주기 층 (#631)
# =========================================================================
#
# 스킬끼리 파이썬 import 는 하지 않는다. 같은 플러그인 안의 launch_cli.py 를
# 서브프로세스로 부르고, 결과는 그대로 돌려주되 "이제 저쪽을 쓰라"는 next 를 싣는다.
# 다음 마이너에서 이 층을 지운다.

MOVED = ("doctor", "devices", "device", "web", "access", "db", "logs", "shrink",
         "get-output-path")

# skills/pro-launch/scripts/launch_cli.py (이 파일: skills/pro-agent-test/scripts/pro_agent_test/)
_LAUNCH_CLI = Path(__file__).resolve().parents[3] / "pro-launch" / "scripts" / "launch_cli.py"


def _launch(argv: list[str]) -> tuple[dict | None, str, int]:
    """launch_cli 를 부르고 (JSON, 원문, 종료코드). 표준입력은 넘기지 않는다."""
    if not _LAUNCH_CLI.is_file():
        return None, "", 1
    r = subprocess.run([sys.executable, str(_LAUNCH_CLI), *argv], capture_output=True,
                       text=True, encoding="utf-8", stdin=subprocess.DEVNULL,
                       env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    try:
        data = json.loads((r.stdout or "").strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        data = None
    return data, (r.stdout or "") + (r.stderr or ""), r.returncode


def delegate(argv: list[str]) -> int:
    """옮긴 명령을 pro-launch 로 넘긴다. 산출물은 여전히 agent-test 폴더에 받는다."""
    cmd = argv[0]
    if cmd == "get-output-path" and "--skill" not in argv:
        argv = [*argv, "--skill", "agent-test"]
    data, raw, rc = _launch(argv)
    if data is None and rc == 0 and raw.strip():
        # --help 처럼 JSON 이 아닌 정상 출력 — 그대로 보여준다
        sys.stdout.write(raw)
        return 0
    if data is None:
        return emit({"ok": False, "code": "launch_unavailable",
                     "error": f"Could not call pro-launch's launch_cli.py ({_LAUNCH_CLI})",
                     "output": raw[-400:],
                     "hint": "Check that projectops is fully installed — pro-launch must be installed with it"})
    moved = f"use pro-launch's launch_cli.py {cmd} (e2e_cli {cmd} is removed in the next minor)"
    data["moved_to"] = f"launch_cli.py {cmd}"
    data["next"] = f"{data['next']} · {moved}" if data.get("next") else moved
    return emit(data)
