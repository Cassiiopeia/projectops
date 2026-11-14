"""worktree backup: staged and unstaged patches + copies of unique untracked files > verify"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from . import generated, shell

# Large files are not copied (50MB) — keeps app binaries and archives from re-growing the backup
MAX_COPY_BYTES = 50 * 1024 * 1024
# Max number of untracked-file copies — above it, report backup failure and do not remove
MAX_COPY_FILE_COUNT = 5000
UNSAFE_NAME_PATTERN = re.compile(r"[^\w.#-]+")
BACKUP_INFO_FILE = "backup.json"


def _safe_folder_name(text: str) -> str:
    return UNSAFE_NAME_PATTERN.sub("_", text)[:120] or "worktree"


def _write_patch(worktree: Path, destination: Path, *diff_arguments: str) -> int:
    # Patches stay as raw bytes (keeps non-UTF-8 file contents)
    try:
        completed = subprocess.run(["git", "-C", str(worktree), "diff", "--binary", *diff_arguments],
                                   capture_output=True, timeout=300)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RuntimeError(f"git diff failed in {worktree}: {error}") from error
    if completed.returncode != 0:
        raise RuntimeError(f"git diff failed in {worktree}")
    destination.write_bytes(completed.stdout)
    return len(completed.stdout)


def _untracked_paths(worktree: Path) -> tuple[list[str], bool]:
    """Untracked file relative paths > (paths, over the count limit). Non-ignored + ignored (.env, signing keys, etc.), generated folders excluded"""
    base = ["git", "-c", "core.quotepath=false", "-C", str(worktree), "ls-files", "--others", "--exclude-standard"]
    _, plain, _ = shell.run(base, timeout_seconds=300)
    _, ignored, _ = shell.run(base + ["--ignored", "--directory"], timeout_seconds=300)
    paths = list(filter(None, plain.splitlines()))
    for entry in filter(None, ignored.splitlines()):
        if generated.is_generated_path(entry.rstrip("/")):
            continue
        if not entry.endswith("/"):
            paths.append(entry)
            continue
        for folder, child_folders, files in os.walk(worktree / entry):
            child_folders[:] = [name for name in child_folders if name not in generated.GENERATED_FOLDER_NAMES]
            paths += [str((Path(folder) / name).relative_to(worktree)) for name in files]
            if len(paths) > MAX_COPY_FILE_COUNT:
                return paths, True
    return paths, len(paths) > MAX_COPY_FILE_COUNT


def _copy_untracked(worktree: Path, destination: Path) -> tuple[list[str], list[str]]:
    # Copy, skipping generated output and large files
    relatives, is_over_limit = _untracked_paths(worktree)
    if is_over_limit:
        raise RuntimeError(f"more than {MAX_COPY_FILE_COUNT} untracked files; review them by hand")
    copied, skipped = [], []
    for relative in relatives:
        source = worktree / relative
        if generated.is_generated_path(relative) or not source.is_file() or source.is_symlink():
            continue
        if source.stat().st_size > MAX_COPY_BYTES:
            skipped.append(relative)
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied.append(relative)
    return copied, skipped


def backup_worktree(facts: dict, backup_base: Path) -> dict:
    """Create backup > verification result. On failure returns {ok: False} instead of raising"""
    worktree = Path(facts["path"])
    repository = _safe_folder_name((facts.get("repository") or worktree.parent.name).replace("/", "__"))
    branch = _safe_folder_name(facts.get("branch") or f"detached_{worktree.name}")
    destination = backup_base / repository / f"{branch}_{time.strftime('%H%M%S')}"
    destination.mkdir(parents=True, exist_ok=True)
    # May contain secret files, so owner-only access (POSIX). On failure the result has is_private False
    is_private = True
    for folder in (backup_base, destination):
        try:
            os.chmod(folder, 0o700)
        except OSError:
            is_private = False
    try:
        staged_bytes = _write_patch(worktree, destination / "staged.patch", "--cached")
        unstaged_bytes = _write_patch(worktree, destination / "unstaged.patch")
        copied, skipped_large = _copy_untracked(worktree, destination / "untracked")
    except (OSError, RuntimeError) as error:
        return {"ok": False, "backup_path": str(destination), "error": str(error)}
    _, head = shell.git(str(worktree), "rev-parse", "HEAD")
    info = {"worktree": str(worktree), "repository": facts.get("repository"), "branch": facts.get("branch"),
            "head": head, "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "untracked_copied": copied,
            "untracked_skipped_large": skipped_large,
            "restore": "git worktree add <path> <branch>; git apply staged.patch unstaged.patch; copy untracked/"}
    (destination / BACKUP_INFO_FILE).write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    is_verified = (destination / "staged.patch").stat().st_size == staged_bytes \
        and (destination / "unstaged.patch").stat().st_size == unstaged_bytes \
        and all((destination / "untracked" / relative).is_file() for relative in copied)
    return {"ok": is_verified, "backup_path": str(destination), "is_private": is_private or shell.IS_WINDOWS,
            "head": head, "untracked_copied": len(copied),
            "untracked_skipped_large": skipped_large, "patch_bytes": staged_bytes + unstaged_bytes}
