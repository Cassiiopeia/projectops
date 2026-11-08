"""worktree 안 재생성 가능한 생성물 찾기: 이름 목록 > git 추적·최근 수정·사용 중 제외"""
from __future__ import annotations

import os
import time
from pathlib import Path

from . import shell, sizes

# 빌드·의존성 설치로 다시 만들어지는 폴더 이름
GENERATED_FOLDER_NAMES = frozenset({
    "build", "node_modules", ".dart_tool", "Pods", ".gradle", ".venv", "venv", "target",
    "dist", ".next", ".nuxt", ".turbo", ".build", "DerivedData", ".expo", ".parcel-cache",
})
# 생성물을 찾을 최대 깊이 (worktree 루트 기준)
SEARCH_DEPTH = 5
SKIP_DESCEND = frozenset({".git", ".idea", ".vscode"})


def is_generated_path(relative_path: str) -> bool:
    """git status 경로가 생성물 폴더 안이거나 플러그인 자동 생성 파일인지"""
    parts = Path(relative_path).parts
    if any(part in GENERATED_FOLDER_NAMES for part in parts):
        return True
    name = parts[-1] if parts else ""
    return name.startswith("generated_plugin") or name in {
        "GeneratedPluginRegistrant.java", "GeneratedPluginRegistrant.swift", "GeneratedPluginRegistrant.m",
        "GeneratedPluginRegistrant.h", "Generated.xcconfig", "flutter_export_environment.sh",
        "local.properties", ".flutter-plugins", ".flutter-plugins-dependencies", "pubspec.lock",
        "Podfile.lock", "gradlew", "gradlew.bat", "gradle-wrapper.jar",
    }


def find_generated_folders(worktree: Path) -> list[Path]:
    found: list[Path] = []
    pending = [(worktree, 0)]
    while pending:
        current, depth = pending.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    if not entry.is_dir(follow_symlinks=False) or entry.name in SKIP_DESCEND:
                        continue
                    if entry.name in GENERATED_FOLDER_NAMES:
                        found.append(Path(entry.path))
                    elif depth + 1 < SEARCH_DEPTH:
                        pending.append((Path(entry.path), depth + 1))
        except OSError:
            continue
    return found


def is_tracked_by_git(worktree: Path, folder: Path) -> bool:
    relative = str(folder.relative_to(worktree))
    _, out = shell.git(str(worktree), "ls-files", "--", relative)
    return bool(out)


def describe_folder(worktree: Path, folder: Path, idle_hours: float, users: list[str] | None) -> dict:
    """생성물 1개 > {path, size, skip_reason}. skip_reason 3개: tracked, recently_modified, in_use"""
    # 크기 측정이 접근 시각을 바꾸므로 시각을 먼저, 수정 시각만 봄
    touched = sizes.newest_touch_seconds(folder, include_access=False)
    byte_count, is_partial = sizes.folder_bytes(folder)
    skip_reason = None
    if is_tracked_by_git(worktree, folder):
        skip_reason = "tracked_by_git"
    elif users:
        skip_reason = "in_use"
    elif touched and time.time() - touched < idle_hours * 3600:
        skip_reason = "recently_modified"
    return {"path": str(folder), "name": folder.name, "size_gb": sizes.to_gigabytes(byte_count),
            "size_bytes": byte_count or 0, "is_partial_size": is_partial,
            "last_touched_days": sizes.age_days(touched), "skip_reason": skip_reason}
