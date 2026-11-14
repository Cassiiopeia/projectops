"""Settings: image section of ~/.projectops/config/config.json (defaults if missing) + repo location"""
from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path

CONFIG_SECTION = "image"
# Repo harness location (relative to repo root)
DEFAULT_HARNESS_DIR = "docs/image-harness"
# Candidate image storage: ~/.projectops/image/{owner__repo}/runs/{yyyyMMdd_HHmmss}_{name}
RUNS_PARTS = (".projectops", "image")


def _section() -> dict:
    path = Path.home() / ".projectops" / "config" / "config.json"
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    section = loaded.get(CONFIG_SECTION) if isinstance(loaded, dict) else None
    return section if isinstance(section, dict) else {}


def configured_providers() -> dict:
    providers = _section().get("providers")
    return providers if isinstance(providers, dict) else {}


def configured_priority() -> list[str] | None:
    """image.priority (user-chosen tool order), None if unset > ask the user on first use"""
    priority = _section().get("priority")
    if isinstance(priority, list) and priority and all(isinstance(item, str) for item in priority):
        return list(priority)
    return None


def is_subscription_required() -> bool:
    # require_subscription: default true; only an explicit false allows Codex API-key login
    return _section().get("require_subscription") is not False


def _git(*arguments: str) -> str:
    try:
        completed = subprocess.run(["git", *arguments], capture_output=True, encoding="utf-8", errors="replace",
                                   timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return completed.stdout.strip() if completed.returncode == 0 else ""


def repository_root() -> Path:
    top_level = _git("rev-parse", "--show-toplevel")
    return Path(top_level) if top_level else Path.cwd()


def repository_key(root: Path) -> str:
    """origin URL > owner__repo, or the folder name if none (separates candidate folders per project)"""
    origin = _git("-C", str(root), "remote", "get-url", "origin")
    matched = re.search(r"[:/]([^/:]+)/([^/]+?)(?:\.git)?/?$", origin)
    if matched:
        return f"{matched.group(1)}__{matched.group(2)}"
    return root.name or "workspace"


def harness_dir(root: Path) -> Path:
    configured = _section().get("harness_dir")
    relative = str(configured) if isinstance(configured, str) and configured.strip() else DEFAULT_HARNESS_DIR
    return (root / relative).resolve()


def new_run_dir(root: Path, name: str) -> Path:
    stamp = time.strftime("%Y%m%d_%H%M%S")
    return Path.home().joinpath(*RUNS_PARTS, repository_key(root), "runs", f"{stamp}_{name}")
