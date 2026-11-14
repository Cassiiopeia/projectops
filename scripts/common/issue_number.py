"""Extract the issue number from a worktree folder name or git branch name."""

import re
import subprocess
from pathlib import Path
from typing import Optional, Tuple


_WORKTREE_PATTERN = re.compile(r"\d{8}_(\d+)_")

# The branch rule is `YYYYMMDD_#number_title`, so the first 8 digits are a **date**. Searching for
# the number without stripping it catches the date as the issue number (#613). The worktree pattern above
# skips the date by design, so working in a worktree hid this bug.
# With a prefix like `feature/` the date is no longer first, so strip the date after `/` too (#697).
_DATE_PREFIX = re.compile(r"(^|/)\d{8}(?=[_/-])")

# `#` is accepted as a separator too — the rule puts `#` before the number, but some branches lack it.
_BRANCH_PATTERN = re.compile(r"(?:^|[/_#-])(\d+)(?:[/_-]|$)")


def extract_from_path(cwd: str) -> Optional[str]:
    """Extract the number from a worktree pattern (YYYYMMDD_number_title) in a path string."""
    for part in Path(cwd).parts:
        m = _WORKTREE_PATTERN.search(part)
        if m:
            return m.group(1)
    return None


def extract_from_branch(branch: str) -> Optional[str]:
    """Extract a number that looks like an issue number from a git branch name.

    The point is stripping the date prefix first. Without it, `20260918_#77_title` gave
    20260918 instead of 77, outputs were named `20260918_20260918_…`, and
    commit messages got a nonexistent issue number (#613).
    """
    m = _BRANCH_PATTERN.search(_DATE_PREFIX.sub(r"\1", branch))
    return m.group(1) if m else None


def get_current_branch(cwd: Optional[str] = None) -> Optional[str]:
    """Return the current git branch name. None outside a git repo, "HEAD" when detached.

    rev-parse's short output cuts non-ASCII branch names mid-character (Apple Git 2.39), so use --show-current (#938).
    """
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=cwd,
            capture_output=True,
            text=True, encoding="utf-8",
            errors='replace',
            check=True,
        )
        return result.stdout.strip() or "HEAD"
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def resolve(
    worktree_number: Optional[str],
    branch_number: Optional[str],
) -> Tuple[Optional[str], bool]:
    """
    Take the worktree number and branch number and return the final issue number and whether to warn.

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
