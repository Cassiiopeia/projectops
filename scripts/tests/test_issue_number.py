# scripts/tests/test_issue_number.py
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import pytest  # noqa: E402
from common.issue_number import (  # noqa: E402
    extract_from_branch, extract_from_path, resolve,
)


# 브랜치 규칙은 `YYYYMMDD_#번호_제목` 이다. 맨 앞 8자리는 날짜지 이슈 번호가 아니다.
# 이것을 떼지 않아 산출물이 `20260918_20260918_…` 이 되고, /pro-commit 이 커밋
# 메시지에 존재하지 않는 이슈 #20260918 을 박았다 (#613).
#
# 워크트리로 작업하면 워크트리 번호가 이겨서 드러나지 않았다 — 워크트리 없이
# 브랜치만 체크아웃하는 경우(이 레포의 develop 직행 포함)에만 터졌다.

@pytest.mark.parametrize("branch,expected", [
    # 프로젝트 표준 규칙 — 날짜를 건너뛰고 그 뒤 번호를 잡는다
    ("20260918_#77_로그인_화면_검증", "77"),
    ("20260115_427_드롭다운_디자인_변경", "427"),      # `#` 없는 형태도 받는다
    ("20260918_#1_한_자리", "1"),
    # 날짜 접두사가 없는 브랜치 — 기존 동작을 깨지 않는다
    ("feature/#77-x", "77"),
    ("fix/123", "123"),
    ("123-hotfix", "123"),
    # 번호가 없으면 없다고 한다 — 아무 숫자나 집어오지 않는다
    ("develop", None),
    ("main", None),
    ("20260918_제목만_있음", None),
])
def test_branch_number_skips_the_date_prefix(branch, expected):
    assert extract_from_branch(branch) == expected, (
        f"{branch!r} 에서 이슈 번호를 잘못 뽑았다")


def test_worktree_and_branch_agree_on_the_same_convention():
    """같은 규칙을 쓰는 두 경로가 다른 답을 내면 mismatch 경고가 헛돈다."""
    name = "20260918_#77_로그인_화면_검증"
    assert extract_from_branch(name) == "77"
    # 워크트리 폴더명은 `#` 없이 만들어진다
    assert extract_from_path(f"/tmp/wt/20260918_77_로그인_화면_검증") == "77"


def test_resolve_warns_only_on_real_disagreement():
    assert resolve("77", "77") == ("77", False)
    assert resolve("77", "88") == ("77", True)     # 워크트리가 이기되 경고한다
    assert resolve(None, "77") == ("77", False)
    assert resolve(None, None) == (None, False)
