"""내부망 · 윈도우 한글 환경에서 web open 이 깨지던 자리.

- 자체서명 인증서는 ERR_CERT_AUTHORITY_INVALID 로 막히는데 고칠 길을 안 알려 줬다.
- 프로필 사용 여부를 `ps` 로 확인해 윈도우에선 항상 예외 → 남은 잠금이 영영 안 치워졌다.
- PowerShell 출력을 기본 코드페이지로 읽으면 stdout 이 None 이 돼 TypeError 로 죽었다.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from pro_launch.commands.web.actions import open as web_open  # noqa: E402
from pro_launch.runtime import procs  # noqa: E402


def test_인증서_오류면_ignore_cert_errors_를_안내한다():
    hint = web_open._cert_hint("Page.goto: net::ERR_CERT_AUTHORITY_INVALID at https://10.0.0.1/")
    assert hint and "--ignore-cert-errors" in hint


def test_인증서와_무관한_오류에는_힌트를_붙이지_않는다():
    assert web_open._cert_hint("net::ERR_CONNECTION_REFUSED") is None


def test_프로세스_목록을_못_읽으면_쓰는_중으로_본다(monkeypatch, tmp_path):
    monkeypatch.setattr(web_open, "process_command_lines", lambda: None)
    assert web_open._profile_in_use(tmp_path) is True


def test_프로필_경로가_명령줄에_있으면_쓰는_중이다(monkeypatch, tmp_path):
    monkeypatch.setattr(web_open, "process_command_lines",
                        lambda: f'chrome.exe --user-data-dir="{tmp_path}" about:blank')
    assert web_open._profile_in_use(tmp_path) is True


def test_명령줄에_없으면_쓰는_중이_아니다(monkeypatch, tmp_path):
    monkeypatch.setattr(web_open, "process_command_lines", lambda: "notepad.exe\nchrome.exe --other")
    assert web_open._profile_in_use(tmp_path) is False


def test_출력이_None_이어도_죽지_않는다(monkeypatch):
    class R:
        stdout = None
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: R())
    assert procs.process_command_lines() is None
