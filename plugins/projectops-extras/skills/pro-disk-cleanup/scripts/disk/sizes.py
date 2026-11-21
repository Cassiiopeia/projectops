"""Size measurement: free space, folder size (virtual mounts and other volumes excluded)"""
from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

from . import shell

BYTES_PER_GIGABYTE = 1024 ** 3
# Concurrent measurements (du waits on disk, so parallel is faster)
MEASURE_WORKERS = 6
# Time limit per folder (seconds) — past it, the count so far + is_partial
FOLDER_MEASURE_SECONDS = 120


def to_gigabytes(byte_count: int | None) -> float | None:
    return None if byte_count is None else round(byte_count / BYTES_PER_GIGABYTE, 2)


def free_space(path: str | None = None) -> dict:
    """Total, used and free space of the volume holding home"""
    target = path or str(Path.home())
    usage = shutil.disk_usage(target)
    return {"volume_of": target, "total_gb": to_gigabytes(usage.total), "used_gb": to_gigabytes(usage.used),
            "free_gb": to_gigabytes(usage.free), "used_percent": round(usage.used * 100 / usage.total, 1)}


def free_bytes(path: str | None = None) -> int:
    return shutil.disk_usage(path or str(Path.home())).free


def is_other_volume(path: Path) -> bool:
    """Mount points (device virtual filesystems, etc.) are not counted as local usage"""
    try:
        return os.path.ismount(path) or path.stat().st_dev != path.parent.stat().st_dev
    except OSError:
        return False


def folder_bytes(path: Path, max_seconds: int = FOLDER_MEASURE_SECONDS) -> tuple[int | None, bool]:
    """Folder size > (bytes, partially counted due to time limit). POSIX uses du -skx, Windows walks directly"""
    if not path.exists():
        return None, False
    if not shell.IS_WINDOWS and shell.has_command("du"):
        code, out, _ = shell.run(["du", "-skx", str(path)], timeout_seconds=max_seconds)
        if out.strip():
            try:
                return int(out.split()[0]) * 1024, code == 124
            except ValueError:
                pass  # odd du output > fall back to walking
    return _walk_bytes(path, max_seconds)


def _walk_bytes(path: Path, max_seconds: int) -> tuple[int, bool]:
    # Same volume only, links not followed
    deadline = time.monotonic() + max_seconds
    root_device = path.stat().st_dev
    total = 0
    pending = [str(path)]
    while pending:
        if time.monotonic() > deadline:
            return total, True
        current = pending.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    try:
                        if entry.is_symlink():
                            continue
                        info = entry.stat(follow_symlinks=False)
                        if entry.is_dir(follow_symlinks=False):
                            # Windows DirEntry.stat() reports st_dev as zero.
                            device = (
                                os.stat(entry.path, follow_symlinks=False).st_dev
                                if shell.IS_WINDOWS
                                else info.st_dev
                            )
                            if device == root_device:
                                pending.append(entry.path)
                        else:
                            total += info.st_size
                    except OSError:
                        continue  # no permission or file gone
        except OSError:
            continue  # unreadable folders are not counted
    return total, False


def newest_touch_seconds(path: Path, should_include_access: bool = True) -> float | None:
    """Most recent modification (or access) time of the folder and its direct children (epoch seconds). Call before sizing"""
    def touch_of(info) -> float:
        return max(info.st_mtime, info.st_atime) if should_include_access else info.st_mtime
    try:
        newest = touch_of(path.stat())
    except OSError:
        return None
    try:
        with os.scandir(path) as entries:
            for entry in entries:
                try:
                    newest = max(newest, touch_of(entry.stat(follow_symlinks=False)))
                except OSError:
                    continue  # entry gone
    except OSError:
        pass  # list unreadable > folder's own time only
    return newest


def age_days(epoch_seconds: float | None) -> float | None:
    return None if epoch_seconds is None else round((time.time() - epoch_seconds) / 86400, 1)
