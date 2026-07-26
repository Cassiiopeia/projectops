"""산출물 md 파일 경로를 계산한다."""

import os
from pathlib import Path
from typing import Optional, Union


def get_next_seq(skill_dir: Path, today: str, strict: bool = False) -> str:
    """
    skill_dir 내에서 오늘 날짜(today)로 시작하는 파일 개수 + 1을 3자리로 반환한다.

    strict=True이면 skill_dir이 존재하지 않을 때 FileNotFoundError를 던진다.
    CLI 레이어가 잘못된 skill_id를 명시적으로 거부할 때 사용한다.
    """
    if not skill_dir.exists():
        if strict:
            raise FileNotFoundError(f"skill_dir does not exist: {skill_dir}")
        return "001"
    count = sum(1 for f in skill_dir.iterdir() if f.name.startswith(today))
    return f"{count + 1:03d}"


def build_output_path(
    base_dir: Union[str, Path],
    skill_id: str,
    today: str,
    number: str,
    title: str,
) -> Path:
    """최종 산출물 경로를 반환한다."""
    return Path(base_dir) / skill_id / f"{today}_{number}_{title}.md"


# ===================================================================
# 산출물 경로 해석 (#525) — Layer 1 단일 구현
# ===================================================================
# 과거에는 report/review/troubleshoot 세 CLI가 같은 로직을 각자 복사해 갖고
# 있었고, 나머지 5개 산출물 스킬(analyze/plan/design-analyze/refactor-analyze/
# ppt)은 계산 수단조차 없어 "agent가 직접 계산"하는 상태였다. 규칙이 코드로
# 강제되지 않으니 스킬마다 파일명이 갈라져도 알아챌 방법이 없었다.
# 이 함수가 유일한 구현이며, 모든 스킬 CLI는 이것을 호출한다.

DEFAULT_OUTPUT_ROOT = "docs/projectops"


def resolve_output_root(project_root: Union[str, Path]) -> Path:
    """산출물 루트를 결정한다. 설정이 없으면 기존 위치를 그대로 쓴다.

    설정(config.json)의 `output.root` 로 팀마다 다른 위치를 쓸 수 있다.
    - 상대경로면 저장소 루트 기준 (예: "docs/dev" → <repo>/docs/dev)
    - 절대경로면 그대로 (저장소 밖에 모으고 싶을 때)
    - 미설정이면 docs/projectops — 즉 설정을 건드리지 않으면 동작이 바뀌지 않는다
    """
    root = Path(project_root)
    try:
        from common.config import load
        cfg = load() or {}
        configured = ((cfg.get("output") or {}).get("root") or "").strip()
    except Exception:
        configured = ""

    if not configured:
        return root / DEFAULT_OUTPUT_ROOT
    p = Path(configured).expanduser()
    return p if p.is_absolute() else root / p


def resolve_output_path(skill_id: str, forced_title: Optional[str] = None) -> dict:
    """산출물 md 경로를 계산해 dict로 반환한다 (CLI가 그대로 emit한다).

    이슈 번호는 worktree 경로 → 브랜치명 순으로 찾고, 둘 다 없으면
    그날의 일련번호를 붙인다. 제목은 인자 우선, 없으면 경로에서 추출한다.
    """
    import subprocess
    from datetime import date

    from common.issue_number import (
        extract_from_path as in_extract_from_path,
        extract_from_branch, get_current_branch, resolve,
    )
    from common.title import normalize, extract_from_path as title_extract_from_path

    cwd = os.getcwd()
    today = date.today().strftime("%Y%m%d")

    wt_number = in_extract_from_path(cwd)
    branch = get_current_branch()
    br_number = extract_from_branch(branch) if branch else None
    issue_num, mismatch = resolve(wt_number, br_number)

    try:
        root_str = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return {"ok": False, "code": "git_not_found", "error": "git 저장소가 아닙니다"}

    output_base = resolve_output_root(root_str)
    skill_dir = output_base / skill_id
    number = issue_num if issue_num else get_next_seq(skill_dir, today)

    if forced_title:
        final_title = normalize(forced_title)
    else:
        raw = title_extract_from_path(cwd)
        final_title = normalize(raw) if raw else "untitled"

    path = build_output_path(output_base, skill_id, today, number, final_title)
    return {
        "path": str(path),
        "summary": str(path),
        "mismatch": mismatch,
        "output_root": str(output_base),
    }
