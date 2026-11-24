"""Private registry (project-blueprint section of ~/.projectops/config/config.json): read references, write team brain
entries with a backup first. Owner-specific values (hosts, credential names) live only here, never in a repo.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from . import common, credentials
from .pro_brain import pro_brain_scripts_directory

SECTION = "project-blueprint"
# infra.brains.<name>.kind for a brain server that can create team brains (its `provisioner` block holds references)
PROVISIONER_KIND = "provisioner"
TEAM_BRAIN_SUFFIX = "-team"


def _pro_brain_registry():
    # Same plugin ships pro-brain next to pro-gbrain: reuse its project matcher instead of a second copy
    sys.path.insert(0, str(pro_brain_scripts_directory()))
    from brain import registry  # noqa: E402
    return registry


def load_config() -> dict | None:
    data, status = credentials.load_config()
    if status == "unreadable":
        raise common.StepError("config_unreadable", "config.json exists but cannot be read; nothing was changed",
                               "fix the JSON in ~/.projectops/config/config.json by hand")
    return data


def load_section() -> dict | None:
    data = load_config()
    section = (data or {}).get(SECTION)
    return section if isinstance(section, dict) else None


def brains(section: dict | None) -> dict:
    found = ((section or {}).get("infra") or {}).get("brains")
    return found if isinstance(found, dict) else {}


def find_provisioner(section: dict | None, name: str | None = None) -> tuple[str | None, dict | None]:
    """(name, provisioner block) of the configured brain server, or (None, None) for teams without one"""
    for brain_name, brain in brains(section).items():
        if not isinstance(brain, dict) or brain.get("kind") != PROVISIONER_KIND:
            continue
        if name and brain_name != name:
            continue
        block = brain.get("provisioner")
        if isinstance(block, dict):
            return brain_name, block
    return None, None


def find_project(section: dict | None, remote_slug: str | None, repo_root: Path | None) -> tuple[str | None, dict | None]:
    if not section:
        return None, None
    return _pro_brain_registry().find_project(section, remote_slug, repo_root)


def team_brain_name(project: str) -> str:
    return project + TEAM_BRAIN_SUFFIX


def plan_entries(section: dict | None, project: str, brain_entry: dict, knowledge_entry: dict) -> dict:
    """What would change: added keys and conflicts (an existing different value is reported, never overwritten)"""
    name = team_brain_name(project)
    existing_brain = brains(section).get(name) if section else None
    existing_project = (((section or {}).get("projects") or {}).get(project) or {})
    existing_knowledge = existing_project.get("knowledge") if isinstance(existing_project.get("knowledge"), dict) else {}
    return {
        "brain_name": name,
        "brain": _diff(existing_brain if isinstance(existing_brain, dict) else {}, brain_entry),
        "knowledge": _diff(existing_knowledge, knowledge_entry),
        "project_known": bool(existing_project),
    }


def _diff(existing: dict, wanted: dict) -> dict:
    added = {key: value for key, value in wanted.items() if key not in existing}
    conflicts = {key: {"registry": existing[key], "wanted": value} for key, value in wanted.items()
                 if key in existing and existing[key] != value}
    return {"added": added, "conflicts": conflicts}


def apply_entries(project: str, brain_entry: dict, knowledge_entry: dict) -> dict:
    """Back up config.json (600), then add missing keys only; existing values stay as they are"""
    data = load_config() or {}
    backup_path = None
    config_file = credentials.config_path()
    if config_file.exists():
        backup_path = config_file.with_name(f"{config_file.name}.bak-pro-gbrain-{common.compact_timestamp()}")
        shutil.copyfile(config_file, backup_path)
        backup_path.chmod(common.PRIVATE_FILE_MODE)
    section = data.setdefault(SECTION, {})
    infra_brains = section.setdefault("infra", {}).setdefault("brains", {})
    brain = infra_brains.setdefault(team_brain_name(project), {})
    project_entry = section.setdefault("projects", {}).setdefault(project, {})
    knowledge = project_entry.setdefault("knowledge", {})
    added = {"brain": [key for key in brain_entry if key not in brain],
             "knowledge": [key for key in knowledge_entry if key not in knowledge]}
    for key, value in brain_entry.items():
        brain.setdefault(key, value)
    for key, value in knowledge_entry.items():
        knowledge.setdefault(key, value)
    if added["brain"] or added["knowledge"]:
        credentials.write_config_atomic(data)
    elif backup_path is not None:
        backup_path.unlink()   # nothing changed: a backup would only pile up
        backup_path = None
    return {"added": added, "backup": str(backup_path) if backup_path else None}


def mark_removed(project: str) -> dict:
    """remove: flag the team brain entry as detached (status: removed); never deletes a key"""
    data = load_config() or {}
    brain = brains(data.get(SECTION)).get(team_brain_name(project))
    if not isinstance(brain, dict):
        return {"changed": False}
    config_file = credentials.config_path()
    backup_path = config_file.with_name(f"{config_file.name}.bak-pro-gbrain-{common.compact_timestamp()}")
    shutil.copyfile(config_file, backup_path)
    backup_path.chmod(common.PRIVATE_FILE_MODE)
    brain["status"] = "removed"
    brain["removed_at"] = common.timestamp()
    credentials.write_config_atomic(data)
    return {"changed": True, "backup": str(backup_path)}


def read_admin_key(provisioner: dict) -> str:
    """Admin key of the brain server, from the credential store entry the registry names (for code only)"""
    name = provisioner.get("credential")
    field = provisioner.get("credential_field") or "token"
    if not name:
        raise common.StepError("provisioner_credential_missing", "the provisioner names no credential",
                               "add provisioner.credential (a credential store entry name) to the registry")
    try:
        return credentials.read_secret(name, field)
    except credentials.CredentialError as error:
        raise common.StepError("provisioner_credential_missing", error.message,
                               f"store it in a terminal: python3 ~/.projectops/bin/projectops_cli.py launch cred set --name {name} --secret-field {field} --prompt")


def describe_brain_entries(section: dict | None) -> list[dict]:
    """status: every team brain in the registry, references only (no URL credentials exist here by design)"""
    rows = []
    for name, brain in brains(section).items():
        if not isinstance(brain, dict) or brain.get("kind") != "team":
            continue
        rows.append({"name": name, **{key: brain.get(key) for key in (
            "database", "mcp_server_name", "service", "port", "sync_script", "provisioned_by", "status") if brain.get(key) is not None},
            "has_mcp_url": bool(brain.get("mcp_url"))})
    return rows


def dump(value) -> str:
    return json.dumps(value, ensure_ascii=False)
