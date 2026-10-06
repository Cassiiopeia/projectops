"""체인지로그 안내와 PR 요약 댓글의 언어 전환(#787): 한국어는 이관 전과 바이트 동일, 영문은 한글이 없다."""
import re
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import changelog_notice as cn  # noqa: E402
import pr_summary_comment as ps  # noqa: E402

GOLD = Path(__file__).resolve().parent / "golden"
HANGUL = re.compile(r"[가-힣]")
RESULT = {"provider": "commit", "attempted": ["copilot", "openai:gemini", "commit"], "failed": ["copilot", "openai:gemini"]}
RAW = "<!-- x -->\n\n## Summary by CodeRabbit\n\n## 릴리스 노트\n\n* **새 기능**\n  * 항목 하나\n\n<!-- end -->\n"


def gold(name):
    return (GOLD / name).read_text(encoding="utf-8")


def test_한국어_요약표는_이관_전과_바이트_동일하다():
    assert cn.build_summary(RESULT, "ko") == gold("changelog_notice_summary_ko.md")
    assert cn.build_summary({"provider": None, "attempted": [], "failed": []}, "ko") == gold("changelog_notice_summary_empty_ko.md")


def test_한국어_안내_댓글은_이관_전과_바이트_동일하다():
    assert cn.build_comment(RESULT, "ko") == gold("changelog_notice_comment_ko.md")


def test_한국어_PR_요약_댓글은_이관_전과_바이트_동일하다():
    assert ps.build_comment(RAW, False, "ko") == gold("pr_summary_comment_ko.md")
    assert ps.build_comment(RAW, True, "ko") == gold("pr_summary_comment_app_ko.md")


def test_영문_출력에는_한글이_없다():
    # PR 요약은 릴리스 노트 본문(사용자 데이터)을 그대로 싣는다 — 그 본문을 빼고 본다
    for text in (cn.build_summary(RESULT, "en"), cn.build_summary({"provider": None, "attempted": [], "failed": []}, "en"),
                 cn.build_comment(RESULT, "en"), ps.build_comment("<!-- x -->\n\n## 릴리스 노트\n\nEnglish item\n\n<!-- end -->", True, "en")):
        assert not HANGUL.search(text), HANGUL.search(text)


def test_안내_댓글의_표식은_언어와_무관하다():
    # 같은 댓글을 찾아 갱신하는 표식이 언어마다 달라지면 댓글이 쌓인다
    for lang in ("en", "ko"):
        assert cn.build_comment(RESULT, lang).startswith(cn.MARKER)
        assert ps.build_comment(RAW, False, lang).startswith(ps.MARKER)


def test_모르는_언어는_영문으로_대체된다():
    assert cn.build_comment(RESULT, "xx") == cn.build_comment(RESULT, "en")
