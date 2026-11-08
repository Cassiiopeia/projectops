"""고정 목록 밖 큰 폴더 찾기: 홈 아래 1~2단계 크기순 > 알려진 위치와 대조 > 나머지는 미분류(decide)
이름 목록이 아니라 실제 크기로 찾음 (어느 컴퓨터·도구든 같은 방식)
"""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import catalog, generated, sizes

# 이 크기 이상인 1단계 폴더는 한 단계 더 들어가 나눠 봄 (5GB)
DESCEND_THRESHOLD_BYTES = 5 * 1024 ** 3
# 보고 최소 크기 (500MB)
REPORT_MINIMUM_BYTES = 500 * 1024 ** 2
# 클라우드 동기화 폴더: 내려받지 않은 파일이 섞여 크기가 실제와 다르고, 지우면 다른 기기에서도 사라짐
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
    """알려진 위치와의 관계 > (키, 관계). 관계 3개: same, inside (알려진 위치 안), contains (알려진 위치를 품음)"""
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
