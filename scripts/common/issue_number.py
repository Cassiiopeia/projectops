"""worktree 폴더명 또는 git 브랜치명에서 이슈 번호를 추출한다."""

import re
import subprocess
from pathlib import Path
from typing import Optional, Tuple


_WORKTREE_PATTERN = re.compile(r"\d{8}_(\d+)_")

# 브랜치 규칙이 `YYYYMMDD_#번호_제목` 이라 맨 앞 8자리는 **날짜**다. 떼고 나서
# 번호를 찾지 않으면 날짜가 이슈 번호로 잡힌다 (#613). 위 워크트리 패턴은 처음부터
# 날짜를 건너뛰게 짜여 있어서, 워크트리로 작업하면 이 버그가 드러나지 않았다.
_DATE_PREFIX = re.compile(r"^\d{8}(?=[_/-])")

# `#` 도 구분자로 받는다 — 규칙이 번호 앞에 `#` 을 붙이고, 붙지 않은 브랜치도 있다.
_BRANCH_PATTERN = re.compile(r"(?:^|[/_#-])(\d+)(?:[/_-]|$)")


def extract_from_path(cwd: str) -> Optional[str]:
    """경로 문자열에서 worktree 패턴(YYYYMMDD_숫자_제목)의 숫자를 추출한다."""
    for part in Path(cwd).parts:
        m = _WORKTREE_PATTERN.search(part)
        if m:
            return m.group(1)
    return None


def extract_from_branch(branch: str) -> Optional[str]:
    """git 브랜치명에서 이슈 번호로 보이는 숫자를 추출한다.

    날짜 접두사를 먼저 떼는 것이 요점이다. 이것이 없어서 `20260918_#77_제목` 에서
    77 이 아니라 20260918 이 나왔고, 산출물 이름이 `20260918_20260918_…` 이 되고
    커밋 메시지에도 없는 이슈 번호가 박혔다 (#613).
    """
    m = _BRANCH_PATTERN.search(_DATE_PREFIX.sub("", branch))
    return m.group(1) if m else None


def get_current_branch() -> Optional[str]:
    """현재 git 브랜치명을 반환한다. git 저장소가 아니면 None."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            errors='replace',
            check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def resolve(
    worktree_number: Optional[str],
    branch_number: Optional[str],
) -> Tuple[Optional[str], bool]:
    """
    worktree 번호와 브랜치 번호를 받아 최종 이슈 번호와 경고 여부를 반환한다.

    Returns:
        (issue_number, mismatch_warn)
    """
    if worktree_number and branch_number:
        warn = worktree_number != branch_number
        return worktree_number, warn
    if worktree_number:
        return worktree_number, False
    if branch_number:
        return branch_number, False
    return None, False
