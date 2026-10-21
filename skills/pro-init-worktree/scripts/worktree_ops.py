"""worktree_cli 의 실행 서브커맨드: create(브랜치 > worktree), copy(기억한 로컬 파일 복사), remove(안전 제거) (#944).

손으로 치던 의식(임시 파이썬 스크립트, `git branch --no-track`, `cp`, `git worktree remove --force`)을
한 명령과 JSON verdict 로 바꾼다.
"""
from __future__ import annotations

import filecmp
import os
import shutil
import subprocess
import sys
from pathlib import Path

from common.emit import emit

_SCRIPTS_ROOT = Path(__file__).resolve().parents[3] / "scripts"


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=60)


def _worktree_path_of(root: Path, branch: str) -> str | None:
    """git worktree list --porcelain 에서 브랜치가 체크아웃된 경로"""
    blocks = _git(root, "worktree", "list", "--porcelain").stdout.split("\n\n")
    for block in blocks:
        fields = dict(line.split(" ", 1) for line in block.splitlines() if " " in line)
        if fields.get("branch") == f"refs/heads/{branch}":
            return fields.get("worktree")
    return None


def cmd_create(args, toplevel) -> int:
    """브랜치명 > (없으면 --base 에서 분기) > worktree 생성 > 로컬 파일 복사. 기존 worktree_manager 를 그대로 쓴다."""
    root = toplevel(args.root)
    manager = _SCRIPTS_ROOT / "worktree_manager.py"
    env = {**os.environ, "GIT_BRANCH_NAME": args.branch, "PYTHONIOENCODING": "utf-8"}
    if args.base:
        env["GIT_BASE_REF"] = args.base
    run = subprocess.run([sys.executable, "-X", "utf8", str(manager)], cwd=root, env=env,
                         capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
    path = _worktree_path_of(root, args.branch)
    tail = [ln for ln in run.stdout.splitlines() if ln.strip()][-12:]
    if run.returncode != 0 or not path:
        return emit({"ok": False, "code": "worktree_create_failed", "branch": args.branch,
                     "output_tail": tail + [ln for ln in run.stderr.splitlines()[-5:]],
                     "next": "output_tail 의 첫 오류를 고친다 (--base 가 origin/develop 같은 실재 ref 인지 확인)"})
    return emit({"ok": True, "code": "ok", "branch": args.branch, "worktree": path, "base": args.base,
                 "output_tail": tail, "summary": f"worktree 생성: {path}",
                 "next": f"worktree_cli.py copy --root {root} --to {path}"})


def cmd_copy(args, toplevel, split, clean, memory_file, load) -> int:
    """기억한 복사 세트(또는 --files)를 worktree 로 복사. 기존 파일은 --overwrite 없이는 건드리지 않는다."""
    root = toplevel(args.root)
    dest = Path(args.to).expanduser().resolve()
    if not dest.is_dir():
        return emit({"ok": False, "code": "worktree_not_found", "error": f"대상 폴더가 없다: {dest}",
                     "next": "create 로 worktree 를 먼저 만든다"})
    rels = [clean(r) for r in split(args.files)]
    if args.files and None in rels:
        return emit({"ok": False, "code": "bad_path", "error": "레포 루트 기준 상대 경로만 받는다",
                     "next": "절대경로·`..`·`=` 를 뺀다"})
    if not args.files:
        mem = load(memory_file(root)) or {}
        rels = [p for p in mem.get("copied", []) if isinstance(p, str)]
        if not rels:
            return emit({"ok": False, "code": "no_memory",
                         "error": "기억한 복사 세트가 없다", "next": "recall 로 후보를 보고 --files a,b 로 복사한 뒤 record"})
    copied, missing, kept = [], [], []
    for rel in rels:
        src, dst = root / rel, dest / rel
        if not src.exists():
            missing.append(rel)
        elif dst.exists() and not args.overwrite:
            kept.append(rel)
        elif src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
            copied.append(rel)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            copied.append(rel)
    return emit({"ok": True, "code": "ok", "copied": copied, "missing": missing, "kept_existing": kept,
                 "summary": f"복사 {len(copied)}개, 이미 있어 유지 {len(kept)}개, 원본에 없음 {len(missing)}개",
                 "next": f"새로 판단한 파일이 있으면 record --root {root} --copied ... 로 기록"})


def _is_untouched_local_copy(rel: str, root: Path, target: Path, copied: list[str]) -> bool:
    """미추적 파일이 기억한 복사 세트(파일·`폴더/`) 안에 있고 원본과 내용이 같은가"""
    in_copied_set = any(rel == c.rstrip("/") or (c.endswith("/") and rel.startswith(c)) for c in copied)
    source, copy = root / rel, target / rel
    return in_copied_set and source.is_file() and copy.is_file() and filecmp.cmp(source, copy, shallow=False)


def _split_dirty(root: Path, target: Path, copied: list[str]) -> tuple[list[str], list[str]]:
    """status > (진짜 변경, 원본과 같은 복사본). 복사본은 copy 가 깐 것이라 지워도 잃는 것이 없다"""
    # -z: 한글 경로가 따옴표·8진수로 바뀌지 않게, untracked=all: 폴더 대신 파일 단위로 비교
    status = _git(target, "status", "--porcelain", "-z", "--untracked-files=all").stdout
    changes, local_copies = [], []
    entries = iter(e for e in status.split("\0") if e.strip())
    for entry in entries:
        code, rel = entry[:2], entry[3:]
        if code[0] in "RC":
            next(entries, None)  # -z 의 rename·copy 는 원래 경로가 다음 칸에 따로 온다
        if code == "??" and _is_untouched_local_copy(rel, root, target, copied):
            local_copies.append(rel)
        else:
            changes.append(entry)
    return changes, local_copies


def cmd_remove(args, toplevel, memory_file, load) -> int:
    """worktree 제거: 미커밋 변경이 있으면 거절(dirty), --force 는 사용자가 정한 뒤에만.

    기억한 복사 세트 중 원본과 같은 미추적 파일은 변경으로 세지 않는다 (#974).
    """
    root = toplevel(args.root)
    path = args.path or (_worktree_path_of(root, args.branch) if args.branch else None)
    if not path:
        return emit({"ok": False, "code": "worktree_not_found",
                     "error": "--path 또는 체크아웃된 --branch 가 필요하다", "next": "git worktree list 로 경로를 본다"})
    target = Path(path).resolve()
    if target == root.resolve():
        return emit({"ok": False, "code": "is_main_worktree", "error": "원본 레포는 제거하지 않는다", "next": None})
    copied = [p for p in (load(memory_file(root)) or {}).get("copied", []) if isinstance(p, str)]
    dirty, local_copies = _split_dirty(root, target, copied)
    if dirty and not args.force:
        return emit({"ok": False, "code": "dirty", "path": str(target), "changes": dirty[:30],
                     "ignored_local_copies": local_copies,
                     "error": f"미커밋 변경 {len(dirty)}개가 있다",
                     "next": "필요한 변경을 보존한 뒤, 버려도 된다고 사용자가 정하면 --force 로 다시"})
    # 남은 미추적이 원본과 같은 복사본뿐이면 git 이 거절하지 않게 --force (잃는 것 없음)
    should_force_git = bool(args.force or local_copies)
    args_git = ["worktree", "remove", *(["--force"] if should_force_git else []), str(target)]
    res = _git(root, *args_git)
    if res.returncode != 0:
        return emit({"ok": False, "code": "remove_failed", "path": str(target),
                     "error": (res.stderr or res.stdout).strip()[:300], "next": None})
    return emit({"ok": True, "code": "ok", "removed": str(target), "forced": bool(args.force),
                 "ignored_local_copies": local_copies,
                 "summary": f"worktree 제거: {target}"
                            + (f" (원본과 같은 로컬 복사본 {len(local_copies)}개 함께 정리)" if local_copies else ""),
                 "next": "브랜치와 커밋은 그대로 남아 있다 (이슈가 닫혔는지 먼저 확인했는지 점검)"})
