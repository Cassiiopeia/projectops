"""Find large folders outside the fixed list: home 1-2 levels deep by size > match against known locations > the rest is unclassified (decide)
Finds by actual size, not by a name list (same approach on any computer or tool)
"""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import catalog, generated, sizes

# Level-1 folders at or above this size are split one level deeper (5GB)
DESCEND_THRESHOLD_BYTES = 5 * 1024 ** 3
# Minimum size to report (500MB)
REPORT_MINIMUM_BYTES = 500 * 1024 ** 2
# Cloud sync folders: not-downloaded files skew the size, and deleting removes them on other devices too
CLOUD_SYNC_NAMES = frozenset({"CloudStorage", "Mobile Documents", "OneDrive", "Dropbox", "Google Drive", "iCloud Drive"})


def _children(folder: Path) -> list[Path]:
    try:
        with os.scandir(folder) as entries:
            return [Path(entry.path) for entry in entries
                    if entry.is_dir(follow_symlinks=False) and not entry.name.startswith(".Trash")]
    except OSError:
        return []


def _measure(folders: list[Path], max_seconds: int) -> list[tuple[Path, int, bool]]:
    def one(folder: Path):
        if sizes.is_other_volume(folder):
            return folder, 0, False
        byte_count, is_partial = sizes.folder_bytes(folder, max_seconds)
        return folder, byte_count or 0, is_partial
    with ThreadPoolExecutor(max_workers=sizes.MEASURE_WORKERS) as pool:
        return list(pool.map(one, folders))


def _known_key(path: Path, known: list[tuple[Path, str]]) -> tuple[str | None, str]:
    """Relation to known locations > (key, relation). 3 relations: same, inside (within a known location), contains (holds a known location)"""
    resolved = path.resolve()
    for location_path, key in known:
        if resolved == location_path:
            return key, "same"
        if location_path in resolved.parents:
            return key, "inside"
    contained = [key for location_path, key in known if resolved in location_path.parents]
    return (",".join(contained), "contains") if contained else (None, "unclassified")


def find_largest(limit: int, max_seconds: int, home: Path | None = None) -> list[dict]:
    home = home or Path.home()
    known = [(location.path.resolve(), location.key) for location in catalog.locations() if location.path.exists()]
    first_level = _measure(_children(home), max_seconds)
    rows: list[tuple[Path, int, bool]] = []
    for folder, byte_count, is_partial in first_level:
        if byte_count >= DESCEND_THRESHOLD_BYTES:
            rows += _measure(_children(folder), max_seconds)
        rows.append((folder, byte_count, is_partial))
    results = []
    for folder, byte_count, is_partial in sorted(rows, key=lambda row: -row[1]):
        if byte_count < REPORT_MINIMUM_BYTES:
            continue
        key, relation = _known_key(folder, known)
        is_cloud = folder.name in CLOUD_SYNC_NAMES
        results.append({"path": str(folder), "size_gb": sizes.to_gigabytes(byte_count), "is_partial_size": is_partial,
                        "depth": len(folder.relative_to(home).parts), "known_location": key, "relation": relation,
                        "is_cloud_sync": is_cloud, "is_generated_name": folder.name in generated.GENERATED_FOLDER_NAMES,
                        "tier": catalog.TIER_KEEP if is_cloud else (None if key else catalog.TIER_DECIDE)})
    return results[:limit]
