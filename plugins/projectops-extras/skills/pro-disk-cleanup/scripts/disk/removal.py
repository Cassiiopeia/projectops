"""worktree 제거: 게이트 검사 > 백업 > 참조 보존 > git worktree remove > 확인"""
from __future__ import annotations

import re
from pathlib import Path

from . import backup, shell, sizes, worktrees

DETACHED_REFERENCE_PREFIX = "refs/disk-cleanup/"


def refusal(facts: dict | None, closed_issue: int | None, is_stale_approved: bool) -> tuple[str, str] | None:
    """제거 거절 사유 (code, 설명). 조건 6개: 등록 worktree, 본 레포 아님, 잠금 없음, 사용 중 아님, 최근 활동 없음, 근거 있음"""
    if facts is None:
        return "not_a_worktree", "Path is not a registered git worktree"
    if facts.get("is_main"):
        return "main_worktree", "This is the main checkout of the repository, not a worktree"
    if facts.get("is_locked"):
        return "locked", "The worktree is locked (git worktree lock)"
    if facts.get("is_in_use"):
        return "in_use", f"A process is using it: {facts.get('in_use_by')}"
    if facts.get("is_recently_active"):
        return "recently_active", "Touched within the idle window; another session may be working here"
    if facts.get("status_error"):
        return "status_error", "git status failed; changes could not be checked"
    if closed_issue is None and not is_stale_approved:
        return "no_reason", "Pass --closed-issue N (confirmed closed on GitHub) or --approved-stale (the user named it)"
    if closed_issue is not None and facts.get("issue_number") not in (None, closed_issue):
        return "issue_mismatch", f"Branch points to issue #{facts.get('issue_number')}, not #{closed_issue}"
    return None


def _keep_detached_head(facts: dict) -> str | None:
    # 브랜치 없는 HEAD 는 지우면 커밋을 잃으므로 참조를 남김
    name = DETACHED_REFERENCE_PREFIX + re.sub(r"[^\w.-]+", "_", Path(facts["path"]).name)
    if not facts.get("head"):
        return None
    code, _ = shell.git(facts["main_repository"], "update-ref", name, facts["head"])
    return name if code == 0 else None


def remove(path: str, closed_issue: int | None, is_stale_approved: bool, idle_hours: float,
           backup_base: Path, is_confirmed: bool, should_skip_large_untracked: bool) -> dict:
    facts = worktrees.find_one(Path(path).expanduser(), idle_hours)
    rejected = refusal(facts, closed_issue, is_stale_approved)
    if rejected:
        return {"ok": False, "code": rejected[0], "summary": rejected[1], "worktree": facts}
    has_changes = facts["real_change_count"] > 0 or facts["generated_change_count"] > 0
    # 백업은 항상 (변경이 없어도 무시된 .env·키 파일이 있을 수 있음)
    plan = {"worktree": facts["path"], "branch_kept": facts.get("branch"), "will_back_up": True,
            "will_force": has_changes, "unpushed_commit_count": facts.get("unpushed_commit_count"),
            "real_change_count": facts["real_change_count"]}
    if not is_confirmed:
        return {"ok": True, "code": "dry_run", "plan": plan, "worktree": facts,
                "summary": "Nothing removed. Re-run with --yes to back up and remove",
                "next": f"remove-worktree {facts['path']} ... --yes"}
    backup_result = backup.backup_worktree(facts, backup_base)
    if not backup_result["ok"]:
        return {"ok": False, "code": "backup_failed", "backup": backup_result,
                "summary": "Backup could not be verified; nothing removed"}
    if backup_result["untracked_skipped_large"] and not should_skip_large_untracked:
        return {"ok": False, "code": "large_untracked_files", "backup": backup_result,
                "summary": "Large untracked files were not backed up; nothing removed",
                "next": "check the files, then re-run with --skip-large-untracked if they can go"}
    kept_reference = _keep_detached_head(facts) if facts.get("is_detached") else None
    free_before = sizes.free_bytes()
    arguments = ["worktree", "remove", *(["--force"] if has_changes else []), facts["path"]]
    code, out = shell.git(facts["main_repository"], *arguments, timeout_seconds=600)
    is_removed = not Path(facts["path"]).exists()
    return {"ok": code == 0 and is_removed, "code": "removed" if is_removed else "remove_failed",
            "worktree": facts["path"], "branch_kept": facts.get("branch"), "detached_reference": kept_reference,
            "backup": backup_result, "git_output": out[-400:],
            "freed_gb": sizes.to_gigabytes(max(sizes.free_bytes() - free_before, 0)),
            "summary": "Removed; branch and commits kept" if is_removed else "git worktree remove failed"}
