"""용량 측정: 남은 공간, 폴더 크기 (가상 마운트·다른 볼륨 제외)"""
from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

from . import shell

BYTES_PER_GIGABYTE = 1024 ** 3
# 폴더 1개 측정 시간 상한 (초) — 넘으면 그때까지 센 값 + is_partial
FOLDER_MEASURE_SECONDS = 120


def to_gigabytes(byte_count: int | None) -> float | None:
    return None if byte_count is None else round(byte_count / BYTES_PER_GIGABYTE, 2)


def free_space(path: str | None = None) -> dict:
    """홈이 있는 볼륨의 전체·사용·남은 용량"""
    target = path or str(Path.home())
    usage = shutil.disk_usage(target)
    return {"volume_of": target, "total_gb": to_gigabytes(usage.total), "used_gb": to_gigabytes(usage.used),
            "free_gb": to_gigabytes(usage.free), "used_percent": round(usage.used * 100 / usage.total, 1)}


def free_bytes(path: str | None = None) -> int:
    return shutil.disk_usage(path or str(Path.home())).free


def is_other_volume(path: Path) -> bool:
    """마운트 지점(기기 가상 파일시스템 등)이면 로컬 사용량에 넣지 않음"""
    try:
        return os.path.ismount(path) or path.stat().st_dev != path.parent.stat().st_dev
    except OSError:
        return False


def folder_bytes(path: Path, max_seconds: int = FOLDER_MEASURE_SECONDS) -> tuple[int | None, bool]:
    """폴더 크기 > (바이트, 시간 상한으로 일부만 셌는지). POSIX 는 du -skx, Windows 는 직접 순회"""
    if not path.exists():
        return None, False
    if not shell.IS_WINDOWS and shell.has_command("du"):
        code, out, _ = shell.run(["du", "-skx", str(path)], timeout_seconds=max_seconds)
        if out.strip():
            try:
                return int(out.split()[0]) * 1024, code == 124
            except ValueError:
                pass
    return _walk_bytes(path, max_seconds)


def _walk_bytes(path: Path, max_seconds: int) -> tuple[int, bool]:
    # 같은 볼륨만, 링크는 따라가지 않음
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
                            if info.st_dev == root_device:
                                pending.append(entry.path)
                        else:
                            total += info.st_size
                    except OSError:
                        continue
        except OSError:
            continue
    return total, False


def newest_touch_seconds(path: Path, include_access: bool = True) -> float | None:
    """폴더와 바로 아래 항목의 마지막 수정(·접근) 시각 중 가장 최근 (epoch 초). 크기 측정 전에 부를 것"""
    def touch_of(info) -> float:
        return max(info.st_mtime, info.st_atime) if include_access else info.st_mtime
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
                    continue
    except OSError:
        pass
    return newest


def age_days(epoch_seconds: float | None) -> float | None:
    return None if epoch_seconds is None else round((time.time() - epoch_seconds) / 86400, 1)
