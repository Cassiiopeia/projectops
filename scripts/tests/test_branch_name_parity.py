"""브랜치명 정규화 교차 테스트 (#717).

이슈 댓글(.github/scripts/issue_helper.py)이 안내하는 브랜치명과
스킬 CLI(scripts/common/gh_branch.py)가 만드는 브랜치명이 같은 제목에서 같아야 한다.
두 구현은 배포 경로가 달라 import 공유가 불가능해 복제돼 있으므로 이 테스트가 동기화를 강제한다.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
# issue_helper.py 는 자기 폴더의 i18n 패키지를 import 한다. 스크립트로 실행할 때는 그 폴더가
# 자동으로 경로에 들어가지만, 파일 경로로 로드하면 들어가지 않는다. 다른 테스트 폴더와 함께
# 돌릴 때만 우연히 통과하고 CI 의 단독 실행(scripts/tests/)에서 깨졌다.
sys.path.insert(0, str(ROOT / ".github" / "scripts"))

from common import gh_branch  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "issue_helper_ref", ROOT / ".github" / "scripts" / "issue_helper.py")
issue_helper = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(issue_helper)

TITLES = [
    "로그인 버그 수정",
    "FCM 푸시: 라우팅용 데이터!",
    "!한글 제목!",
    "a - - b",
    "日本語のタイトル",
    "Ünïcödé café",
    "🚀",
    "!!!",
    "",
    "가" * 200,
    "a" * 87 + " bbb",
    "a" * 80 + " " + "b" * 30,
]


@pytest.mark.parametrize("title", TITLES)
@pytest.mark.parametrize("number", [7, 12345])
def test_same_title_same_branch(title, number):
    expected = issue_helper.create_branch_name(title, number, "20261001")
    assert gh_branch.create_branch_name(title, number, "20261001") == expected


@pytest.mark.parametrize("title", TITLES)
def test_normalize_parity(title):
    assert gh_branch.normalize_title(title) == issue_helper.normalize_title(title)


def test_known_values_unchanged():
    # 기존 한글·영문 결과는 바뀌지 않는다
    assert gh_branch.create_branch_name("로그인 버그 수정", 123, "20260712") == "20260712_#123_로그인_버그_수정"
    assert gh_branch.create_branch_name("x", 664, "20261001") == "20261001_#664_x"


def test_japanese_and_empty_fallback():
    assert gh_branch.create_branch_name("日本語のタイトル", 7, "20261001") == "20261001_#7_日本語のタイトル"
    assert gh_branch.create_branch_name("🚀", 7, "20261001") == "20261001_#7_issue-7"
