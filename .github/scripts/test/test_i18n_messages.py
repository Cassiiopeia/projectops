"""메시지 카탈로그(#787): 키 정합성, 계약 격리, 대체 동작, 언어 결정."""
import json
import re
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
from i18n import contracts, messages  # noqa: E402

HANGUL = re.compile(r"[가-힣]")
PLACEHOLDER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
CATALOGS = sorted((SCRIPTS / "i18n").glob("*.json"))


def _load(p):
    return json.loads(p.read_text(encoding="utf-8"))


EN = _load(SCRIPTS / "i18n" / "en.json")


def test_영문_정본이_있고_모든_언어는_영문의_부분집합이다():
    for p in CATALOGS:
        extra = set(_load(p)) - set(EN)
        assert not extra, f"{p.name} 에만 있는 키(영문 정본에 없다): {sorted(extra)}"


@pytest.mark.parametrize("path", CATALOGS, ids=lambda p: p.name)
def test_자리표시자_집합이_영문과_같다(path):
    for key, value in _load(path).items():
        assert set(PLACEHOLDER.findall(value)) == set(PLACEHOLDER.findall(EN[key])), f"{path.name}:{key}"


def test_영문_카탈로그에는_한글이_없다():
    bad = [k for k, v in EN.items() if HANGUL.search(v)]
    assert not bad, bad


def test_계약_문자열은_어떤_카탈로그_값에도_들어_있지_않다():
    # 구버전 소비자가 정규식으로 읽는 문자열은 번역 대상이 아니다 — 코드가 contracts 에서 붙인다
    for p in CATALOGS:
        for key, value in _load(p).items():
            for c in contracts.ALL:
                assert c not in value, f"{p.name}:{key} 에 계약 문자열 {c!r} 이 있다"


def test_코드가_쓰는_키는_모두_영문_카탈로그에_있다():
    used = set()
    pat = re.compile(r"""\bt\(\s*["']([a-z0-9_.]+)["']""")
    for f in list(SCRIPTS.glob("*.py")) + list((SCRIPTS.parent / "workflows").glob("PROJECT-COMMON-*.y*ml")):
        used |= set(pat.findall(f.read_text(encoding="utf-8")))
    missing = sorted(k for k in used if k not in EN)
    assert not missing, f"영문 카탈로그에 없는 키: {missing}"


@pytest.fixture
def partial(tmp_path, monkeypatch):
    (tmp_path / "en.json").write_text(json.dumps({"a.one": "One {n}", "a.two": "Two"}), encoding="utf-8")
    (tmp_path / "ja.json").write_text(json.dumps({"a.one": "ひとつ {n}"}), encoding="utf-8")
    monkeypatch.setattr(messages, "CATALOG_DIR", tmp_path)
    messages.load_catalog.cache_clear()
    yield tmp_path
    messages.load_catalog.cache_clear()


def test_번역이_없는_키는_영문으로_대체한다(partial):
    assert messages.t("a.one", "ja", n=3) == "ひとつ 3"
    assert messages.t("a.two", "ja") == "Two"        # ja 에 없다 → 영문
    assert messages.t("a.none", "ja") == "a.none"   # 어디에도 없다 → 키 (죽지 않는다)


def test_지원하지_않는_언어는_영문으로_대체한다(partial):
    assert messages.t("a.two", "xx") == "Two"


def test_치환할_값이_없으면_자리표시자를_그대로_둔다(partial):
    assert messages.t("a.one", "en") == "One {n}"
    assert messages.t("a.one", "en", n=1, extra=2) == "One 1"


def test_중괄호가_들어간_문구도_안전하다(partial):
    (partial / "en.json").write_text(json.dumps({"j": 'json: {"a": 1} {n}'}), encoding="utf-8")
    messages.load_catalog.cache_clear()
    assert messages.t("j", "en", n=2) == 'json: {"a": 1} 2'


def test_언어_코드는_정규화해_받는다(partial):
    assert messages.normalize("ko-KR") == "ko" or messages.normalize("ko-KR") == "en"  # ko 카탈로그가 없으면 en
    assert messages.normalize("JA") == "ja"
    assert messages.normalize("ja_JP.UTF-8") == "ja"
    assert messages.normalize("") == "en"
    assert messages.normalize(None) == "en"


def test_언어_결정_순서(tmp_path, monkeypatch):
    monkeypatch.setattr(messages, "CATALOG_DIR", SCRIPTS / "i18n")
    messages.load_catalog.cache_clear()
    vy = tmp_path / "version.yml"
    # version.yml 이 없으면 신규로 본다 → en
    assert messages.resolve_language(tmp_path / "none.yml", env={}) == "en"
    # version.yml 은 있는데 language 키가 없으면 기존 레포 → ko (문구가 바뀌면 안 된다)
    vy.write_text("metadata:\n  template:\n    options:\n      deploy: none\n", encoding="utf-8")
    assert messages.resolve_language(vy, env={}) == "ko"
    # 키가 있으면 그 값
    vy.write_text("metadata:\n  template:\n    options:\n      language: en\n", encoding="utf-8")
    assert messages.resolve_language(vy, env={}) == "en"
    # 환경변수가 이긴다
    assert messages.resolve_language(vy, env={"REPO_LANG": "ko"}) == "ko"


def test_번들은_접두사로_모은_키를_돌려준다(partial):
    assert messages.bundle("a.", "en") == {"a.one": "One {n}", "a.two": "Two"}
