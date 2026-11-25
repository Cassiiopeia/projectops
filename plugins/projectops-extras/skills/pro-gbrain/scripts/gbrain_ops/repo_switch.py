"""Repo switch facts read through pro-brain (same plugin): team brain key, team write mode, branches.
One reader for both skills, so the project key and the write mode never differ between pro-brain and pro-gbrain.
"""
from __future__ import annotations

import sys
from pathlib import Path

from . import common
from .pro_brain import pro_brain_scripts_directory

WRITE_MODES = ("sync", "direct")
DEFAULT_WRITE_MODE = "sync"   # existing team setups were all sync (members read, a sync host imports knowledge/)


def _repo_facts_module():
    sys.path.insert(0, str(pro_brain_scripts_directory()))
    from brain import repo_facts  # noqa: E402
    return repo_facts


def read(repo_root: Path) -> dict:
    """{switch, team_key, write_mode, default_branch, development_branch}; empty facts when version.yml is unreadable"""
    try:
        repo_facts = _repo_facts_module()
        text = repo_facts.read_version_yml_text(repo_root)
        switch = repo_facts.read_knowledge_switch(text)
        version_facts = repo_facts.read_version_facts(text)
    except (common.StepError, ImportError, OSError, ValueError):
        return {"switch": {}, "team_key": None, "write_mode": None, "default_branch": None, "development_branch": None}
    # Guarded: an older pro-brain copy may not ship the shared key reader yet
    key_reader = getattr(repo_facts, "team_brain_project_key", None)
    raw_key = key_reader(switch) if key_reader else None
    team = switch.get("team_brain") if isinstance(switch.get("team_brain"), dict) else {}
    write_mode = team.get("write") if team.get("write") in WRITE_MODES else (DEFAULT_WRITE_MODE if team else None)
    return {"switch": switch, "team_key": raw_key, "team_key_valid": common.to_project_key(raw_key) == raw_key if raw_key else None,
            "write_mode": write_mode, "default_branch": version_facts.get("default_branch"),
            "development_branch": version_facts.get("development_branch")}


def rule_file_branch(repo_root: Path, default_branch: str, development_branch: str | None) -> dict:
    """Branch a teammate pulls to get the pro-brain rule (rules file or CLAUDE.md block): default branch first"""
    candidates = [branch for branch in (default_branch, development_branch) if branch]
    for branch in dict.fromkeys(candidates):
        for relative in (".claude/rules/pro-brain.md", "CLAUDE.md", ".claude/CLAUDE.md"):
            exit_code, output = common.run(["git", "-C", str(repo_root), "show", f"origin/{branch}:{relative}"])
            if exit_code == 0 and ("pro-brain:begin" in output or relative.endswith("pro-brain.md")):
                return {"branch": branch, "file": relative}
    return {"branch": None, "file": None}
