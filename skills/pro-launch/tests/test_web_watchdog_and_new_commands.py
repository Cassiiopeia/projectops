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


def test_login_handoff_extends_the_command_deadline():
    """web login --handoff-seconds 120 이 90초 상한에 끊기지 않는다 (#973)"""
    import argparse
    sys.path.insert(0, str(SCRIPTS))
    sys.path.insert(0, str(COMMON_SCRIPTS))
    from pro_launch.commands.web.watchdog import deadline_seconds

    assert deadline_seconds(argparse.Namespace(timeout=None, handoff_seconds=120), "page") >= 90 + 120


def test_script_memory_cap_kills_the_snippet_and_sums_the_browser_tree():
    """브라우저 묶음(본 + 자손) RSS 가 상한을 넘으면 조각 프로세스를 죽인다 — 275GB 까지 키운 실측 (#973)"""
    sys.path.insert(0, str(SCRIPTS))
    sys.path.insert(0, str(COMMON_SCRIPTS))
    from pro_launch.commands.web import browser_memory

    # 본 10 · 렌더러 20 · 렌더러의 자식 30 · 남의 프로세스 999 (MB, ps 는 KB)
    table = [(10, 1, 10 * 1024), (11, 10, 20 * 1024), (12, 11, 30 * 1024), (99, 1, 999 * 1024)]
    assert browser_memory.tree_rss_megabytes(table, 10) == 60
    assert browser_memory.tree_rss_megabytes(table, 4242) is None

    started = time.time()
    result = browser_memory.run_with_memory_cap([sys.executable, "-c", "import time; time.sleep(30)"], "{}",
                                                timeout_seconds=30, browser_pid=10, limit_megabytes=8192,
                                                read_rss=lambda pid: 9000)
    assert result == {"status": "memory_exceeded", "rss_megabytes": 9000}
    assert time.time() - started < 10
