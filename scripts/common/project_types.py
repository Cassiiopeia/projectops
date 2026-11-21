"""Project type registry for skills (#1244): scripts/common/project_types.json, a generated copy of src/core/project-types.json
Regenerate with node scripts/build_project_types.mjs; never edit the copy by hand."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

REGISTRY_PATH = Path(__file__).resolve().parent / "project_types.json"


@lru_cache(maxsize=1)
def load_project_types() -> tuple[dict, ...]:
    """Registry entries in detection order"""
    return tuple(json.loads(REGISTRY_PATH.read_text(encoding="utf-8")))


def app_type_ids() -> tuple[str, ...]:
    """Types released through app stores (is_app)"""
    return tuple(entry["id"] for entry in load_project_types() if entry["is_app"])


def launch_kinds_by_type() -> dict[str, list[str]]:
    """Type id > what pro-launch can start for it (app, web, server)"""
    return {entry["id"]: list(entry["launch_kinds"]) for entry in load_project_types()}
