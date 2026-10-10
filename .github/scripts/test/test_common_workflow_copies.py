# .github/scripts/test/test_common_workflow_copies.py
"""루트 공통 워크플로우와 project-types/common 원본이 같은지 검증 (#751).

CLAUDE.md 규칙: 공통 워크플로우는 `project-types/common/`(원본)과 `.github/workflows/`(루트 사본)
두 곳을 동일하게 유지한다. 원본이 사용자 프로젝트로 복사되는 쪽이라 어긋나면 이 레포가 쓰는
버전과 사용자에게 나가는 버전이 달라진다. Dependabot 이 루트 사본만 바꾸는 경우를 막는다.
"""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
WORKFLOWS = ROOT / ".github" / "workflows"
COMMON = WORKFLOWS / "project-types" / "common"


def _pairs():
    out = []
    for src in sorted(COMMON.glob("PROJECT-COMMON-*.y*ml")):
        root_copy = WORKFLOWS / src.name
        if root_copy.exists():
            out.append((src, root_copy))
    return out


def test_there_are_pairs_to_compare():
    assert _pairs(), "비교할 공통 워크플로우 쌍을 하나도 찾지 못했다 (경로가 바뀌었나?)"


@pytest.mark.parametrize("src,root_copy", _pairs(), ids=lambda p: p.name if hasattr(p, "name") else str(p))
def test_root_copy_matches_common_original(src, root_copy):
    assert root_copy.read_text(encoding="utf-8") == src.read_text(encoding="utf-8"), (
        f"{src.name}: 루트 사본과 project-types/common 원본이 다르다. 두 곳을 같이 고쳐야 한다."
    )


# ── 하위 폴더 사본까지 (#832) ─────────────────────────────────────────────────
# 위 검사는 common/ 최상위만 본다. pr-summary/ · projects-sync/ 는 루트에도 복사되는 짝인데 비교되지 않아,
# 한쪽만 고쳐도 아무도 몰랐다 (지금은 우연히 같다). 루트에 사본이 있는 하위 폴더 파일은 모두 같아야 한다.
def _nested_pairs():
    out = []
    for src in sorted(COMMON.glob("*/PROJECT-COMMON-*.y*ml")) + sorted(COMMON.glob("*/*/PROJECT-COMMON-*.y*ml")):
        root_copy = WORKFLOWS / src.name
        if root_copy.exists():
            out.append((src, root_copy))
    return out


def test_nested_pairs_are_found():
    assert len(_nested_pairs()) >= 2, "pr-summary/ · projects-sync/ 사본 쌍을 찾지 못했다"


@pytest.mark.parametrize("src,root_copy", _nested_pairs(), ids=lambda p: p.name if hasattr(p, "name") else str(p))
def test_nested_root_copy_matches_original(src, root_copy):
    assert root_copy.read_text(encoding="utf-8") == src.read_text(encoding="utf-8"), (
        f"{src.relative_to(COMMON)}: 루트 사본과 원본이 다르다. 두 곳을 같이 고쳐야 한다."
    )
