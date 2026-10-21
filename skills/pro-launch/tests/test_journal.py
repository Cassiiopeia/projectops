"""작업 일지 — 자유롭게 적고, 같은 영역에 돌아오면 다시 읽힌다."""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import journal  # noqa: E402


def test_비밀값이_든_기록은_거절한다(tmp_path):
    p = tmp_path / "journal.jsonl"
    assert journal.add(p, "password=Sup3rSecret!99 로 로그인").get("error") == "secret_detected"
    assert journal.load(p) == []

