"""Release context: collect app review signals, read config (read-only), look up the app_release record.

detect-release-context (signal report) and create-pr (app review approval gate, #970) share the same judgement.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from common.project_types import app_type_ids

# Workflow file name keywords that lead straight to app store review (case-insensitive substring match).
# For a new store or platform, adding a keyword here extends detection (no change to SKILL.md or decision logic).
_STORE_WORKFLOW_KEYWORDS = ("PLAYSTORE", "TESTFLIGHT", "APPSTORE", "APP-STORE")
# Project types with a strong app (store release) nature: registry is_app (#1244)
_APP_PROJECT_TYPES = app_type_ids()
# Hints that count as app review signals
APP_SIGNAL_HINTS = ("strong_app", "app_release_likely")


def _read_project_types(project_root: Path) -> list[str]:
    """Extract the project_types array from version.yml (regex, no yaml dependency).

    Offline / standard-library-first: does not import PyYAML; parses the `project_types: [...]` line
    as a string. Returns an empty list if the file or key is missing (not an error)."""
    vy = project_root / "version.yml"
    if not vy.exists():
        return []
    try:
        text = vy.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    # Find the one-line `project_types: ["spring", "react"]` form and extract tokens inside quotes.
    m = re.search(r"^\s*project_types\s*:\s*\[([^\]]*)\]", text, re.MULTILINE)
    if m:
        return [t.strip().strip("\"'") for t in m.group(1).split(",") if t.strip()]
    # Fallback for the singular non-array `project_type: "flutter"`.
    m2 = re.search(r"^\s*project_type\s*:\s*[\"']?([A-Za-z0-9_-]+)", text, re.MULTILINE)
    return [m2.group(1)] if m2 else []


def _scan_store_workflows(project_root: Path) -> list[str]:
    """Scan file names in .github/workflows and return store review workflow file names."""
    wf_dir = project_root / ".github" / "workflows"
    if not wf_dir.is_dir():
        return []
    found = []
    try:
        for entry in sorted(os.listdir(wf_dir)):
            upper = entry.upper()
            if any(kw in upper for kw in _STORE_WORKFLOW_KEYWORDS):
                found.append(entry)
    except OSError:
        return []
    return found


def collect_app_signals(project_root: Path) -> tuple[dict, str]:
    """(signals, hint). hint: strong_app | app_release_likely | backend_only | unknown (no signals)"""
    project_types = _read_project_types(project_root)
    store_workflows = _scan_store_workflows(project_root)
    has_store_workflow = bool(store_workflows)
    has_app_type = any(t.lower() in _APP_PROJECT_TYPES for t in project_types)
    # If neither version.yml nor workflows could be read, it is the signal-less unknown state.
    no_signals = not project_types and not (project_root / ".github" / "workflows").is_dir()

    if no_signals:
        hint = "unknown"
    elif has_store_workflow and has_app_type:
        hint = "strong_app"          # app type + store workflow → app review almost certain
    elif has_store_workflow:
        hint = "app_release_likely"  # store workflow exists but type signal is weak
    elif has_app_type:
        hint = "app_release_likely"  # app type exists but no store workflow found (TEST builds only etc.)
    else:
        hint = "backend_only"        # no app signal at all → treated as backend
    signals = {
        "project_types": project_types,
        "store_workflows": store_workflows,
        "has_store_workflow": has_store_workflow,
        "has_app_type": has_app_type,
    }
    return signals, hint


def load_config(config_arg: str | None) -> dict | None:
    """Open config.json read-only. Without a path, uses the same fixed path as PAT auto-load.

    The CLI reading config follows the PAT auto-load precedent (common.config) — it never writes.
    Python resolves the path with Path.home() itself, so there is no Windows Git Bash `$HOME` path issue."""
    if config_arg:
        path = Path(config_arg).expanduser()
    else:
        from common.config import config_path
        path = config_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def read_app_release(config: dict | None, owner: str, repo: str) -> bool | None:
    """Per-repo changelog_deploy.app_release (true · false · None if absent). No global default (config.md §4)"""
    github_section = (config or {}).get("github") if isinstance(config, dict) else None
    if not isinstance(github_section, dict):
        return None
    for repo_entry in github_section.get("repos", []) or []:
        if isinstance(repo_entry, dict) and repo_entry.get("owner") == owner and repo_entry.get("repo") == repo:
            changelog_deploy = repo_entry.get("changelog_deploy")
            value = changelog_deploy.get("app_release") if isinstance(changelog_deploy, dict) else None
            return value if isinstance(value, bool) else None
    return None
