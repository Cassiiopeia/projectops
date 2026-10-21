"""launch_cli 단위 테스트 (#629).

pro-agent-test 에서 옮겨 온 실행·캡처 계약(web · device · shrink · webp · output · env)과
새 명령(app · web viewport · web route · http · stealth · 저장 폴더 이전)을 본다.

기기·브라우저·서버가 없어도 돌아야 한다. 진짜 브라우저가 필요한 것만 `local_only` 다.

⚠️ 브라우저 테스트는 HOME 을 바꾸지 않는다 — macOS Chrome 은 HOME 이 바뀌면 이동 중
멈춘다(실측). 대신 상태 루트(PROJECTOPS_HOME)만 conftest 가 테스트마다 임시로 돌린다 (#836).
"""
from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

CLI = Path(__file__).resolve().parents[1] / "scripts" / "launch_cli.py"
sys.path.insert(0, str(CLI.parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import app_input  # noqa: E402
import launch_cli  # noqa: E402
from pro_launch.commands import shrink as shrink_cmd  # noqa: E402
from pro_launch.commands.app import gestures as app_gestures  # noqa: E402
from pro_launch.commands.web import session as web_session  # noqa: E402
from pro_launch.runtime import browser as rt_browser, devices as rt_devices  # noqa: E402
from common import state as common_state  # noqa: E402


def run_cli(*args, home: Path | None = None, cwd: Path | None = None, env_extra=None):
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    # 기록은 홈에 쌓인다. 테스트가 사용자의 진짜 기록을 건드리면 안 된다.
    if home is not None:
        env["HOME"] = str(home)
        env["USERPROFILE"] = str(home)   # Windows
    # 상태 루트는 conftest 가 테스트마다 임시로 준다. 그 밖에서 불려도 실제 홈에 쓰지 않게 한다 (#836)
    if not env.get("PROJECTOPS_HOME"):
        import tempfile
        env["PROJECTOPS_HOME"] = str((home or Path(tempfile.mkdtemp())) / ".projectops")
    for k in ("SHOT_DIR", "RUN_DIR", "DEV", "PKG"):
        env.pop(k, None)
    env.update(env_extra or {})
    r = subprocess.run([sys.executable, str(CLI), *args], capture_output=True, text=True,
                       encoding="utf-8", env=env, cwd=str(cwd) if cwd else None)
    return r.returncode, r.stdout or "", r.stderr or ""


def _j(out: str) -> dict:
    return json.loads(out.strip().splitlines()[-1])


def _repo(tmp: Path, name: str = "proj", remote: str | None = "https://github.com/acme/thing.git") -> Path:
    proj = tmp / name
    proj.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(proj)], check=True)
    if remote:
        subprocess.run(["git", "-C", str(proj), "remote", "add", "origin", remote], check=True)
    return proj


@contextlib.contextmanager
def playwright_hidden():
    """설치 여부와 무관하게 '없는 상태'를 만든다 — 깔린 기계에서도 이 검사가 돌아야 한다 (#591)."""
    names = [k for k in sys.modules if k == "playwright" or k.startswith("playwright.")]
    saved = {k: sys.modules[k] for k in names}
    for k in names:
        del sys.modules[k]
    sys.modules["playwright"] = None
    sys.modules["playwright.sync_api"] = None
    try:
        yield
    finally:
        sys.modules.pop("playwright", None)
        sys.modules.pop("playwright.sync_api", None)
        sys.modules.update(saved)


# ── 명령 표면 ─────────────────────────────────────────────────────────────

def test_bad_args_still_answer_json():
    rc, out, _ = run_cli("app", "fly")
    assert rc != 0 and _j(out)["code"] == "bad_args"


def test_unexpected_handler_exception_becomes_json(monkeypatch, capsys):
    """어떤 핸들러든 예외가 새도 main 이 JSON 으로 감싼다."""
    def boom(*args, **kwargs):
        raise RuntimeError("boom")
    monkeypatch.setattr(shrink_cmd, "shrink", boom)
    rc = launch_cli.main(["shrink", "x.png"])
    d = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert rc == 1 and d["code"] == "handler_error" and "boom" in d["error"]


# ── Playwright 가 없을 때 무엇을 말해 주나 ────────────────────────────────

def test_web_reports_missing_playwright_with_install_hint():
    with playwright_hidden():
        ok, err = rt_browser.require_playwright()
    assert ok is None
    assert err["code"] == "playwright_missing"
    assert err["fix"].startswith("web setup"), err
    assert "venv" in err["manual"], err
    assert "설치할까요" in err["ask_user"], err


# ── 저장 자리 · 이전 ──────────────────────────────────────────────────────

def _old_dir(home: Path) -> Path:
    d = home / ".projectops" / "agent-test" / "acme__thing"
    d.mkdir(parents=True)
    (d / "devices.json").write_text('{"package":"com.a","bindings":[]}', encoding="utf-8")
    (d / "access.json").write_text('{"base_url":"http://x"}', encoding="utf-8")
    (d / "learned.json").write_text("{}", encoding="utf-8")
    (d / "shots").mkdir()
    return d


def test_migration_does_not_move_a_browser_in_use(tmp_path, monkeypatch):
    """떠 있는 브라우저의 프로필을 옮기면 깨진다 — 미루고 알린다."""
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    proj = _repo(tmp_path)
    old = _old_dir(home)
    (old / "browser.json").write_text(json.dumps({"pid": os.getpid()}), encoding="utf-8")
    (old / ".browser-profile").mkdir()

    r = common_state.migrate_launch(proj)
    assert "browser.json" not in r["moved"] and ".browser-profile" not in r["moved"]
    assert any("브라우저" in w for w in r["warnings"])
    # 옛 자리를 계속 읽는다 — 기능이 멈추지 않는다
    assert common_state.launch_file(proj, "browser.json") == old / "browser.json"


# ── access ───────────────────────────────────────────────────────────────

def test_access_refuses_raw_secret(tmp_path):
    proj = _repo(tmp_path)
    _, out, _ = run_cli("access", "set", "--root", str(proj), "--key", "db",
                        "--json", '{"password": "hunter2supersecret"}', home=tmp_path)
    d = _j(out)
    assert d["code"] == "secret_in_value" and "hunter2" not in json.dumps(d["found"])


# ── logs: 실패한 명령을 성공으로 보고하지 않는다 (#704) ───────────────────

def test_logs_reports_command_not_found_as_failure(tmp_path):
    rc, out, _ = run_cli("logs", "--command", "nonexistent_zzz_cmd", home=tmp_path / "h", cwd=tmp_path)
    d = _j(out)
    assert d["ok"] is False and d["code"] == "logs_failed", d
    assert rc != 0


# ── app ──────────────────────────────────────────────────────────────────

_DEV2 = {"android": ["emulator-5554"],
         "ios_booted": ["iPhone 16 [3F328F1A-16D1-453B-A0D3-94CDC21C4189]"],
         "android_avds": [], "adb_path": "/x/adb", "emulator_path": None}


def test_pick_device_refuses_to_guess_between_several(monkeypatch):
    """여러 대인데 고르지 않으면 엉뚱한 기기를 찍는다 — 멈춘다."""
    monkeypatch.setattr(rt_devices, "list_devices", lambda: _DEV2)
    monkeypatch.delenv("DEV", raising=False)
    assert rt_devices.pick_device(None)[0] is None
    assert rt_devices.pick_device("emulator-5554")[:2] == ("android", "emulator-5554")
    assert rt_devices.pick_device("3F328F1A-16D1-453B-A0D3-94CDC21C4189")[0] == "ios"
    monkeypatch.setenv("DEV", "emulator-5554")
    assert rt_devices.pick_device(None)[1] == "emulator-5554"


# ── web viewport · route (브라우저 없이 기록된다) ──────────────────────────

def _root_for_web(tmp):
    return _repo(tmp, "webproj", remote=None)


def test_route_handler_takes_the_request_as_second_argument():
    """Playwright 는 handler(route, request) 로 부른다. 기본 인자로 규칙을 묶으면 request 가 덮는다 (실측)."""
    got = {}

    class FakeRoute:
        def fulfill(self, **kw):
            got.update(kw)

        def continue_(self):
            got["continued"] = True

    h = web_session._route_handler({"status": 500, "body": "x", "content_type": "text/plain"})
    h(FakeRoute(), object())
    assert got["status"] == 500 and got["body"] == "x"

    got.clear()
    web_session._route_handler({"status": None, "delay_ms": 0})(FakeRoute(), object())
    assert got == {"continued": True}


# ── 앱 탭 · 스와이프 (#826) ───────────────────────────────────────────────

def test_every_registered_backend_implements_the_contract():
    """새 백엔드를 등록하면 계약 메서드를 다 채웠는지 여기서 걸린다 (기여자 안전망)."""
    for name, make in app_input.BACKENDS.items():
        be = make()
        assert be.name == name
        for m in ("tap_ratio", "swipe_ratio", "grab", "nodes", "locale"):
            assert getattr(type(be), m) is not getattr(app_input.Backend, m), f"{name}.{m} 미구현"
        needed = "tap_selector" if be.selects_itself else "tap_xy"
        assert getattr(type(be), needed) is not getattr(app_input.Backend, needed), f"{name}.{needed} 미구현"
        assert be.install_hint


class _FrameBackend(app_input.Backend):
    name = "fake"

    def __init__(self, frames):
        self.frames, self.i = frames, 0

    def grab(self, dev):
        f = self.frames[min(self.i, len(self.frames) - 1)]
        self.i += 1
        return f


def _after_args(tmp_path):
    import argparse
    return argparse.Namespace(shot=str(tmp_path / "after.png"), root=str(tmp_path))


def _no_wait(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda s: None)
    monkeypatch.setattr(app_gestures, "finish_shot", lambda raw, explicit, args: raw)


def test_after_shot_waits_for_change_then_stability(monkeypatch, tmp_path):
    """동작 전 화면이 두 번 연속 나와도 '멈췄다'로 보지 않는다 — Android 실측 사고(전환 전 장면을 찍음)."""
    _no_wait(monkeypatch)
    be = _FrameBackend([b"\x89PNG-before", b"\x89PNG-before", b"\x89PNG-mid", b"\x89PNG-new", b"\x89PNG-new"])
    r = app_gestures.after_shot(_after_args(tmp_path), be, "emu", b"\x89PNG-before")
    assert r["screen_changed"] is True
    assert Path(r["shot"]).read_bytes() == b"\x89PNG-new"


# ── render (#632) ────────────────────────────────────────────────────────
#
# 임시 git 레포를 픽스처로 쓴다. 렌더 명령은 셸로 PNG 를 만드는 흉내만 낸다 —
# 스크립트가 하는 일은 실행 · 수집 · 청소 · 흔적 검사뿐이라 그걸로 충분하다.


_PNG = "printf '\\211PNG\\r\\n\\032\\n' > "


def _render_repo(tmp_path):
    proj = _repo(tmp_path, "renderproj", remote=None)
    (proj / "keep.txt").write_text("x", encoding="utf-8")
    subprocess.run(["git", "-C", str(proj), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(proj), "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "init"], check=True)
    return proj


def _render(proj, tmp, *args, shots=None):
    shots = shots or tmp / "shots"
    shots.mkdir(exist_ok=True)
    rc, out, err = run_cli("render", *args, "--root", str(proj), home=tmp,
                           env_extra={"SHOT_DIR": str(shots)})
    return _j(out), shots


def test_render_refuses_to_clean_outside_the_repo(tmp_path):
    proj = _render_repo(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("남의 파일", encoding="utf-8")
    d, _ = _render(proj, tmp_path, "run", "--cmd", f"{_PNG}a.png", "--collect", "*.png",
                   "--cleanup", str(outside), "--cleanup", "..")
    assert outside.exists() and d["refused_cleanup"] and "warning" in d


# ── web close: 응답 없는 브라우저에서 멈추지 않는다 (#712) ────────────────

_STUBBORN = ("import signal,time,sys\n"
             "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
             "print('up', flush=True)\n"
             "time.sleep(60)\n")


def test_web_close_does_not_hang_on_unresponsive_browser(tmp_path, monkeypatch):
    """CDP 포트는 아무도 안 듣는다 — 연결해서 close() 를 부르던 옛 경로라면 멈춘다."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    proj = _root_for_web(tmp_path)
    proc = subprocess.Popen([sys.executable, "-c", _STUBBORN], stdout=subprocess.PIPE,
                            start_new_session=True)
    # 실제로는 close 를 부르는 CLI 가 부모가 아니다. 테스트에서는 우리가 부모라 죽은 뒤 거둬 줘야 좀비로 안 남는다
    threading.Thread(target=proc.wait, daemon=True).start()
    try:
        proc.stdout.readline()
        state_f = rt_browser.state_path(proj)
        rt_browser.write_state(state_f, {"cdp": "http://127.0.0.1:1", "pid": proc.pid})
        rc, out, err = run_cli("web", "close", "--root", str(proj), home=tmp_path)
        d = _j(out)
        assert d["ok"] is True and d.get("action") == "close", d
        assert proc.wait(timeout=5) is not None
        assert not state_f.exists()
    finally:
        if proc.poll() is None:
            proc.kill()


# ── 캡처 자리 (#972) ─────────────────────────────────────────────────────

# 다른 세션의 get-output-path 폴더에 캡처가 저장됐다 — last_run 은 세션별이고 남의 것은 쓰지 않는다
def test_last_run_folder_is_never_another_sessions(tmp_path, monkeypatch):
    from pro_launch.runtime import shots
    monkeypatch.delenv("SHOT_DIR", raising=False)
    proj = _repo(tmp_path)
    run_dir = tmp_path / "run-a"
    run_dir.mkdir()
    monkeypatch.setenv("LAUNCH_SESSION", "session-a")
    shots.record_last_run(proj, run_dir, run_dir / "screenshots")
    assert shots.resolve_shot_folder(proj) == (run_dir / "screenshots", "last_run")
    monkeypatch.setenv("LAUNCH_SESSION", "session-b")
    assert shots.resolve_shot_folder(proj)[1] == "state"


# web shot --out <확장자 없는 경로> 가 unsupported mime type 으로 실패했다
def test_explicit_shot_path_without_extension_gets_one(tmp_path):
    from pro_launch.runtime import shots
    path, is_explicit = shots.shot_target(tmp_path, str(tmp_path / "out" / "02_empty"))
    assert is_explicit and path.name == "02_empty.png"
