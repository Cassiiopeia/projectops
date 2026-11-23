"""
Reads and writes the user config (`~/.projectops/config/config.json`).

config is one global file, namespaced by skill_id as top-level keys.
e.g. config["github"]["global_pat"], config["launch"]["credentials"]

See skills/references/config-rules.md and skills/config.json.example for the full schema.
"""

import json
import shutil
from pathlib import Path
from typing import Any, Optional


def config_path() -> Path:
    """
    Return the path of the single global config file (`~/.projectops/config/config.json`).

    The #459 namespace neutralization moved the config home from `~/.suh-template` to `~/.projectops`.
    If an existing user's config is only at the old path, copy it to the new path once on first access
    (the old file is kept for rollback — lossless migration).
    """
    new = Path.home() / ".projectops" / "config" / "config.json"
    old = Path.home() / ".suh-template" / "config" / "config.json"
    if not new.exists() and old.exists():
        new.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(old, new)
    return new


def load_with_status() -> tuple:
    """(data, status). status is "ok", "missing" or "unreadable".

    Missing and broken must differ so the user can be told "your settings are being ignored".
    """
    path = config_path()
    if not path.exists():
        return None, "missing"
    try:
        # A BOM added by Windows Notepad breaks json — utf-8-sig reads fine with or without a BOM
        return json.loads(path.read_text(encoding="utf-8-sig")), "ok"
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None, "unreadable"


def load() -> Optional[dict]:
    """Read the whole config.json as a dict. None if the file is missing or broken."""
    return load_with_status()[0]


def get_section(skill_id: str) -> Optional[dict]:
    """Return one skill_id section (e.g. config["github"]). None if absent."""
    data = load()
    if not isinstance(data, dict):
        return None
    section = data.get(skill_id)
    return section if isinstance(section, dict) else None


def get_github_pat(owner: Optional[str] = None, repo: Optional[str] = None) -> Optional[str]:
    """
    Resolve the GitHub PAT from config.

    Priority (config-rules.md §3):
      1. If owner/repo are given, the pat (non-null) of the matching entry in the repos array
      2. Otherwise global_pat
      3. Otherwise the credential store entry named by global_pat_cred (config-rules.md §9)
    None if no PAT is found.
    """
    section = get_section("github")
    if not section:
        return None

    # 1. Per-repo PAT first
    if owner and repo:
        for r in section.get("repos", []) or []:
            if r.get("owner") == owner and r.get("repo") == repo and r.get("pat"):
                return r["pat"]

    # 2. Fall back to the shared global_pat
    if section.get("global_pat"):
        return section["global_pat"]

    # 3. Migrated PAT: reference by name into the credential store
    return _read_referenced_pat(section.get("global_pat_cred"))


def _read_referenced_pat(cred_name: Optional[str]) -> Optional[str]:
    """github.global_pat_cred > credential store token (None when unset, missing or unreadable)"""
    if not cred_name:
        return None
    from common.credentials import CredentialError, read_secret
    try:
        return read_secret(cred_name, "token")
    except CredentialError:
        return None


def save(data: dict) -> Path:
    """
    Save the whole config.json and return its path.

    Note: for partial edits, always load() the whole file and merge before calling
    (so other sections are not wiped).
    """
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
