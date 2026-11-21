"""Project type registry for scripts in user repos (#1244): .github/config/project-types.json (generated copy)
Source: src/core/project-types.json in projectops; copied with .github/config on every install or update."""
from __future__ import annotations

import json
from pathlib import Path

# <repo>/.github/config/project-types.json, next to this scripts folder
REGISTRY_PATH = Path(__file__).resolve().parent.parent / "config" / "project-types.json"
RESTORE_HINT = "run npx projectops to restore it"


class RegistryMissingError(RuntimeError):
    """The registry copy is missing or unreadable (config folder deleted or edited)"""


_cached_types: list[dict] | None = None


def load_project_types() -> list[dict]:
    """Registry entries in detection order (read once per process)"""
    global _cached_types
    if _cached_types is None:
        try:
            _cached_types = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise RegistryMissingError(
                f"registry missing: .github/config/project-types.json ({error.__class__.__name__}) — {RESTORE_HINT}") from error
    return _cached_types


def type_by_id(type_id: str) -> dict | None:
    return next((entry for entry in load_project_types() if entry["id"] == type_id), None)


def valid_type_ids() -> list[str]:
    return [entry["id"] for entry in load_project_types()]
