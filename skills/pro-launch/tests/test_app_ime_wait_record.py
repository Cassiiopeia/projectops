"""app type 의 입력기 전환·대조 (#926), app wait · record · burst · shot 별칭·시각 (#928, #931). 기기 없이 대역으로 검사한다."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import app_input  # noqa: E402
from pro_launch.commands.app import android_ime, burst, steps as steps_module  # noqa: E402
from pro_launch.commands.app.actions import record, shot, type_, wait  # noqa: E402

KOREAN_GBOARD = "com.google.android.inputmethod.latin/com.android.inputmethod.latin.LatinIME"
MAESTRO_IME = android_ime.MAESTRO_INPUT_METHOD
SECRET = "Pa55w0rd!"


def field_xml(text: str, is_password: bool = False) -> str:
    return (f'<hierarchy><node class="android.widget.EditText" text="{text}" focused="true" '
            f'password="{"true" if is_password else "false"}" bounds="[0,0][10,10]"/></hierarchy>')


def probe_output(default: str, subtype_locale: str = "", installed: tuple[str, ...] = (), enabled: tuple[str, ...] = ()):
    return "\n@@\n".join([default, f"mSubtypeLocale={subtype_locale}" if subtype_locale else "", "ko-KR\n",
                          "\n".join(installed), "\n".join(enabled)])


class FakeShell:
    """android_ime 의 셸 대역 — 명령을 기록하고 IME 상태를 흉내 낸다."""

    def __init__(self, default: str, subtype_locale: str, installed: tuple[str, ...], enabled: tuple[str, ...] = ()):
        self.default, self.commands = default, []
        self.output = probe_output(default, subtype_locale, installed, enabled)

    def __call__(self, command: str) -> str:
        self.commands.append(command)
        if command.startswith("settings get secure default_input_method") and "@@" not in command:
            return self.default + "\n"
        if command.startswith("settings get secure default_input_method"):
            return self.output
        if command.startswith("ime set "):
            self.default = command.split()[2]
        return ""


# ── #926 입력기 판정 · 전환 · 원복 ───────────────────────────────────────

def test_korean_gboard_is_composing_but_english_gboard_is_not():
    korean = android_ime.parse_probe(probe_output(KOREAN_GBOARD, "ko_KR"))
    english = android_ime.parse_probe(probe_output(KOREAN_GBOARD, "en_US"))
    assert android_ime.is_composing(korean) and not android_ime.is_composing(english)


def test_switches_to_maestro_ime_while_typing_and_restores_it():
    shell = FakeShell(KOREAN_GBOARD, "ko_KR", (KOREAN_GBOARD, MAESTRO_IME))
    with android_ime.ascii_input_method(shell, "auto") as report:
        assert shell.default == MAESTRO_IME and report["switched_to"] == MAESTRO_IME
    assert shell.default == KOREAN_GBOARD and report["restored"] is True
    assert f"ime enable {MAESTRO_IME}" in shell.commands and f"ime disable {MAESTRO_IME}" in shell.commands


def test_ime_change_is_recorded_for_device_release_and_forgotten_after_restore(monkeypatch):
    calls = []
    monkeypatch.setattr(android_ime, "record_device_setting", lambda *a, **k: calls.append(("record", a)))
    monkeypatch.setattr(android_ime, "pop_device_setting", lambda *a, **k: calls.append(("pop", a)))
    shell = FakeShell(KOREAN_GBOARD, "ko_KR", (KOREAN_GBOARD, MAESTRO_IME))
    with android_ime.ascii_input_method(shell, "auto", "emulator-5554"):
        # 입력 중에는 되돌리는 명령이 기록돼 있다 (프로세스가 죽어도 device release 가 되돌린다)
        kind, args = calls[0]
        assert kind == "record" and args[0] == "emulator-5554" and args[1] == "ime" and args[2] == KOREAN_GBOARD
        assert args[3][0][-3:] == ["shell", "ime", "set"] or args[3][0][-1] == KOREAN_GBOARD
    assert calls[-1][0] == "pop"   # 정상 복원되면 기록을 지운다


def test_restores_even_when_typing_raises():
    shell = FakeShell(KOREAN_GBOARD, "ko_KR", (MAESTRO_IME,), enabled=(MAESTRO_IME,))
    with pytest.raises(RuntimeError):
        with android_ime.ascii_input_method(shell, "auto"):
            raise RuntimeError("boom")
    assert shell.default == KOREAN_GBOARD
    assert f"ime disable {MAESTRO_IME}" not in shell.commands   # 원래 켜져 있던 입력기는 끄지 않는다


@pytest.mark.parametrize("mode,default,installed,reason", [
    ("keep", KOREAN_GBOARD, (MAESTRO_IME,), "keep"),
    ("auto", KOREAN_GBOARD, (), "no_ascii_input_method_installed"),
    ("auto", "com.other.ime/.Latin", (MAESTRO_IME,), "not_composing"),
])
def test_does_not_switch_when_not_needed_or_impossible(mode, default, installed, reason):
    shell = FakeShell(default, "ko_KR", installed)
    with android_ime.ascii_input_method(shell, mode) as report:
        pass
    assert report["reason"] == reason and not any(c.startswith("ime set") for c in shell.commands)


# ── #926 필드 대조 ──────────────────────────────────────────────────────

def test_mismatch_masks_secret_value():
    result = android_ime.verify_typed_text(field_xml("ㅈㅏㅎㅛ"), SECRET, is_secret=True)
    assert result["verification"] == "mismatch" and result["expected_length"] == len(SECRET)
    assert "visible_value" not in result and result["visible_has_non_ascii"] is True


def test_mismatch_shows_visible_value_for_plain_text():
    assert android_ime.verify_typed_text(field_xml("ㅊㅗ"), "cho", is_secret=False)["visible_value"] == "ㅊㅗ"


def test_password_field_and_missing_field_are_skipped():
    assert android_ime.verify_typed_text(field_xml("", True), "x", True)["verification"] == "skipped_password_field"
    assert android_ime.verify_typed_text("<hierarchy/>", "x", True)["verification"] == "skipped_no_focused_field"
    assert android_ime.verify_typed_text("", "x", True)["verification"] == "skipped_read_failed"


class FakeAndroidBackend:
    name = "android"

    def __init__(self, shown_text: str):
        self.shown_text, self.submitted = shown_text, False

    def _adb(self, dev, *args, **kwargs):
        text = {"exec-out": field_xml(self.shown_text)}.get(args[0], "")
        if args[:3] == ("shell", "input", "keyevent"):
            self.submitted = True
        return subprocess.CompletedProcess(args, 0, text, "")

    def input_text(self, dev, value, submit=False):
        return True, ""


def type_args(**values):
    base = dict(device="EMU1", pkg=None, cred=None, cred_field=None, text_env="PL_TEST_SECRET", submit=False,
                ime="keep", started_monotonic=time.monotonic())
    base.update(values)
    return argparse.Namespace(**base)


@pytest.fixture
def android_type(monkeypatch):
    monkeypatch.setenv("PL_TEST_SECRET", SECRET)
    monkeypatch.setattr(type_, "pick_device", lambda want: ("android", "EMU1", {}))
    monkeypatch.setattr(type_, "sdk_tool", lambda name: "/x/adb")


def test_type_reports_mismatch_without_leaking_secret_and_does_not_submit(android_type, monkeypatch, capsys):
    backend = FakeAndroidBackend("ㅔㅁㄴㄴ")
    monkeypatch.setattr(app_input, "get_backend", lambda platform, app_id=None: backend)
    type_._app_type(type_args(submit=True))
    data = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert data["ok"] is False and data["code"] == "typed_text_mismatch" and data["expected_length"] == len(SECRET)
    assert SECRET not in json.dumps(data) and "visible_value" not in data and backend.submitted is False


def test_type_succeeds_when_field_shows_the_value(android_type, monkeypatch, capsys):
    backend = FakeAndroidBackend(SECRET)
    monkeypatch.setattr(app_input, "get_backend", lambda platform, app_id=None: backend)
    type_._app_type(type_args(submit=True))
    data = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert data["ok"] and data["verification"] == "matched" and backend.submitted is True


# ── #928 wait · gone 단계 · burst ───────────────────────────────────────

class FakeWaitBackend:
    name = "android"
    device_failure = None

    def __init__(self, screens):
        self.screens = list(screens)

    def nodes(self, dev):
        return self.screens.pop(0) if len(self.screens) > 1 else self.screens[0]


def node(text: str) -> dict:
    return app_input.make_node(text, "", "", True, "[0,0][10,10]")


def wait_args(**values):
    base = dict(device="EMU1", pkg=None, sel_text="로드 중", sel_id=None, sel_desc=None, gone=False, timeout=5,
                interval=0.2, started_monotonic=time.monotonic())
    base.update(values)
    return argparse.Namespace(**base)


def run_wait(monkeypatch, capsys, screens, **values):
    backend = FakeWaitBackend(screens)
    monkeypatch.setattr(wait, "backend_for", lambda args: (backend, "EMU1", None))
    monkeypatch.setattr(wait, "MINIMUM_POLL_INTERVAL_SECONDS", 0)
    wait._app_wait(wait_args(**values))
    return json.loads(capsys.readouterr().out.strip().splitlines()[-1])


def test_wait_gone_returns_when_element_disappears(monkeypatch, capsys):
    data = run_wait(monkeypatch, capsys, [[node("로드 중")], [node("로드 중")], [node("홈")]], gone=True, interval=0)
    assert data["ok"] and data["polls"] == 3 and data["condition"].endswith("gone")


def test_wait_gone_times_out_while_element_stays(monkeypatch, capsys):
    data = run_wait(monkeypatch, capsys, [[node("로드 중")]], gone=True, timeout=0.3, interval=0)
    assert data["code"] == "wait_timeout" and "사라지지" in data["error"]


def test_wait_gone_does_not_count_unreadable_screen_as_gone(monkeypatch, capsys):
    data = run_wait(monkeypatch, capsys, [[]], gone=True, timeout=0.3, interval=0)
    assert data["ok"] is False


def test_gone_step_normalizes_to_wait_with_gone(tmp_path):
    path = tmp_path / "s.json"
    path.write_text(json.dumps([{"gone": {"text": "로드 중", "timeout": 5}},
                                {"wait": {"id": "x", "gone": True}}]), encoding="utf-8")
    loaded = steps_module.load_steps(str(path))
    assert all(s["kind"] == "wait" and s["gone"] for s in loaded)
    command = steps_module.to_maestro_commands(loaded[0], 0)[0]["extendedWaitUntil"]
    assert "notVisible" in command and "visible" not in command


def test_burst_spec_and_changed_frames():
    assert burst.burst_spec("5:0.3") == (5.0, 0.3) and burst.burst_spec("2")[1] == burst.DEFAULT_BURST_INTERVAL_SECONDS
    for bad in ("0", "abc", "999"):
        with pytest.raises(argparse.ArgumentTypeError):
            burst.burst_spec(bad)
    frames = [(0.0, b"a"), (0.4, b"a"), (0.8, b"b"), (1.2, b"b"), (1.6, b"a")]
    assert [f[0] for f in burst.changed_frames(frames)] == [0.0, 0.8, 1.6]


# ── #928 record ─────────────────────────────────────────────────────────

def test_record_start_stop_keeps_state_and_finishes_ios_file(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SHOT_DIR", str(tmp_path / "shots"))
    monkeypatch.setattr(record, "state_home", lambda root: tmp_path / "state")
    monkeypatch.setattr(record, "pick_device", lambda want: ("ios", "UDID-1", {}))
    spawned, interrupted = [], []

    def fake_spawn(command, working_folder, log_path):
        spawned.append(command)
        Path(command[-1]).write_bytes(b"mp4")
        return 4242

    monkeypatch.setattr(record.procs, "spawn_detached", fake_spawn)
    monkeypatch.setattr(record.procs, "interrupt_process", lambda pid, wait_seconds=10.0: interrupted.append(pid) or True)
    monkeypatch.setattr(record, "pid_alive", lambda pid: True)
    monkeypatch.setattr(record.shutil, "which", lambda name: None)
    base = dict(root=str(tmp_path), device="UDID-1", out="demo", gif=False, started_monotonic=time.monotonic())
    record._app_record(argparse.Namespace(session_verb="start", **base))
    started = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert started["recording"] is True and spawned[0][:5] == ["xcrun", "simctl", "io", "UDID-1", "recordVideo"]
    assert "--codec=h264" in spawned[0] and (tmp_path / "state" / "recordings").exists()
    record._app_record(argparse.Namespace(session_verb="start", **base))
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1])["code"] == "already_recording"
    record._app_record(argparse.Namespace(session_verb="stop", **base))
    stopped = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert stopped["ok"] and interrupted == [4242] and stopped["extras_skipped"] == "ffmpeg_missing"
    assert not list((tmp_path / "state" / "recordings").glob("*.json"))
    record._app_record(argparse.Namespace(session_verb="stop", **base))
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1])["code"] == "not_recording"


# ── #931 shot --shot 별칭 · #928 --time ─────────────────────────────────

def test_shot_accepts_shot_alias_and_fixes_status_bar_time(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SHOT_DIR", str(tmp_path))
    monkeypatch.setattr(shot, "pick_device", lambda want: ("ios", "UDID-1", {}))
    monkeypatch.setattr(shot.time, "sleep", lambda seconds: None)
    status_calls = []
    monkeypatch.setattr(shot, "run", lambda command, **kw: status_calls.append(command))

    def fake_capture(command, **kw):
        Path(command[-1]).write_bytes(b"png")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(shot.subprocess, "run", fake_capture)
    args = argparse.Namespace(root=str(tmp_path), device=None, out=None, shot="01_first", time="7:42",
                              clean_status=False, keep_format=True, quality=80, max_side=0)
    shot._app_shot(args)
    data = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert Path(data["file"]).name == "01_first.png" and data["status_time"] == "7:42"
    override = status_calls[0]
    assert override[override.index("--time") + 1] == "7:42" and status_calls[-1][-1] == "clear"


def test_shot_rejects_bad_time(tmp_path, monkeypatch, capsys):
    args = argparse.Namespace(root=str(tmp_path), device=None, out=None, shot=None, time="25:99", clean_status=False)
    shot._app_shot(args)
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1])["code"] == "bad_time"
