"""읽기 전용 전체 보고: 남은 공간 + 위치별 크기·단계 + worktree 요약 + Docker 요약 (큰 것부터)"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import catalog, docker_cleanup, generated, sizes, worktrees
from .processes import ProcessSnapshot

# 동시 측정 개수
MEASURE_WORKERS = 6
# 위치 종류 > 정리 명령 힌트
NEXT_BY_KIND = {
    "tool": "tool {key} --yes",
    "aged": "aged {key} --older-than-days N  # N from the user for decide-tier items",
    "browser": "browser --yes",
    "info": None,
}


def _location_row(location: catalog.Location, max_seconds: int) -> dict:
    row = {"key": location.key, "label": location.label, "path": str(location.path), "tier": location.tier,
           "kind": location.kind, "note": location.note or None, "exists": location.path.exists(),
           "is_whole_folder_reclaimable": location.is_whole_folder_reclaimable}
    if not row["exists"]:
        return {**row, "size_gb": 0.0, "size_bytes": 0}
    if sizes.is_other_volume(location.path):
        return {**row, "size_gb": None, "size_bytes": 0, "is_other_volume": True,
                "note": "Mount point or other volume; not counted"}
    byte_count, is_partial = sizes.folder_bytes(location.path, max_seconds)
    hint = NEXT_BY_KIND[location.kind]
    return {**row, "size_gb": sizes.to_gigabytes(byte_count), "size_bytes": byte_count or 0,
            "is_partial_size": is_partial, "next": hint.format(key=location.key) if hint else None}


def _worktree_summary(roots: list[Path], idle_hours: float, snapshot: ProcessSnapshot) -> dict:
    facts = worktrees.collect(roots, idle_hours, with_size=False, snapshot=snapshot)
    linked = [item for item in facts if not item["is_main"]]
    generated_bytes = 0
    for item in linked:
        if item.get("is_missing"):
            continue
        for folder in generated.find_generated_folders(Path(item["path"])):
            byte_count, _ = sizes.folder_bytes(folder)
            generated_bytes += byte_count or 0
    return {"roots": [str(root) for root in roots], "repository_count": len({item["main_repository"] for item in facts}),
            "worktree_count": len(linked),
            "with_issue_number": sum(1 for item in linked if item.get("issue_number")),
            "with_real_changes": sum(1 for item in linked if item.get("real_change_count")),
            "in_use": sum(1 for item in linked if item.get("is_in_use")),
            "missing_folders": sum(1 for item in linked if item.get("is_missing")),
            "generated_output_gb": sizes.to_gigabytes(generated_bytes),
            "next": ["worktrees  # then check issue state with pro-github", "generated  # build output inside worktrees"]}


def build(roots: list[Path], idle_hours: float, is_worktree_skipped: bool, max_seconds: int) -> dict:
    started = time.monotonic()
    snapshot = ProcessSnapshot()
    # du 는 디스크 대기라 병렬로 (위치별 + worktree 요약 동시)
    with ThreadPoolExecutor(max_workers=MEASURE_WORKERS) as pool:
        worktree_future = None if is_worktree_skipped else pool.submit(_worktree_summary, roots, idle_hours, snapshot)
        rows = list(pool.map(lambda location: _location_row(location, max_seconds), catalog.locations()))
        worktree_summary = worktree_future.result() if worktree_future else None
    rows.sort(key=lambda row: -row["size_bytes"])
    report = {"free_space": sizes.free_space(), "locations": rows, "worktrees": worktree_summary,
              "docker": docker_cleanup.facts(),
              "running_builds": snapshot.is_running("xcodebuild", "XCBBuildService", "GradleDaemon", "flutter_tools"),
              "is_in_use_supported": snapshot.is_supported}
    # 폴더 일부만 정리되는 위치는 합계에서 제외
    countable = [row for row in rows if row["is_whole_folder_reclaimable"]]
    safe_gb = sum(row["size_gb"] or 0 for row in countable if row["tier"] == catalog.TIER_SAFE)
    decide_gb = sum(row["size_gb"] or 0 for row in countable if row["tier"] == catalog.TIER_DECIDE)
    report["totals_gb"] = {"safe": round(safe_gb, 2), "decide": round(decide_gb, 2),
                           "worktree_generated": (report["worktrees"] or {}).get("generated_output_gb")}
    report["seconds"] = round(time.monotonic() - started, 1)
    report["summary"] = (f"{report['free_space']['free_gb']} GB free ({report['free_space']['used_percent']}% used). "
                         f"Safe-tier caches {round(safe_gb, 1)} GB, decide-tier {round(decide_gb, 1)} GB")
    report["next"] = "show the user the three tiers; clear safe items after one confirmation, decide items only by name"
    return report
