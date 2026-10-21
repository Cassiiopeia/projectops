"""app type 의 입력기 원복·대조 (#926). 기기 없이 대역으로 검사한다."""
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
from pro_launch.commands.app import android_ime  # noqa: E402
from pro_launch.commands.app.actions import type_  # noqa: E402

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


def test_restores_even_when_typing_raises():
    shell = FakeShell(KOREAN_GBOARD, "ko_KR", (MAESTRO_IME,), enabled=(MAESTRO_IME,))
    with pytest.raises(RuntimeError):
        with android_ime.ascii_input_method(shell, "auto"):
            raise RuntimeError("boom")
    assert shell.default == KOREAN_GBOARD
    assert f"ime disable {MAESTRO_IME}" not in shell.commands   # 원래 켜져 있던 입력기는 끄지 않는다


# ── #926 필드 대조 ──────────────────────────────────────────────────────


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
