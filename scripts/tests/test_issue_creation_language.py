"""이슈 작성 안내가 레포 템플릿의 언어를 따르고, 영문 태그를 안다 (#769)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CREATION = (ROOT / "skills/references/issue-creation.md").read_text(encoding="utf-8")
RULES = (ROOT / "skills/references/common-rules.md").read_text(encoding="utf-8")


def test_템플릿의_언어와_절_제목을_따르라고_안내한다():
    assert "대상 레포의 `.github/ISSUE_TEMPLATE/`" in CREATION
    assert "템플릿이 없으면 영문" in CREATION


def test_태그_표에_영문_태그가_있다():
    for tag in ("[Bug]", "[Feature Request]", "[Feature]", "[Improvement]", "[Design]", "[QA]"):
        assert tag in RULES, tag
    assert "`❗[버그]`" in RULES  # 한글 태그도 계속 유효하다
