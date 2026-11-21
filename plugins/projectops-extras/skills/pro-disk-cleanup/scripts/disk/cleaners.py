"""Per-location cleanup: tool (tool command) · aged (subfolders older than N days) · browser (cache folders only). Plan only without --yes"""
from __future__ import annotations

import json
import os
import shutil
import re
import time
from pathlib import Path

from . import guard, shell, sizes
from .catalog import Location
from .processes import ProcessSnapshot

# Cache folder names inside a browser profile that can be deleted while keeping logins
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
    """Subfolders > {path, age_days, size_gb, skip_reason}. Age is read before sizing (keeps access times)"""
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
    # browser-profiles/<profile>/... or .../.browser-profile/...
    for ancestor in cache.parents:
        if ancestor.name == ".browser-profile":
            return ancestor
        if ancestor.parent.name == "browser-profiles":
            return ancestor
    return None

def _numeric_version(name: str) -> tuple[int, ...] | None:
    """Parse numeric versions; leave unrecognized names untouched."""
    if not re.fullmatch(r"\d+(?:\.\d+)*", name):
        return None

    parts = [int(part) for part in name.split(".")]
    while len(parts) > 1 and parts[-1] == 0:
        parts.pop()
    return tuple(parts)


def _real_subfolders(parent: Path) -> list[Path]:
    """List directories without following symbolic links."""
    if parent.is_symlink() or not parent.is_dir():
        return []

    return [
        child
        for child in parent.iterdir()
        if not child.is_symlink() and child.is_dir()
    ]


def _installed_plugin_paths() -> set[Path]:
    """installed_plugins.json installPath values > resolved paths (missing, unreadable or wrongly shaped file > empty set)"""
    config = Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude"))
    manifest = config / "plugins" / "installed_plugins.json"
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    # Valid JSON of another shape (array, string) falls back the same way
    plugins = data.get("plugins") if isinstance(data, dict) else None
    if not isinstance(plugins, dict):
        return set()
    paths = set()
    for entries in plugins.values():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            raw = (entry or {}).get("installPath") if isinstance(entry, dict) else None
            if raw:
                paths.add(Path(raw).resolve())
    return paths


def plugin_version_candidates(location: Location) -> list[dict]:
    """List cached versions, keeping the newest two per plugin."""
    candidates = []
    # An install pinned in installed_plugins.json stays even when it is older than the newest two (read once)
    installed = _installed_plugin_paths()

    for marketplace in _real_subfolders(location.path):
        for plugin in _real_subfolders(marketplace):
            versions = _real_subfolders(plugin)
            parsed = {
                folder: _numeric_version(folder.name)
                for folder in versions
            }

            recognized = [
                folder for folder in versions
                if parsed[folder] is not None
            ]
            recognized.sort(
                key=lambda folder: (parsed[folder], folder.name),
                reverse=True,
            )
            kept = set(recognized[:2])

            for folder in versions:
                if parsed[folder] is None:
                    skip_reason = "unknown_version"
                elif folder in kept:
                    skip_reason = "newest_two"
                elif folder.resolve() in installed:
                    skip_reason = "installed"
                else:
                    skip_reason = None

                byte_count, is_partial = sizes.folder_bytes(folder)
                candidates.append({
                    "path": str(folder),
                    "marketplace": marketplace.name,
                    "plugin": plugin.name,
                    "version": folder.name,
                    "size_bytes": byte_count or 0,
                    "size_gb": sizes.to_gigabytes(byte_count),
                    "is_partial_size": is_partial,
                    "skip_reason": skip_reason,
                })

    return sorted(candidates, key=lambda item: -item["size_bytes"])

def delete_candidates(candidates: list[dict], allowed_base: Path, is_confirmed: bool) -> dict:
    """Delete only candidates without skip_reason, through the gate > result summary"""
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
