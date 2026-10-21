"""web 시간 상한 (#921) 과 새 명령의 실제 브라우저 동작 (#930 · #931)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
COMMON_SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"


# ── 시간 상한 (#921) ───────────────────────────────────────────────────────

def test_watchdog_ends_a_stuck_command_with_browser_hung_json(tmp_path):
    """상한을 넘기면 멈춘 채 두지 않고 browser_hung JSON 하나를 내고 끝낸다"""
    state_file = tmp_path / "browser.json"
    state_file.write_text(json.dumps({"pid": 4242, "profile": "/p/.browser-profile", "cdp": "http://127.0.0.1:1"}))
    code = (
        "import sys, time; from pathlib import Path\n"
        f"sys.path.insert(0, {str(SCRIPTS)!r})\n"
        f"sys.path.insert(0, {str(COMMON_SCRIPTS)!r})\n"
        "from pro_launch.commands.web.watchdog import Watchdog\n"
        f"Watchdog('text', 1, Path({str(state_file)!r})).start()\n"
        "time.sleep(30)\n")
    started = time.time()
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                            env={**os.environ, "PROJECTOPS_HOME": str(tmp_path / "ph")})
    data = json.loads(result.stdout.strip().splitlines()[-1])
    assert time.time() - started < 15 and result.returncode != 0
    assert data["code"] == "browser_hung" and data["pid"] == 4242 and data["profile"] == "/p/.browser-profile"
    assert json.loads(state_file.read_text()).get("hung_at")   # 다음 web open 이 다시 붙지 않는다
