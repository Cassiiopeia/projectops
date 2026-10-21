"""내부망 · 윈도우 한글 환경에서 web open 이 깨지던 자리.

- 자체서명 인증서는 ERR_CERT_AUTHORITY_INVALID 로 막히는데 고칠 길을 안 알려 줬다.
- 프로필 사용 여부를 `ps` 로 확인해 윈도우에선 항상 예외 → 남은 잠금이 영영 안 치워졌다.
- PowerShell 출력을 기본 코드페이지로 읽으면 stdout 이 None 이 돼 TypeError 로 죽었다.
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from pro_launch.commands.web import recovery  # noqa: E402


def test_프로세스_목록을_못_읽으면_쓰는_중으로_본다(monkeypatch, tmp_path):
    monkeypatch.setattr(recovery, "process_command_lines", lambda: None)
    assert recovery.profile_in_use(tmp_path) is True

