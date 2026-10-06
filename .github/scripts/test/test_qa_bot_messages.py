"""QA 봇이 게시하는 문구(#787): 한국어는 이관 전 JS 가 만들던 문자열과 바이트 동일, 영문에는 한글이 없다."""
import json
import re
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import qa_bot_messages as qb  # noqa: E402

GOLD = json.loads((Path(__file__).resolve().parent / "golden" / "qa_bot_ko.json").read_text(encoding="utf-8"))
HANGUL = re.compile(r"[가-힣]")
TITLE, ORIG, PR, QA, USER = "로그인 실패", 12, 34, 56, "octo"


def _issue(lang, is_pr):
    return qb.build_issue(lang, TITLE, ORIG, PR if is_pr else None, USER)


def _comment(lang, is_pr):
    return qb.build_comment(lang, QA, ORIG if is_pr else None)


def test_한국어_이슈_제목과_본문은_이관_전_JS_출력과_바이트_동일하다():
    for key, is_pr in (("pr", True), ("issue", False)):
        got = _issue("ko", is_pr)
        assert got["title"] == GOLD[key]["qaTitle"], key
        assert got["body"] == GOLD[key]["qaBody"], key


def test_한국어_원본_댓글과_오류_문구는_바이트_동일하다():
    for key, is_pr in (("pr", True), ("issue", False)):
        assert _comment("ko", is_pr) == GOLD[key]["commentBody"], key
    assert qb.build_error("ko", "boom") == GOLD["issue"]["errBody"]


def test_영문_출력에는_사용자_데이터를_뺀_한글이_없다():
    for is_pr in (True, False):
        issue = _issue("en", is_pr)
        text = "\n".join([issue["title"], issue["body"], _comment("en", is_pr), qb.build_error("en", "boom")])
        assert not HANGUL.search(text.replace(TITLE, "")), HANGUL.search(text.replace(TITLE, ""))


def test_영문_제목은_영문_표준_태그를_쓴다():
    # 이슈 헬퍼가 [QA] 를 test 타입으로 매핑한다(1단계) — 태그가 어긋나면 커밋 타입이 틀어진다
    assert _issue("en", False)["title"] == "🔍 [QA]로그인 실패"


def test_모르는_언어는_영문으로_대체된다():
    assert _issue("xx", True) == _issue("en", True)


def test_PR이면_PR_정보를_넣고_이슈면_자리를_비워_둔다():
    assert "- PR: #34" in _issue("en", True)["body"]
    assert "- PR: #34" not in _issue("en", False)["body"]


def test_CLI는_JSON_한_줄을_출력한다():
    r = subprocess.run([sys.executable, str(SCRIPTS / "qa_bot_messages.py"), "issue", "--lang", "ko", "--title", TITLE,
                        "--original", str(ORIG), "--requester", USER], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["title"] == GOLD["issue"]["qaTitle"]
