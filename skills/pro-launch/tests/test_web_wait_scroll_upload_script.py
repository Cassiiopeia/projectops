"""web 의 가려진 클릭 · 아이콘 버튼 · iframe · 기다리기 · 스크롤 · 올리기 · 조각 실행 (#879 · #877 · #880 · #876 · #904).

여기서 지키는 것:
  · 고정 머리글이 덮으면 가운데로 옮겨 다시 누르고, 그래도 덮이면 덮은 것을 알려 --dom-click 을 안내한다
  · find 는 아이콘 리거처를 icon:<이름> 으로, aria 는 aria-label · title 로 채운다
  · --frame <이름|iframe 선택자|주소 일부> 로 iframe 안에서 찾고 · 넣고 · 누르고 · 확인한다
  · wait 는 주어진 조건이 모두 맞으면 끝나고, 아니면 wait_timeout + 지금 주소
  · upload 는 없는 파일 · 허용 폴더 밖 · accept 밖 · 여러 개 금지를 code 로 가른다
  · script 는 결과를 result 에, 예외는 script_failed, 상한은 script_timeout, 저장된 비밀 값은 가린다
"""
from __future__ import annotations

import argparse
import contextlib
import http.server
import os
import shutil
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_launch_cli import _j, _repo, run_cli  # noqa: E402
from pro_launch.commands.web import frames as web_frames  # noqa: E402
from pro_launch.commands.web.actions import script as web_script  # noqa: E402
from pro_launch.commands.web.actions import upload as web_upload  # noqa: E402
from pro_launch.runtime import browser as rt_browser  # noqa: E402
from common import state as common_state  # noqa: E402


# ── upload (#876) ─────────────────────────────────────────────────────────

def test_upload_files_must_exist_and_stay_inside_allowed_folders(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SHOT_DIR", str(tmp_path / "run"))
    (tmp_path / "a.png").write_bytes(b"x")
    paths, failure = web_upload.resolve_upload_files("a.png", tmp_path)
    assert failure is None and paths == [(tmp_path / "a.png").resolve()]
    assert web_upload.resolve_upload_files("nope.png", tmp_path)[1]["code"] == "file_not_found"
    outside = tmp_path.parent / f"outside-{os.getpid()}.png"
    outside.write_bytes(b"x")
    try:
        assert web_upload.resolve_upload_files(str(outside), tmp_path)[1]["code"] == "file_outside_allowed"
    finally:
        outside.unlink()
    assert web_upload.resolve_upload_files(" , ", tmp_path)[1]["code"] == "files_required"


@pytest.mark.parametrize("name,accept,expected", [
    ("a.PNG", ".png,.jpg", True), ("a.png", "image/png", True), ("a.txt", "image/*", False),
])
def test_accept_attribute_rules(name, accept, expected):
    assert web_upload.is_type_accepted(Path(name), accept) is expected


# ── --frame (#877) — 가짜 페이지 ──────────────────────────────────────────

class _FakeFrame:
    def __init__(self, name, url):
        self.name, self.url = name, url


class _FakeFramePage:
    url = "http://local/"

    def __init__(self, children):
        self.main_frame = _FakeFrame("", "http://local/")
        self.frames = [self.main_frame, *children]

    def locator(self, selector):
        raise ValueError("선택자가 아니다")


def test_missing_frame_lists_what_is_there():
    page = _FakeFramePage([_FakeFrame("login", "https://idmsa.example/auth")])
    scope, failure = web_frames.frame_scope(page, argparse.Namespace(frame="nope"), "type")
    assert scope is None and failure["code"] == "frame_not_found"
    assert failure["frames"] == [{"name": "login", "url": "https://idmsa.example/auth"}]
    assert web_frames.frame_scope(page, argparse.Namespace(frame=None), "type") == (page, None)
    assert web_frames.frames_hint(_FakeFramePage([])) == {}


# ── script (#904) ─────────────────────────────────────────────────────────

def test_script_payload_masks_saved_secrets_and_truncates(monkeypatch):
    monkeypatch.setattr(web_script.credentials, "load_all",
                        lambda: {"apple": {"account": "me@x.com", "password": "hunter2!!"}})
    secrets = web_script.saved_secret_values()
    assert secrets == ["hunter2!!"]
    ok = web_script.build_payload({"ok": True, "result_text": '{"pw": "hunter2!!"}', "stdout": "typed hunter2!!",
                                   "url": "u", "title": "t"}, secrets)
    assert ok["result"] == {"pw": "***"} and ok["stdout"] == "typed ***"
    failed = web_script.build_payload({"ok": False, "error": "Error: bad hunter2!!"}, secrets)
    assert failed["code"] == "script_failed" and "hunter2" not in str(failed)
    long_text = '"' + "a" * (web_script.MAXIMUM_RESULT_CHARS + 10) + '"'
    cut = web_script.build_payload({"ok": True, "result_text": long_text}, [])
    assert cut["result_truncated"] is True and len(cut["result"]) == web_script.MAXIMUM_RESULT_CHARS


# ── 실제 브라우저 ─────────────────────────────────────────────────────────

_PAGE = """<!doctype html><meta charset="utf-8"><title>probe</title>
<style>#bar{position:fixed;top:0;left:0;right:0;height:120px;background:#ccc;z-index:10}
body{margin:0;padding-top:130px} .card{height:200px} #box{height:150px;overflow-y:auto} #box div{height:80px}</style>
<div id="bar" class="sticky">머리글</div>
<div class="card"><button id="del1" aria-label="01.png delete" onclick="document.title='del1'">
<span class="material-icons">delete</span></button></div><div class="card">c2</div><div class="card">c3</div>
<div id="box"><div>a</div><div>b</div><div>c</div><div>깊은 항목</div></div>
<input type="file" id="f" accept="image/png" hidden onchange="document.getElementById('st').textContent='올림'">
<button id="drop" onclick="document.getElementById('f').click()">끌어다 놓기</button><p id="st">대기</p><p id="later"></p>
<iframe name="login" src="/frame.html"></iframe>
<script>setTimeout(()=>{document.getElementById('later').textContent='저장 완료'},1500)</script>""".encode()
_FRAME = b'<!doctype html><meta charset="utf-8"><input id="acc"><button onclick="this.textContent=\'pressed\'">go</button>'


@contextlib.contextmanager
def _session(tmp_path):
    if rt_browser.require_playwright()[0] is None:
        pytest.skip("Playwright 없음 — web setup 후 실행된다")

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            body = _FRAME if self.path.startswith("/frame") else _PAGE
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    project = _repo(tmp_path, f"wsus-{os.getpid()}", remote=None)
    try:
        yield project, f"http://127.0.0.1:{server.server_port}/"
    finally:
        run_cli("web", "close", "--root", str(project))
        server.shutdown()
        shutil.rmtree(common_state.state_dir("launch", project), ignore_errors=True)


def _web(project, *args):
    return _j(run_cli("web", *args, "--root", str(project), cwd=project)[1])


@pytest.mark.local_only
def test_real_browser_cover_icon_frame_wait_scroll_upload_script(tmp_path):
    with _session(tmp_path) as (project, url):
        assert _web(project, "open", "--url", url)["ok"]
        found = _web(project, "find", "--role", "button")
        assert found["items"][0]["text"] == "icon:delete" and found["items"][0]["aria"] == "01.png delete", found
        _web(project, "scroll", "--by", "60")
        clicked = _web(project, "click", "--ref", "1")
        assert clicked["ok"] and "#bar" in clicked["recovery"]["covered_by"], clicked
        assert _web(project, "type", "--frame", "login", "--selector", "#acc", "--text", "me")["ok"]
        assert _web(project, "click", "--frame", "frame.html", "--selector", "text=go")["ok"]
        assert _web(project, "assert", "--frame", "login", "--text", "pressed")["ok"]
        assert _web(project, "find", "--frame", "nope")["code"] == "frame_not_found"
        assert _web(project, "wait", "--text", "저장 완료", "--timeout", "10")["ok"]
        assert _web(project, "wait", "--gone", "머리글", "--timeout", "1")["code"] == "wait_timeout"
        assert _web(project, "scroll", "--to", "깊은 항목")["ok"]
        (project / "a.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")
        (project / "b.txt").write_text("x")
        uploaded = _web(project, "upload", "--files", "a.png")
        assert uploaded["ok"] and uploaded["input_files"] == ["a.png"], uploaded
        assert _web(project, "upload", "--files", "b.txt")["code"] == "type_not_accepted"
        _web(project, "find", "--text", "끌어다")
        assert _web(project, "upload", "--files", "a.png", "--click-ref", "1")["via"] == "file_chooser"
        snippet = project / "count.py"
        snippet.write_text("print('hi')\npage.locator('.card').count()\n")
        ran = _web(project, "script", "--file", str(snippet))
        assert ran["result"] == 3 and ran["stdout"] == "hi\n", ran
        snippet.write_text("page.wait_for_timeout(30000)\n")
        assert _web(project, "script", "--file", str(snippet), "--timeout", "1")["code"] == "script_timeout"
        assert _web(project, "text", "--max-chars", "10")["ok"], "조각을 멈춘 뒤에도 브라우저를 쓸 수 있어야 한다"
