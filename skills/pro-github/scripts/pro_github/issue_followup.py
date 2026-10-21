"""이슈 생성 직후 이어지는 일: 로컬 이슈 문서 번호 맞추기, 브랜치명·커밋 틀 (#969 A14)."""
from __future__ import annotations

import re
from pathlib import Path

# get-output-path 가 등록 전에 붙이는 이름: YYYYMMDD_일련번호3자리_제목
_DRAFT_BODY_FILE_NAME = re.compile(r"^(\d{8})_\d{3}_(.+)$")


def rename_body_file_to_issue_number(body_path: Path, issue_number: int) -> tuple:
    """20261021_001_제목.md > 20261021_{번호}_제목.md (같은 폴더) > (새 경로 | None, 경고 | None)

    이름 형식이 다르거나 같은 이름 파일이 이미 있으면 바꾸지 않고 경고만 돌려준다.
    """
    matched = _DRAFT_BODY_FILE_NAME.match(body_path.name)
    if not matched:
        return None, f"본문 파일 이름이 YYYYMMDD_NNN_ 형식이 아니라 바꾸지 않았다: {body_path.name}"
    target = body_path.with_name(f"{matched.group(1)}_{issue_number}_{matched.group(2)}")
    if target.exists():
        return None, f"같은 이름 파일이 이미 있어 바꾸지 않았다: {target}"
    body_path.rename(target)
    return target, None


def build_work_start_hints(issue_title: str, issue_number: int, issue_url: str) -> dict:
    """create-branch-name · get-commit-template 와 같은 해석 경로로 {branch, commit_template}"""
    from common.commit_style import render_for_issue, resolve_for_repo
    from common.gh_branch import create_branch_name
    _, style = resolve_for_repo(None)
    return {
        "branch": create_branch_name(issue_title, issue_number),
        "commit_template": render_for_issue(style, issue_title=issue_title, issue_url=issue_url),
    }
