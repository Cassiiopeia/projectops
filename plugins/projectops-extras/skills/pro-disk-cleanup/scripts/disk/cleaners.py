"""위치별 정리: tool (도구 명령) · aged (N일 지난 하위 폴더) · browser (캐시 폴더만). --yes 없으면 계획만"""
from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

from . import guard, shell, sizes
from .catalog import Location
from .processes import ProcessSnapshot

# 브라우저 프로필 안에서 지워도 로그인이 남는 캐시 폴더 이름
BROWSER_CACHE_NAMES = frozenset({
    "Cache", "Code Cache", "GPUCache", "DawnCache", "DawnGraphiteCache", "DawnWebGPUCache", "GrShaderCache",
    "GraphiteDawnCache", "ShaderCache", "component_crx_cache", "CacheStorage", "ScriptCache",
})
BROWSER_PROFILE_MARKERS = ("browser-profiles", ".browser-profile")


def run_tool(location: Location, is_confirmed: bool) -> dict:
    executable = shutil.which(location.tool_command[0])
    if not executable:
        return {"ok": False, "code": "tool_missing", "summary": f"`{location.tool_command[0]}` is not installed"}
    command = [executable, *location.tool_command[1:]]
    if not is_confirmed:
        return {"ok": True, "code": "dry_run", "command": " ".join(location.tool_command),
                "summary": "Nothing run. Re-run with --yes", "next": f"tool {location.key} --yes"}
    free_before = sizes.free_bytes()
    code, out, error = shell.run(command, timeout_seconds=1800)
    return {"ok": code == 0, "code": "cleaned" if code == 0 else "tool_failed", "command": " ".join(location.tool_command),
            "output_tail": (out + error)[-600:], "freed_gb": sizes.to_gigabytes(max(sizes.free_bytes() - free_before, 0)),
            "summary": "Tool clean-up finished" if code == 0 else "The tool reported an error; see output_tail"}


def aged_candidates(location: Location, older_than_days: float, snapshot: ProcessSnapshot) -> list[dict]:
    """하위 폴더 > {path, age_days, size_gb, skip_reason}. 나이는 크기 재기 전에 (접근 시각 보존)"""
    if not location.path.is_dir():
        return []
    candidates = []
    with os.scandir(location.path) as entries:
        children = [Path(entry.path) for entry in entries if not entry.is_symlink()]
    for child in children:
        touched = sizes.newest_touch_seconds(child)
        age = sizes.age_days(touched)
        users = snapshot.users_of(child)
        skip_reason = "in_use" if users else ("too_recent" if age is None or age < older_than_days else None)
        byte_count, is_partial = sizes.folder_bytes(child) if child.is_dir() else (child.stat().st_size, False)
        candidates.append({"path": str(child), "age_days": age, "size_gb": sizes.to_gigabytes(byte_count),
                           "size_bytes": byte_count or 0, "is_partial_size": is_partial, "skip_reason": skip_reason})
    return sorted(candidates, key=lambda item: -item["size_bytes"])


def browser_candidates(location: Location, snapshot: ProcessSnapshot) -> list[dict]:
    candidates = []
    for folder, child_folders, _ in os.walk(location.path):
        cache_names = [name for name in child_folders if name in BROWSER_CACHE_NAMES]
        child_folders[:] = [name for name in child_folders if name not in BROWSER_CACHE_NAMES]
        for name in cache_names:
            cache = Path(folder) / name
            profile = _profile_root(cache)
            users = snapshot.users_of(profile) if profile else None
            byte_count, is_partial = sizes.folder_bytes(cache)
            candidates.append({"path": str(cache), "profile": str(profile) if profile else None,
                               "size_gb": sizes.to_gigabytes(byte_count), "size_bytes": byte_count or 0,
                               "is_partial_size": is_partial,
                               "skip_reason": "browser_running" if users else ("unknown_profile" if profile is None else None)})
    return sorted(candidates, key=lambda item: -item["size_bytes"])


def _profile_root(cache: Path) -> Path | None:
    # browser-profiles/<프로필>/... 또는 .../.browser-profile/...
    for ancestor in cache.parents:
        if ancestor.name == ".browser-profile":
            return ancestor
        if ancestor.parent.name == "browser-profiles":
            return ancestor
    return None


def delete_candidates(candidates: list[dict], allowed_base: Path, is_confirmed: bool) -> dict:
    """skip_reason 없는 후보만 게이트 거쳐 삭제 > 결과 요약"""
    chosen = [item for item in candidates if not item["skip_reason"]]
    skipped = [item for item in candidates if item["skip_reason"]]
    planned_gb = sizes.to_gigabytes(sum(item["size_bytes"] for item in chosen))
    if not is_confirmed:
        return {"ok": True, "code": "dry_run", "planned": chosen, "skipped": skipped, "planned_gb": planned_gb,
                "summary": f"{len(chosen)} items ({planned_gb} GB) would be removed, {len(skipped)} kept. Re-run with --yes"}
    free_before = sizes.free_bytes()
    started = time.monotonic()
    results = [guard.remove_tree(item["path"], allowed_base) for item in chosen]
    refused = [result for result in results if not result["removed"]]
    return {"ok": not refused, "code": "cleaned" if not refused else "partially_cleaned",
            "removed_count": len(results) - len(refused), "refused": refused, "skipped": skipped,
            "freed_gb": sizes.to_gigabytes(max(sizes.free_bytes() - free_before, 0)),
            "seconds": round(time.monotonic() - started, 1),
            "summary": f"Removed {len(results) - len(refused)} of {len(chosen)}; kept {len(skipped)}"}
