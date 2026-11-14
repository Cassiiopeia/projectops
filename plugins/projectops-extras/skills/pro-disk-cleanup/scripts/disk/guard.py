"""Delete gate: validate path > delete. Every deletion goes through here"""
from __future__ import annotations

import os
import shutil
import stat
import sys
from pathlib import Path

from . import shell

# Minimum depth of a deletable path (blocks folders right under home or a drive root)
MINIMUM_PATH_DEPTH = 3


def protected_paths() -> set[Path]:
    """Paths never deleted: root, home, main folders right under home"""
    home = Path.home().resolve()
    protected = {Path("/"), home, home.parent}
    for name in ("Desktop", "Documents", "Downloads", "Library", "AppData", "Pictures", "Movies", ".ssh", ".config"):
        protected.add(home / name)
    if shell.IS_WINDOWS:
        protected.update(Path(f"{letter}:\\") for letter in "CDEFGH")
    return protected


def refusal_reason(target: str | None, allowed_base: Path) -> str | None:
    """Reason not to delete (None if none). Rejects empty, relative, protected, outside allowed folders, links"""
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
    # Handle Windows read-only files (.git objects, etc.)
    try:
        os.chmod(path, stat.S_IWRITE)
        function(path)
    except OSError:
        pass  # remove_tree reports leftovers as partially_removed


def remove_tree(target: str, allowed_base: Path) -> dict:
    """Delete the folder if it passes the gate > {path, removed, reason}"""
    reason = refusal_reason(target, allowed_base)
    if reason:
        return {"path": target, "removed": False, "reason": reason}
    resolved = Path(target).resolve()
    if resolved.is_dir():
        # 3.12+ onexc, older onerror
        if sys.version_info >= (3, 12):
            shutil.rmtree(resolved, onexc=_clear_readonly_and_retry)
        else:
            shutil.rmtree(resolved, onerror=_clear_readonly_and_retry)
    else:
        resolved.unlink()
    still_exists = resolved.exists()
    return {"path": str(resolved), "removed": not still_exists,
            "reason": "partially_removed" if still_exists else None}
