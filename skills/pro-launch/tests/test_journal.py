"""작업 일지 — 자유롭게 적고, 같은 영역에 돌아오면 다시 읽힌다."""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import journal  # noqa: E402


def test_자유_서술을_적고_최근_순으로_꺼낸다(tmp_path):
    p = tmp_path / "journal.jsonl"
    journal.add(p, "오탐만 체크, 의견은 단답형", title="제외 요청", area="web")
    journal.add(p, "수정 완료 건은 재스캔에 맡김", title="기준", area="web")
    assert [r["title"] for r in journal.recent(p, 5, area="web")] == ["기준", "제외 요청"]


def test_비밀값이_든_기록은_거절한다(tmp_path):
    p = tmp_path / "journal.jsonl"
    assert journal.add(p, "password=Sup3rSecret!99 로 로그인").get("error") == "secret_detected"
    assert journal.load(p) == []


def test_하루_한_번만_싣고_빈_날은_치지_않는다(tmp_path):
    p, seen = tmp_path / "journal.jsonl", tmp_path / "seen.json"
    assert journal.surface(p, "web", seen, today="2026-10-16") == []
    journal.add(p, "같은 날 나중에 적은 것", title="later", area="web")
    assert len(journal.surface(p, "web", seen, today="2026-10-16")) == 1
    assert journal.surface(p, "web", seen, today="2026-10-16") == []


def test_깨진_줄이_있어도_나머지를_읽는다(tmp_path):
    p = tmp_path / "journal.jsonl"
    p.write_text('{"text":"정상","title":"ok"}\n{깨진 줄\n', encoding="utf-8")
    assert [r["title"] for r in journal.load(p)] == ["ok"]
