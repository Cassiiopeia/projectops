"""삭제 게이트: 경로 검증 > 지우기. 모든 삭제가 여기를 거친다"""
from __future__ import annotations

import os
import shutil
import stat
import sys
from pathlib import Path

from . import shell

# 지울 경로의 최소 깊이 (홈·드라이브 루트 바로 아래 폴더 차단)
MINIMUM_PATH_DEPTH = 3


def protected_paths() -> set[Path]:
    """어떤 경우에도 지우지 않는 경로: 루트, 홈, 홈 바로 아래 주요 폴더"""
    home = Path.home().resolve()
    protected = {Path("/"), home, home.parent}
    for name in ("Desktop", "Documents", "Downloads", "Library", "AppData", "Pictures", "Movies", ".ssh", ".config"):
        protected.add(home / name)
    if shell.IS_WINDOWS:
        protected.update(Path(f"{letter}:\\") for letter in "CDEFGH")
    return protected


def refusal_reason(target: str | None, allowed_base: Path) -> str | None:
    """지우면 안 되는 이유 (없으면 None). 빈 경로·상대경로·보호 경로·허용 폴더 밖·링크 거절"""
    if not target or not str(target).strip():
        return "empty_path"
    raw = Path(target)
    if not raw.is_absolute():
        return "relative_path"
    if raw.is_symlink():
        return "symlink"
    resolved = raw.resolve()
    base = allowed_base.resolve()
    if resolved in protected_paths() or resolved == base:
        return "protected_path"
    if len(resolved.parts) < MINIMUM_PATH_DEPTH + 1:
        return "too_shallow"
    if base not in resolved.parents:
        return "outside_allowed_base"
    if not resolved.exists():
        return "missing"
    return None


def _clear_readonly_and_retry(function, path, _error_info):
    # Windows 읽기 전용 파일(.git 객체 등) 대응
    try:
        os.chmod(path, stat.S_IWRITE)
        function(path)
    except OSError:
        pass


def remove_tree(target: str, allowed_base: Path) -> dict:
    """게이트 통과 시 폴더 삭제 > {path, removed, reason}"""
    reason = refusal_reason(target, allowed_base)
    if reason:
        return {"path": target, "removed": False, "reason": reason}
    resolved = Path(target).resolve()
    if resolved.is_dir():
        # 3.12+ onexc, 그 전 onerror
        if sys.version_info >= (3, 12):
            shutil.rmtree(resolved, onexc=_clear_readonly_and_retry)
        else:
            shutil.rmtree(resolved, onerror=_clear_readonly_and_retry)
    else:
        resolved.unlink()
    still_exists = resolved.exists()
    return {"path": str(resolved), "removed": not still_exists,
            "reason": "partially_removed" if still_exists else None}
