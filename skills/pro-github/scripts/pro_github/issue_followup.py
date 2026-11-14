"""Follow-up right after issue creation: align the local issue doc number, branch name and commit template (#969 A14)."""
from __future__ import annotations

import re
from pathlib import Path

# Name get-output-path gives before registration: YYYYMMDD_3-digit serial_title
_DRAFT_BODY_FILE_NAME = re.compile(r"^(\d{8})_\d{3}_(.+)$")


def rename_body_file_to_issue_number(body_path: Path, issue_number: int) -> tuple:
    """20261021_001_title.md > 20261021_{number}_title.md (same folder) > (new path | None, warning | None)

    If the name format differs or a file with the same name already exists, nothing is renamed and only a warning is returned.
    """
    matched = _DRAFT_BODY_FILE_NAME.match(body_path.name)
    if not matched:
        return None, f"not renamed: the body file name is not in YYYYMMDD_NNN_ form: {body_path.name}"
    target = body_path.with_name(f"{matched.group(1)}_{issue_number}_{matched.group(2)}")
    if target.exists():
        return None, f"not renamed: a file with that name already exists: {target}"
    body_path.rename(target)
    return target, None


def build_work_start_hints(issue_title: str, issue_number: int, issue_url: str) -> dict:
    """{branch, commit_template} via the same resolution path as create-branch-name · get-commit-template"""
    from common.commit_style import render_for_issue, resolve_for_repo
    from common.gh_branch import create_branch_name
    _, style = resolve_for_repo(None)
    return {
        "branch": create_branch_name(issue_title, issue_number),
        "commit_template": render_for_issue(style, issue_title=issue_title, issue_url=issue_url),
    }
