"""커밋 템플릿 계약 테스트 (#606).

**이 템플릿이 틀리면 규칙 위반 커밋이 나가고 릴리스 버전이 잘못 올라간다.**

두 가지를 본다.

1. 이슈 제목의 이모지·태그를 벗기는가 — CLAUDE.md 가 커밋 메시지에 금지한 것들이다
2. 태그에서 커밋 타입을 유도하는가 — `semver_auto` 저장소에서 이 값이 승격 폭을 정한다

그리고 **워크플로 쪽 정본과 매핑이 어긋나지 않는지** 확인한다. 어긋나면 이슈 댓글이
안내한 타입과 스킬이 만든 타입이 달라진다.
"""
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))

from common.gh_branch import (  # noqa: E402
    COMMIT_TYPE_MAP,
    get_commit_template,
    infer_commit_type,
    strip_issue_decorations,
)

URL = "https://github.com/o/r/issues/1"


# ── 이모지·태그를 벗긴다 ─────────────────────────────────────────────

@pytest.mark.parametrize("title,expected", [
    ("⚙️[기능추가][pro-agent-test] 소셜 로그인 절차", "소셜 로그인 절차"),
    ("❗[버그][워크플로] 빌드가 실패함", "빌드가 실패함"),
    ("🚀[기능개선][스킬] 무언가 개선", "무언가 개선"),
    ("🔍 [시험요청][워크플로] 확인 요청", "확인 요청"),   # 이모지와 태그 사이 공백
    ("[문서] 태그만 있는 제목", "태그만 있는 제목"),       # 이모지 없음
    ("장식이 전혀 없는 제목", "장식이 전혀 없는 제목"),
])
def test_decorations_are_stripped(title, expected):
    assert strip_issue_decorations(title) == expected


def test_middle_brackets_survive():
    """제목 **중간**의 대괄호는 내용이다 — 지우면 제목이 깨진다."""
    title = ".env[테스트] 처리가 안 됨"
    assert strip_issue_decorations(title) == title


def test_title_is_never_emptied():
    """다 벗기고 나면 아무것도 안 남는 제목도 있다. 통째로 사라지는 것이 더 나쁘다."""
    assert strip_issue_decorations("⚙️[기능추가]") == "⚙️[기능추가]"


def test_template_has_no_emoji_or_tag():
    """CLAUDE.md: 커밋 메시지 앞에 이모지·태그 절대 포함 금지."""
    out = get_commit_template("⚙️[기능추가][x] 무언가", URL)
    assert "⚙️" not in out
    assert "[기능추가]" not in out
    assert out.startswith("무언가 : ")


# ── 태그가 커밋 타입을 정한다 ────────────────────────────────────────

@pytest.mark.parametrize("title,expected_type", [
    ("❗[버그][워크플로] 빌드가 실패함", "fix"),
    ("⚙️[기능추가][스킬] 새 기능", "feat"),
    ("🚀[기능개선][스킬] 개선", "feat"),
    ("📄[문서] 문서 수정", "docs"),
    ("🔍[시험요청] 확인", "test"),
    ("태그가 없는 제목", "feat"),          # 판단 불가 → 기본값
    ("[알수없는태그] 제목", "feat"),        # 매핑에 없음 → 기본값
])
def test_type_comes_from_the_tag(title, expected_type):
    assert infer_commit_type(title) == expected_type
    assert f" : {expected_type} : " in get_commit_template(title, URL)


def test_bug_issue_does_not_become_a_minor_release():
    """버그 이슈에 feat 를 주면 patch 로 끝날 릴리스가 minor 로 올라간다."""
    out = get_commit_template("❗[버그][CI] 무언가 고장", URL)
    assert " : fix : " in out
    assert " : feat : " not in out


def test_explicit_type_wins():
    """이슈는 기능인데 작업 내용이 버그 수정일 수 있다 — 부르는 쪽이 정할 수 있어야 한다."""
    out = get_commit_template("⚙️[기능추가][x] 무언가", URL, commit_type="fix")
    assert " : fix : " in out


def test_template_keeps_the_issue_url():
    """이슈 링크가 빠지면 커밋에서 맥락을 되찾을 수 없다."""
    assert get_commit_template("[문서] 제목", URL).endswith(URL)


# ── 워크플로 쪽 정본과 어긋나지 않는다 ───────────────────────────────

def test_type_map_matches_the_workflow_source():
    """정본은 .github/scripts/issue_helper.py 다.

    배포 경로가 달라 import 할 수 없어 값을 복제해 두었다. 어긋나면 **이슈 댓글이
    안내한 커밋 타입과 스킬이 만드는 타입이 달라진다** — 사용자는 둘 중 무엇이
    맞는지 알 방법이 없다.
    """
    source = (REPO / ".github/scripts/issue_helper.py").read_text(encoding="utf-8")
    block = re.search(r"DEFAULT_COMMIT_TYPE_MAP\s*=\s*\{(.*?)\}", source, re.S)
    assert block, "정본에서 DEFAULT_COMMIT_TYPE_MAP 을 찾지 못했습니다"
    upstream = dict(re.findall(r'"([^"]+)"\s*:\s*"([^"]+)"', block.group(1)))
    assert upstream == COMMIT_TYPE_MAP
