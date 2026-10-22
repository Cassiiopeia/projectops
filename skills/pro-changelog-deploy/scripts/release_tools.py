"""릴리스 보조: 릴리스 노트 포장, 브랜치 쌍 점검, base 동기화 (#945).

에이전트가 매 배포마다 손으로 치던 것(CodeRabbit 표식 블록, base 병합, 브랜치 쌍이 맞는지 확인)을
한 곳으로 모은다.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from common.emit import emit
from release_language import BUILT_IN_HEADINGS, load_headings, resolve_notes_language

NOTES_MARKER = "Summary by CodeRabbit"
_NOTES_OPEN = "<!-- This is an auto-generated comment: release notes by coderabbit.ai -->"
_NOTES_CLOSE = "<!-- end of auto-generated comment: release notes by coderabbit.ai -->"


def read_repo_language(project_root: Path) -> str:
    """version.yml options.language > 노트 언어 (정본: release_language — 워크플로우 i18n 과 같은 규칙, #977)"""
    return resolve_notes_language(project_root, load_headings(project_root))[0]


def wrap_release_notes(body: str, language: str = "ko") -> tuple[str, bool]:
    """(본문, 포장했는지). 본문이 비었거나 이미 표식이 있으면 그대로 둔다.

    워크플로우는 표식 블록 구조에 의존한다. 사람이 손으로 쓰다 틀리면 본문이 지워지거나
    missing_coderabbit_summary 가 나므로 도구가 대신 씌운다.
    """
    if not body.strip() or NOTES_MARKER in body:
        return body, False
    inner = body.strip()
    if not inner.startswith("##"):
        heading = (BUILT_IN_HEADINGS.get(language) or BUILT_IN_HEADINGS["en"])["heading"]
        inner = f"## {heading}\n\n" + inner
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
        out["warning"] = f"{', '.join(missing)} not found. Check the development/default branches in version.yml, or git fetch and try again"
        return out
    out["ahead_count"] = _commit_count(project_root, base_ref, head_ref)
    out["behind_count"] = _commit_count(project_root, head_ref, base_ref)
    if out["ahead_count"] == 0:
        out["warning"] = (f"{head_ref} has no commits ahead of {base_ref}; there may be nothing to release, or "
                          "the branch pair may be wrong (confirm this repo's real release flow with the user)")
    return out


# deploy 브랜치형 레포의 배포 브랜치 이름 (개발은 기본 브랜치, 배포는 이 브랜치로 PR)
DEPLOY_BRANCH_NAME = "deploy"


def detect_release_shape(project_root: Path, branches: dict, check: dict) -> dict:
    """릴리스 구조 판정: standard(개발 > 기본) | deploy_branch(기본 > deploy, #970)

    개발 브랜치가 origin 에 없고 origin/deploy 가 있으면 deploy 브랜치형. 그 외는 standard 그대로
    """
    is_deploy_branch_shape = (not check.get("head_exists")
                              and branches["head"] != DEPLOY_BRANCH_NAME
                              and _ref_exists(project_root, f"origin/{DEPLOY_BRANCH_NAME}"))
    if not is_deploy_branch_shape:
        return {"release_shape": "standard"}
    # 개발은 기본 브랜치에서, 릴리스 PR 은 기본 브랜치 > deploy
    head = branches["base"] if branches["base"] != DEPLOY_BRANCH_NAME else "main"
    return {
        "release_shape": "deploy_branch",
        "release_branches": {"head": head, "base": DEPLOY_BRANCH_NAME},
        "release_steps": [
            f"follow the deploy mode steps as written with HEAD_BRANCH={head}, BASE_BRANCH={DEPLOY_BRANCH_NAME} "
            f"(do not use the missing {branches['head']} as head)",
            f"Step 1-1: sync-base --head {head} --base {DEPLOY_BRANCH_NAME}",
            f"Step 6: create-pr ... {head} {DEPLOY_BRANCH_NAME} (release notes in the body)",
            f"Step 7: deploy-status --pr N --base {DEPLOY_BRANCH_NAME}",
            "confirm the pair once with the user (without version.yml, record it in the per-repo config)",
        ],
    }


def cmd_sync_base(args) -> int:
    """배포 전 base > head 역방향 병합: fetch > 차이 확인 > merge. 충돌은 되돌리지 않고 멈춘다."""
    root = Path(args.project_root).resolve() if args.project_root else Path.cwd()
    current = _git(root, "branch", "--show-current").stdout.strip()
    if current != args.head:
        return emit({"ok": False, "code": "wrong_branch", "current": current, "expected": args.head,
                     "error": "the current branch is not the release head (another session may have switched it)",
                     "next": "do not switch branches on your own; tell the user"})
    fetched = _git(root, "fetch", "origin")
    if fetched.returncode != 0:
        return emit({"ok": False, "code": "fetch_failed", "error": fetched.stderr.strip()[:300], "next": None})
    behind = _git(root, "log", "--oneline", f"origin/{args.head}..origin/{args.base}").stdout.strip().splitlines()
    if not behind:
        return emit({"ok": True, "code": "in_sync", "behind": [], "summary": f"origin/{args.base} is already included",
                     "next": "continue the deploy steps"})
    merged = _git(root, "merge", "--no-edit", f"origin/{args.base}")
    if merged.returncode == 0:
        return emit({"ok": True, "code": "merged", "behind": behind[:20],
                     "summary": f"merged {len(behind)} commit(s) from origin/{args.base}", "next": "push, then continue the deploy steps"})
    conflicted = _git(root, "diff", "--name-only", "--diff-filter=U").stdout.split()
    if not conflicted:
        # 충돌 파일이 없는데 실패했다면 충돌이 아니라 다른 원인(커밋 작성자 미설정, 훅, 더러운 작업트리 등)이다
        return emit({"ok": False, "code": "merge_failed", "behind": behind[:20],
                     "error": (merged.stderr or merged.stdout).strip()[:400],
                     "next": "read the cause and fix it (git config user.name/email, overlapping uncommitted changes, ...). It is not a conflict, so there is nothing to abort"})
    return emit({"ok": False, "code": "merge_conflict", "conflicted_files": conflicted[:30], "behind": behind[:20],
                 "error": "merge conflict", "next": "resolve the conflict keeping both sides' intent, or decide with the user (do not merge --abort or reset on your own)"})
