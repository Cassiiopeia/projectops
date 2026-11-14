"""Safe git calls and file reads on a local clone: blocks a malicious .git/config, skips symlinks, paths outside the repo and anything over the caps
"""
from __future__ import annotations

import os
import stat
import subprocess
from collections import Counter
from pathlib import Path

# Cap on total bytes read at once — keeps a large monorepo from blowing up memory and time
MAX_TOTAL_BYTES = 50 * 1024 * 1024
MAX_SOURCE_FILES = 20000
_SOURCE_MAX_BYTES = 300_000
_MANIFEST_MAX_BYTES = 1_000_000


# Keep a malicious repo's .git/config from running commands through a mere git call (core.fsmonitor runs on ls-files — reproduced)
_GIT_SAFE = ["-c", "core.fsmonitor=false", "-c", f"core.hooksPath={os.devnull}", "-c", "core.pager=cat",
             "-c", "core.quotepath=false", "-c", "protocol.ext.allow=never", "-c", "core.untrackedCache=false"]


def _git_env() -> dict:
    env = {k: v for k, v in os.environ.items()
           if k not in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_CONFIG_PARAMETERS")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0",
               GIT_CONFIG_GLOBAL=os.devnull)
    return env


def _git_raw(root: Path, *args: str, timeout: int = 60) -> tuple[int, str, str]:
    """(returncode, stdout, stderr). The code is returned as is to tell failure apart from 'no results'."""
    try:
        r = subprocess.run(["git", *_GIT_SAFE, "-C", str(root), *args], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", env=_git_env(), timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, "", f"{type(e).__name__}: {e}"
    return r.returncode, r.stdout, r.stderr


def _git(root: Path, *args: str) -> str:
    rc, out, _ = _git_raw(root, *args)
    return out if rc == 0 else ""


class _Budget:
    """Caps on total bytes and file count read, plus tallies of skip reasons."""

    def __init__(self, max_bytes: int = MAX_TOTAL_BYTES, max_files: int = MAX_SOURCE_FILES):
        self.max_bytes, self.max_files = max_bytes, max_files
        self.used = 0
        self.files = 0
        self.skipped: Counter = Counter()
        self.capped_bytes = False
        self.capped_files = False


def _safe_read(root: Path, rel: str, limit: int, budget: _Budget) -> str | None:
    """Read tracked files safely: skip symlinks, paths outside the repo, non-regular files, files too large and anything over the total cap."""
    fp = root / rel
    try:
        st = os.lstat(fp)
    except OSError:
        return None
    if stat.S_ISLNK(st.st_mode):
        budget.skipped["symlinks"] += 1
        return None
    if not stat.S_ISREG(st.st_mode):
        budget.skipped["not_regular"] += 1
        return None
    if st.st_size > limit:
        budget.skipped["too_large"] += 1
        return None
    try:
        fp.resolve().relative_to(root)  # also blocks escaping the repo through a symlinked parent path
    except ValueError:
        budget.skipped["outside_root"] += 1
        return None
    if budget.files >= budget.max_files:
        budget.capped_files = True
        return None
    if budget.used + st.st_size > budget.max_bytes:
        budget.capped_bytes = True
        return None
    try:
        with open(fp, "rb") as f:
            raw = f.read(limit + 1)
    except OSError:
        return None
    budget.used += len(raw)
    budget.files += 1
    return raw.decode("utf-8", "ignore")


def _gitfile_target(root: Path) -> tuple[bool, str | None]:
    """When `.git` is a file (worktree·submodule), check that the gitdir it points to is a real git directory."""
    gp = root / ".git"
    if not gp.is_file():
        return True, None
    try:
        first = gp.read_text(encoding="utf-8", errors="ignore").splitlines()[0]
    except (OSError, IndexError):
        return False, None
    if not first.startswith("gitdir:"):
        return False, None
    target = Path(first.split(":", 1)[1].strip())
    if not target.is_absolute():
        target = (root / target)
    target = target.resolve()
    return (target / "HEAD").is_file(), str(target)
