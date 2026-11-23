"""Private registry lookup: project-blueprint section of ~/.projectops/config/config.json (owner only, optional)
Returns references only (names, kinds, script paths, whether an endpoint is set); never prints anything secret-shaped.
"""
from __future__ import annotations

import json
from pathlib import Path

CONFIG_PATH = Path.home() / ".projectops" / "config" / "config.json"
SECTION = "project-blueprint"
# Brain fields safe to echo: references and non-secret metadata (mcp_url is reported only as present or not)
BRAIN_FIELDS_SHOWN = ("engine", "kind", "server", "database_instance", "database", "sync_script", "mcp_server_name",
                      "token_cred", "notes")   # token_cred: credential store entry name, never the token


def load_section(config_path: Path = CONFIG_PATH) -> dict | None:
    """project-blueprint section, or None when the file or section is missing or unreadable (teammates have none)"""
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    section = data.get(SECTION) if isinstance(data, dict) else None
    return section if isinstance(section, dict) else None


def _normalize_path(value: str) -> str:
    # Forward slashes and lower case so Windows and macOS paths compare the same way
    return str(Path(value).expanduser()).replace("\\", "/").rstrip("/").lower()


def find_project(section: dict, remote_slug: str | None, repo_root: Path | None) -> tuple[str | None, dict | None]:
    """Match order: repos[].github == remote (case-insensitive) > local_path / worktree_path is the repo root or a parent"""
    projects = section.get("projects") if isinstance(section.get("projects"), dict) else {}
    if remote_slug:
        for key, entry in projects.items():
            for repo in entry.get("repos") or []:
                if str(repo.get("github", "")).lower() == remote_slug.lower():
                    return key, entry
    if repo_root:
        root = _normalize_path(str(repo_root))
        for key, entry in projects.items():
            for repo in entry.get("repos") or []:
                for field in ("local_path", "worktree_path"):
                    base = repo.get(field)
                    if base and (root == _normalize_path(base) or root.startswith(_normalize_path(base) + "/")):
                        return key, entry
    return None, None


def matching_repo(entry: dict, remote_slug: str | None) -> dict:
    for repo in entry.get("repos") or []:
        if remote_slug and str(repo.get("github", "")).lower() == remote_slug.lower():
            return repo
    repos = entry.get("repos") or []
    return repos[0] if repos else {}


def describe_sync_target(section: dict | None, project_key: str | None, entry: dict | None) -> dict:
    """Where the repo folder is synced from, as references only; known=false when this machine has no registry entry"""
    if section is None:
        return {"known": False, "reason": "no private registry on this machine"}
    if not entry:
        return {"known": False, "reason": "this repo is not in the private registry"}
    knowledge = entry.get("knowledge") if isinstance(entry.get("knowledge"), dict) else {}
    brain_name = knowledge.get("brain")
    if not brain_name:
        return {"known": False, "reason": f"registry entry '{project_key}' names no brain (projects.{project_key}.knowledge.brain)"}
    brains = (section.get("infra") or {}).get("brains") or {}
    brain = brains.get(brain_name)
    if not isinstance(brain, dict):
        return {"known": False, "reason": f"brain '{brain_name}' is not defined in infra.brains"}
    shown = {field: brain[field] for field in BRAIN_FIELDS_SHOWN if brain.get(field) not in (None, "")}
    return {
        "known": True,
        "brain": brain_name,
        **shown,
        "has_mcp_url": bool(brain.get("mcp_url")),
        "source_id": knowledge.get("source_id") or f"{project_key}-knowledge",
        "sync": knowledge.get("sync") or "repo-commit",
        "registry_intent": {key: knowledge[key] for key in ("enabled", "path") if key in knowledge},
    }
