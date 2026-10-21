"""web 브라우저 위생 · 시간 상한 · 계약 (#921 · #930 · #931).

브라우저 없이 도는 것: 버려진 브라우저 판정 · 테스트 정리 안전망 · 요청 주소 정리 · 저장 값 · timeout 상한 · 역할 별칭.
실제 브라우저가 필요한 것만 local_only.
"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from browser_cleanup import close_browser_for_test  # noqa: E402
from pro_launch.runtime.procs import kill_browser  # noqa: E402


def _fake_browser(profile: Path) -> subprocess.Popen:
    """Chrome 처럼 보이는 명령줄을 가진 잠자는 프로세스 (--remote-debugging-port · --user-data-dir)"""
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)", "--remote-debugging-port=1",
         f"--user-data-dir={profile}"], start_new_session=True)
    # 죽자마자 거둔다 — 안 거두면 좀비로 남아 pid_alive 가 계속 True 다 (진짜 고아는 PPID 1 이 거둔다)
    threading.Thread(target=proc.wait, daemon=True).start()
    return proc


# ── 테스트 정리 안전망 (#921) ──────────────────────────────────────────────

def test_cleanup_helper_kills_the_recorded_pid_when_web_close_fails(tmp_path):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    proc = _fake_browser(tmp_path / "p" / ".browser-profile")
    try:
        (state_dir / "browser.json").write_text(json.dumps({"pid": proc.pid}))
        # web close 가 아무것도 못 끈 상황 — run_cli 를 아무 일도 안 하는 가짜로 바꾼다
        close_browser_for_test(lambda *a, **k: (1, "", ""), tmp_path, state_dir)
        proc.wait(timeout=5)
        assert proc.poll() is not None
    finally:
        if proc.poll() is None:
            kill_browser(proc.pid, grace=0.5)

