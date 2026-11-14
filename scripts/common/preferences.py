"""Merge per-person presentation settings (preferences).

If each skill invented its own keys, users could not learn them and docs would go stale. So there is one shape
and every skill reads it through this one function. It covers presentation only (language, tone, format); safety rules
like approval or dry-run cannot be turned off here; keys outside the allow list go to ignored, not values.
"""
from __future__ import annotations

import re
import subprocess
from typing import Optional

from common import config

COMMON_KEYS = ("language", "tone", "rules")
SKILL_KEYS = ("template", "preset", "examples", "sections")

# Allowed type per key. Silently using a wrong type breaks each skill differently, so block it at the entry.
_TYPES = {
    "language": str, "tone": str, "template": str, "preset": str,
    "rules": list, "examples": list, "sections": list,
}


def _as_dict(x: object) -> dict:
    """Treat a non-dict setting as an empty dict, so a hand-broken config falls back to defaults."""
    return x if isinstance(x, dict) else {}


# Skill name > old name (fallback to config key skills.<old name>; the new-name key wins if present)
PREVIOUS_SKILL_IDS = {"pro-code-consult": ("pro-architecture-consult",), "pro-ui-design": ("pro-design-brief",)}


def _skill_layer(skills: object, skill_id: str) -> tuple:
    """skills map > (settings layer, actual key): new name first, else old name (#912)"""
    skills = _as_dict(skills)
    for key in (skill_id, *PREVIOUS_SKILL_IDS.get(skill_id, ())):
        if key in skills:
            return skills[key], key
    return None, skill_id


# Key pairs that set the format. If a layer sets either one, the earlier layer's pair is dropped whole;
# otherwise a repo-layer preset always loses to the global template and "per-repo formats" are impossible.
FORMAT_KEYS = ("template", "preset")


def _valid(key: str, val: object, allowed: tuple) -> bool:
    typ = _TYPES.get(key)
    if key not in allowed or typ is None or not isinstance(val, typ):
        return False
    return not (typ is list and not all(isinstance(x, str) for x in val))


def _take(layer: object, allowed: tuple, label: str, values: dict, sources: dict, ignored: list) -> None:
    if not isinstance(layer, dict):
        return
    if any(k in FORMAT_KEYS and _valid(k, v, allowed) for k, v in layer.items()):
        for k in FORMAT_KEYS:
            values.pop(k, None)
            sources.pop(k, None)
    for key, val in layer.items():
        if not _valid(key, val, allowed):
            ignored.append(f"{label}.{key}")
            continue
        values[key] = val
        sources[key] = label


def _find_repo(data: dict, owner: Optional[str], repo: Optional[str]) -> Optional[dict]:
    if not owner or not repo:
        return None
    repos = _as_dict(data.get("github")).get("repos")
    if not isinstance(repos, list):
        return None
    for r in repos:
        if not isinstance(r, dict):
            continue
        # remote URL and config often differ in case (GitHub is case-insensitive)
        if str(r.get("owner", "")).lower() == owner.lower() and str(r.get("repo", "")).lower() == repo.lower():
            return r
    return None


def resolve(skill_id: str, owner: Optional[str] = None, repo: Optional[str] = None,
            data: Optional[dict] = None, *, load: bool = False) -> dict:
    """Overlay the layers in order and return the final values and their sources.

    Without data and with load=True, read the config file. Missing or broken file gives an empty result.
    config_status is "ok" · "missing" · "unreadable" ("ok" when data is passed directly).
    """
    status = "ok"
    if data is None and load:
        data, status = config.load_with_status()
    values: dict = {}
    sources: dict = {}
    ignored: list = []
    if not isinstance(data, dict):
        if data is None:
            status = "missing" if status == "ok" else status
        else:
            status = "unreadable"  # JSON whose top level is not an object is also an unreadable config
        return {"values": values, "sources": sources, "ignored": ignored, "config_status": status}

    skill_allowed = COMMON_KEYS + SKILL_KEYS
    _take(data.get("preferences"), COMMON_KEYS, "preferences", values, sources, ignored)
    layer, key = _skill_layer(data.get("skills"), skill_id)
    _take(layer, skill_allowed, f"skills.{key}", values, sources, ignored)

    entry = _find_repo(data, owner, repo)
    if entry is not None:
        tag = f"repos[{entry.get('owner')}/{entry.get('repo')}]"
        _take(entry.get("preferences"), COMMON_KEYS, f"{tag}.preferences", values, sources, ignored)
        layer, key = _skill_layer(entry.get("skills"), skill_id)
        _take(layer, skill_allowed, f"{tag}.skills.{key}", values, sources, ignored)
    return {"values": values, "sources": sources, "ignored": ignored, "config_status": status}


def is_legacy_commit_user(data: Optional[dict]) -> bool:
    """Whether this person has used pro-commit before: an approval setting (github.commit or repos[].commit) remains.

    Silently applying the new default (conventional) to them would change their commit format one day (spec S1).
    """
    gh = _as_dict(_as_dict(data).get("github"))
    if isinstance(gh.get("commit"), dict):
        return True
    repos = gh.get("repos")
    return isinstance(repos, list) and any(isinstance(r, dict) and isinstance(r.get("commit"), dict)
                                           for r in repos)


# Some forms carry a port, like ssh://git@github.com:22/o/r. A port is not an owner, so skip it
# (scp form git@github.com:1234/r has no two segments after it, so it is not mistaken for a port).
_REMOTE = re.compile(r"github\.com(?::\d+(?=/))?[:/]+([^/]+)/([^/]+?)(?:\.git)?/?$")


def detect_repo(cwd: Optional[str] = None) -> tuple:
    """Extract owner/repo from the origin remote. (None, None) if git or the remote is missing."""
    try:
        url = subprocess.run(["git", "remote", "get-url", "origin"], cwd=cwd,
                             capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None, None
    m = _REMOTE.search(url)
    return (m.group(1), m.group(2)) if m else (None, None)
