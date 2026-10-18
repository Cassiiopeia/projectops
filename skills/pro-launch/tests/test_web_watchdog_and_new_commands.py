"""web 시간 상한 (#921) 과 새 명령의 실제 브라우저 동작 (#930 · #931)."""
from __future__ import annotations

import http.server
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from browser_cleanup import close_browser_for_test  # noqa: E402
from test_launch_cli import _j, _repo, run_cli  # noqa: E402
from common import state as common_state  # noqa: E402

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


def test_deadline_grows_with_timeout_but_stays_capped():
    from types import SimpleNamespace
    from pro_launch.commands.web.watchdog import MAXIMUM_DEADLINE_SECONDS, MINIMUM_DEADLINE_SECONDS, deadline_seconds
    assert deadline_seconds(SimpleNamespace(timeout=10), "page") == MINIMUM_DEADLINE_SECONDS
    assert deadline_seconds(SimpleNamespace(timeout=200), "page") == 260
    assert deadline_seconds(SimpleNamespace(timeout=300, tiles=50), "page") == MAXIMUM_DEADLINE_SECONDS


# ── 실제 브라우저로 새 명령 (#930 · #931) ──────────────────────────────────

_PAGE = """<!doctype html><meta charset="utf-8"><title>t</title>
<input id="otp" placeholder="otp"><input name="dup" class="d"><input name="dup2" class="d">
<input id="secret" value="S3cr3t-Val_ue">
<div id="scroller" style="height:120px;overflow:auto"><div style="height:700px">tall</div></div>
<div id="term" tabindex="0">term</div><pre id="log"></pre>
<button id="save" onclick="fetch('/save?token=abc123',{method:'POST',body:'a'})">save</button>
<script>document.getElementById('term').addEventListener('keydown',e=>{document.getElementById('log').textContent+=e.key});</script>
""".encode()


@pytest.fixture
def page_session(tmp_path):
    from pro_launch.runtime.browser import require_playwright
    if require_playwright()[0] is None:
        pytest.skip("Playwright 없음")

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _reply(self, body):
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            self._reply(_PAGE)

        def do_POST(self):
            self._reply(b"ok")
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    project = _repo(tmp_path, f"hyg-{os.getpid()}", remote=None)
    state = common_state.state_dir("launch", project)

    def web(*args):
        return _j(run_cli("web", *args, "--root", str(project))[1])
    web("open", "--url", f"http://127.0.0.1:{server.server_port}/")
    try:
        yield web
    finally:
        close_browser_for_test(run_cli, project, state)
        server.shutdown()
        shutil.rmtree(state, ignore_errors=True)


@pytest.mark.local_only
def test_new_web_commands_against_a_real_page(page_session):
    web = page_session
    # 요청 캡처: 비밀 쿼리는 가리고 GET 이 아닌 것만
    clicked = web("click", "--selector", "#save", "--capture-requests")
    assert [(r["method"], r["status"]) for r in clicked["requests"]] == [("POST", 200)]
    assert "abc123" not in json.dumps(clicked["requests"])
    # 키 단위 입력은 keydown 을 일으킨다
    assert web("type", "--selector", "#term", "--keys", "ls", "--delay-ms", "5")["typed_characters"] == 2
    assert web("text", "--selector", "#log")["text"].strip() == "ls"
    # 선택자가 둘 이상 맞으면 알린다
    multiple = web("type", "--selector", "input.d, input[name=dup2]", "--text", "x")
    assert multiple["ok"] and multiple["matches"] == 2 and multiple["warning"] == "multiple_matches"
    # role=textbox 는 그냥 input 도 잡고, 못 찾아도 items 키가 있다
    assert web("find", "--role", "textbox", "--all")["total"] >= 4
    assert web("find", "--role", "textbox", "--text", "nope-nothing")["items"] == []
    # 값은 출력 없이 저장하고 다른 칸에 다시 넣는다
    saved = web("value", "--selector", "#secret", "--save-env", "CLIENT_SECRET")
    assert "S3cr3t" not in json.dumps(saved) and saved["length"] == 13
    assert web("type", "--selector", "#otp", "--text-env", "CLIENT_SECRET")["ok"]
    assert web("value", "--selector", "#otp")["sha256_prefix"] == saved["sha256_prefix"]
    # 안쪽 스크롤 영역은 바닥까지 조각으로
    tiles = web("shot", "--container", "#scroller", "--out", "tiles")
    assert tiles["is_complete"] and tiles["tiles"] >= 2 and len(tiles["files"]) == tiles["tiles"]
    # 별칭
    assert web("viewport", "--width", "800", "--height", "600")["viewport"] == [800, 600]
