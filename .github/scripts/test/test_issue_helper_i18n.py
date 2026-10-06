"""이슈 헬퍼 댓글의 언어 전환(#787): 한국어는 이관 전과 바이트 동일, 계약은 모든 언어에서 유지."""
import json
import re
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import issue_helper as ih  # noqa: E402
from i18n import contracts, messages  # noqa: E402

GOLD = Path(__file__).resolve().parent / "golden"
HANGUL = re.compile(r"[가-힣]")
# 구버전 소비자(앱 빌드 트리거 등)가 쓰는 정규식 그대로
BRANCH_RE = re.compile(r"### 브랜치\s*```\s*([\s\S]*?)\s*```")


@pytest.fixture
def workflows(tmp_path):
    for n in ("PROJECT-FLUTTER-PROJECTOPS-APP-BUILD-TRIGGER.yaml", "PROJECT-FLUTTER-ANDROID-TEST-APK.yaml",
              "PROJECT-FLUTTER-IOS-TEST-TESTFLIGHT.yaml"):
        (tmp_path / n).write_text("x")
    return tmp_path


def _body(lang, wf):
    cfg = dict(ih.DEFAULT_CONFIG)
    return ih.build_comment_body(cfg, "20261007_#1_테스트_이슈", "테스트 이슈 : feat : {변경 사항} https://x/1",
                                 ih.build_guide(wf, lang), lang)


def test_한국어_댓글은_이관_전_출력과_바이트_동일하다(workflows):
    assert _body("ko", workflows) == (GOLD / "issue_helper_comment_ko.md").read_text(encoding="utf-8")


def test_의존_기능이_없는_레포의_한국어_댓글도_바이트_동일하다():
    cfg = dict(ih.DEFAULT_CONFIG)
    body = ih.build_comment_body(cfg, "b", "m", ih.build_guide(Path("/nonexistent"), "ko"), "ko")
    assert body == (GOLD / "issue_helper_comment_bare_ko.md").read_text(encoding="utf-8")


def test_영문_댓글은_안내가_영문이고_계약은_그대로다(workflows):
    body = _body("en", workflows)
    m = BRANCH_RE.search(body)
    assert m and m.group(1) == "20261007_#1_테스트_이슈"          # 구버전 소비자가 브랜치명을 그대로 뽑는다
    assert "Guide by ProjectOps\n---" in body                       # 서명 구조 유지
    assert contracts.LEGACY_COMMENT in body                         # 옛 서명 숨김 주석 유지
    # 계약 문자열과 사용자 데이터(브랜치명, 커밋 메시지)를 빼면 한글이 없어야 한다
    scrubbed = body
    # 긴 것부터 지운다: 옛 서명을 먼저 지우면 그것을 품은 숨김 주석 전체가 매치되지 않는다
    for s in (contracts.LEGACY_COMMENT, *contracts.ALL, "테스트_이슈", "테스트 이슈", "변경 사항"):
        scrubbed = scrubbed.replace(s, "")
    assert not HANGUL.search(scrubbed), HANGUL.search(scrubbed)
    assert "Why use this branch name?" in body


def test_지원하는_모든_언어에서_계약_정규식에_걸린다(workflows, tmp_path, monkeypatch):
    # 아직 없는 언어(ja)가 생겨도 계약이 깨지지 않는지 가짜 카탈로그로 확인한다
    (tmp_path / "en.json").write_text((SCRIPTS / "i18n" / "en.json").read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "ja.json").write_text(json.dumps({"issue_helper.guide.summary": "💡 なぜこのブランチ名?"}), encoding="utf-8")
    monkeypatch.setattr(messages, "CATALOG_DIR", tmp_path)
    messages.load_catalog.cache_clear()
    try:
        for lang in ("en", "ja"):
            assert BRANCH_RE.search(_body(lang, workflows)), lang
    finally:
        messages.load_catalog.cache_clear()


def test_모르는_언어는_영문으로_대체된다(workflows):
    assert _body("xx", workflows) == _body("en", workflows)
