"""projectops version the running script belongs to — attached by failure responses · doctor (#863).

3-step lookup: plugin root version.yml > .claude-plugin/plugin.json > version folder in the path
Both repo checkouts and plugin caches (~/.claude/plugins/cache/<market>/projectops/<version>/) have version.yml at the root.
"""
from __future__ import annotations

import functools
import json
import re
from pathlib import Path

# Plugin root: <root>/skills/pro-launch/scripts/pro_launch/runtime/plugin_version.py
PLUGIN_ROOT_DEPTH = 5
UNKNOWN_VERSION = "unknown"
VERSION_LINE = re.compile(r'^version:\s*["\']?([0-9][^"\'\s#]*)', re.MULTILINE)
VERSION_FOLDER = re.compile(r"^\d+\.\d+\.\d+$")


@functools.lru_cache(maxsize=1)
def plugin_version() -> str:
    """Version string. 'unknown' if not found (computed once per process)."""
    here = Path(__file__).resolve()
    if len(here.parents) <= PLUGIN_ROOT_DEPTH:
        return UNKNOWN_VERSION
    plugin_root = here.parents[PLUGIN_ROOT_DEPTH]
    return (_from_version_yml(plugin_root) or _from_manifest(plugin_root)
            or _from_path(here) or UNKNOWN_VERSION)


def _from_version_yml(plugin_root: Path) -> str | None:
    try:
        match = VERSION_LINE.search((plugin_root / "version.yml").read_text(encoding="utf-8"))
    except OSError:
        return None
    return match.group(1) if match else None


def _from_manifest(plugin_root: Path) -> str | None:
    try:
        manifest = json.loads((plugin_root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    version = manifest.get("version") if isinstance(manifest, dict) else None
    return str(version) if version else None


def _from_path(here: Path) -> str | None:
    """Innermost x.y.z folder name in the path (installs with only the cache folder layout left)."""
    return next((part for part in reversed(here.parts) if VERSION_FOLDER.match(part)), None)


# Newer install notice {running, installed, use} — launch_cli sets it at startup and the first response takes it (#920)
_NEWER_INSTALLED: dict = {}


def set_newer_installed(info: dict | None) -> None:
    """Keep the launch_resolver.newer_installed_info result (does nothing for None)"""
    if info:
        _NEWER_INSTALLED["info"] = dict(info)


def take_newer_installed() -> dict | None:
    """Take the kept notice — once per process (None from the second call)"""
    return _NEWER_INSTALLED.pop("info", None)
