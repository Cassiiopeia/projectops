"""로컬 clone 의 안전한 git 호출·파일 읽기: 악성 .git/config 차단, 심볼릭 링크·레포 밖·상한 초과 건너뜀
"""
from __future__ import annotations

import os
import stat
import subprocess
from collections import Counter
from pathlib import Path

# 한 번에 읽는 총량 상한 — 대형 모노레포에서 메모리·시간이 터지지 않게
MAX_TOTAL_BYTES = 50 * 1024 * 1024
MAX_SOURCE_FILES = 20000
_SOURCE_MAX_BYTES = 300_000
_MANIFEST_MAX_BYTES = 1_000_000


# 악성 레포의 .git/config 가 git 호출만으로 명령을 실행하지 못하게 막는다 (core.fsmonitor 가 ls-files 에서 실행됨 — 재현됨)
_GIT_SAFE = ["-c", "core.fsmonitor=false", "-c", f"core.hooksPath={os.devnull}", "-c", "core.pager=cat",
             "-c", "core.quotepath=false", "-c", "protocol.ext.allow=never", "-c", "core.untrackedCache=false"]


def _git_env() -> dict:
    env = {k: v for k, v in os.environ.items()
           if k not in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_CONFIG_PARAMETERS")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0",
               GIT_CONFIG_GLOBAL=os.devnull)
    return env


def _git_raw(root: Path, *args: str, timeout: int = 60) -> tuple[int, str, str]:
    """(returncode, stdout, stderr). 실패와 '결과 없음'을 구분하려고 코드를 그대로 돌려준다."""
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
    """읽기 총량·파일 수 상한과 건너뛴 이유 집계."""

    def __init__(self, max_bytes: int = MAX_TOTAL_BYTES, max_files: int = MAX_SOURCE_FILES):
        self.max_bytes, self.max_files = max_bytes, max_files
        self.used = 0
        self.files = 0
        self.skipped: Counter = Counter()
        self.capped_bytes = False
        self.capped_files = False


def _safe_read(root: Path, rel: str, limit: int, budget: _Budget) -> str | None:
    """추적된 파일을 안전하게 읽는다: 심볼릭 링크·레포 밖·일반 파일 아님·너무 큼·총량 초과는 건너뛴다."""
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
        fp.resolve().relative_to(root)  # 중간 경로가 링크여서 밖으로 나가는 경우까지 막는다
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
    """`.git` 이 파일(worktree·submodule)이면 가리키는 gitdir 이 실재하는 git 디렉터리인지 본다."""
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
