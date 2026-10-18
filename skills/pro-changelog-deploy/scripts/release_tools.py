"""릴리스 보조: 릴리스 노트 포장, 브랜치 쌍 점검, base 동기화 (#945).

에이전트가 매 배포마다 손으로 치던 것(CodeRabbit 표식 블록, base 병합, 브랜치 쌍이 맞는지 확인)을
한 곳으로 모은다.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from common.emit import emit

NOTES_MARKER = "Summary by CodeRabbit"
_NOTES_OPEN = "<!-- This is an auto-generated comment: release notes by coderabbit.ai -->"
_NOTES_CLOSE = "<!-- end of auto-generated comment: release notes by coderabbit.ai -->"


def wrap_release_notes(body: str) -> tuple[str, bool]:
    """(본문, 포장했는지). 본문이 비었거나 이미 표식이 있으면 그대로 둔다.

    워크플로우는 표식 블록 구조에 의존한다. 사람이 손으로 쓰다 틀리면 본문이 지워지거나
    missing_coderabbit_summary 가 나므로 도구가 대신 씌운다.
    """
    if not body.strip() or NOTES_MARKER in body:
        return body, False
    inner = body.strip()
    if not inner.startswith("##"):
        inner = "## 릴리스 노트\n\n" + inner
    return f"{_NOTES_OPEN}\n\n## {NOTES_MARKER}\n\n{inner}\n\n{_NOTES_CLOSE}\n", True


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=120)


def _ref_exists(root: Path, ref: str) -> bool:
    return _git(root, "rev-parse", "--verify", "--quiet", ref).returncode == 0


def _commit_count(root: Path, exclude: str, include: str) -> int | None:
    done = _git(root, "rev-list", "--count", f"{exclude}..{include}")
    return int(done.stdout.strip()) if done.returncode == 0 and done.stdout.strip().isdigit() else None


def branches_check(project_root: Path, head: str, base: str) -> dict:
    """설정된 head/base 쌍이 실제로 릴리스할 차이를 갖는지. 로컬 origin/* 추적 ref 기준(fetch 는 하지 않는다)"""
    head_ref, base_ref = f"origin/{head}", f"origin/{base}"
    out = {"head_exists": _ref_exists(project_root, head_ref), "base_exists": _ref_exists(project_root, base_ref),
           "ahead_count": None, "behind_count": None, "warning": None}
    if not (out["head_exists"] and out["base_exists"]):
        missing = [r for r, ok in ((head_ref, out["head_exists"]), (base_ref, out["base_exists"])) if not ok]
        out["warning"] = f"{', '.join(missing)} 가 없다. version.yml 의 development/default 브랜치를 확인하거나 git fetch 후 다시"
        return out
    out["ahead_count"] = _commit_count(project_root, base_ref, head_ref)
    out["behind_count"] = _commit_count(project_root, head_ref, base_ref)
    if out["ahead_count"] == 0:
        out["warning"] = (f"{head_ref} 가 {base_ref} 보다 앞선 커밋이 없다 — 릴리스할 것이 없거나 "
                          "브랜치 쌍이 틀렸을 수 있다 (이 레포의 실제 릴리스 흐름을 사용자에게 확인)")
    return out


def cmd_sync_base(args) -> int:
    """배포 전 base > head 역방향 병합: fetch > 차이 확인 > merge. 충돌은 되돌리지 않고 멈춘다."""
    root = Path(args.project_root).resolve() if args.project_root else Path.cwd()
    current = _git(root, "branch", "--show-current").stdout.strip()
    if current != args.head:
        return emit({"ok": False, "code": "wrong_branch", "current": current, "expected": args.head,
                     "error": "현재 브랜치가 릴리스 head 가 아니다 (다른 세션이 옮겼을 수 있다)",
                     "next": "브랜치를 임의로 바꾸지 말고 사용자에게 알린다"})
    fetched = _git(root, "fetch", "origin")
    if fetched.returncode != 0:
        return emit({"ok": False, "code": "fetch_failed", "error": fetched.stderr.strip()[:300], "next": None})
    behind = _git(root, "log", "--oneline", f"origin/{args.head}..origin/{args.base}").stdout.strip().splitlines()
    if not behind:
        return emit({"ok": True, "code": "in_sync", "behind": [], "summary": f"origin/{args.base} 가 이미 포함돼 있다",
                     "next": "deploy 절차 계속"})
    merged = _git(root, "merge", "--no-edit", f"origin/{args.base}")
    if merged.returncode == 0:
        return emit({"ok": True, "code": "merged", "behind": behind[:20],
                     "summary": f"origin/{args.base} 커밋 {len(behind)}개를 병합했다", "next": "push 후 deploy 절차 계속"})
    conflicted = _git(root, "diff", "--name-only", "--diff-filter=U").stdout.split()
    return emit({"ok": False, "code": "merge_conflict", "conflicted_files": conflicted[:30], "behind": behind[:20],
                 "error": "병합 충돌", "next": "충돌을 양쪽 의도를 살려 해소하거나 사용자와 정한다 (merge --abort·reset 을 임의로 하지 않는다)"})
