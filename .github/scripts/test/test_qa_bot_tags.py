"""QA 봇의 제목 정제 정규식이 한글과 영문 태그를 모두 안다 (#769)."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BOT = ROOT / ".github/workflows/PROJECT-COMMON-QA-ISSUE-CREATION-BOT.yaml"


def _alternatives() -> set[str]:
    text = BOT.read_text(encoding="utf-8")
    m = re.search(r"keywordPattern = /\^\.\*\?\\\[\(([^)]*)\)\\\]/", text)
    assert m, "keywordPattern 을 찾지 못했다"
    return set(m.group(1).split("|"))


def test_한글_태그를_계속_인식한다():
    assert {"버그", "디자인", "기능요청", "기능추가", "기능개선"} <= _alternatives()


def test_영문_태그를_인식한다():
    assert {"Bug", "Design", "Feature Request", "Feature", "Improvement"} <= _alternatives()
