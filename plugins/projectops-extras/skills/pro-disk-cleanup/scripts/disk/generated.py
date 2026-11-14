"""Find regenerable output inside a worktree: name list > exclude git-tracked, recently modified, in use"""
from __future__ import annotations

import os
import time
from pathlib import Path

from . import shell, sizes

# Folder names recreated by builds and dependency installs
GENERATED_FOLDER_NAMES = frozenset({
    "build", "node_modules", ".dart_tool", "Pods", ".gradle", ".venv", "venv", "target",
    "dist", ".next", ".nuxt", ".turbo", ".build", "DerivedData", ".expo", ".parcel-cache",
})
# Max depth to search for generated output (from the worktree root)
SEARCH_DEPTH = 5
SKIP_DESCEND = frozenset({".git", ".idea", ".vscode"})


def is_generated_path(relative_path: str) -> bool:
    """Whether a git status path is inside a generated folder or is a plugin-generated file"""
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
            continue  # no permission or folder gone
    return found


def is_tracked_by_git(worktree: Path, folder: Path) -> bool:
    relative = str(folder.relative_to(worktree))
    _, out = shell.git(str(worktree), "ls-files", "--", relative)
    return bool(out)


def describe_folder(worktree: Path, folder: Path, idle_hours: float, users: list[str] | None) -> dict:
    """One generated item > {path, size, skip_reason}. 3 skip_reasons: tracked, recently_modified, in_use"""
    # Sizing changes access times, so read times first, and only modification time
    touched = sizes.newest_touch_seconds(folder, should_include_access=False)
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
