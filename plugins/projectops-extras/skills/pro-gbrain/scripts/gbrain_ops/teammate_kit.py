"""Teammate kit: one private message covering everything a member needs to join a team brain.
Parts 5: key (this file only) > store it > connect (pro-brain) > pull the branch with the rule > verify after restart.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from . import common, context, repo_switch

SHARE_FOLDER_NAME = "share"
CLI = "python3 ~/.projectops/bin/projectops_cli.py"


def _rule_branch(repo_root: Path) -> dict:
    """Where the pro-brain rule is tracked (default branch first, else the development branch); unknown outside a repo"""
    try:
        root = context.find_repo_root(repo_root)
    except common.StepError:
        return {"branch": None, "file": None}
    facts = repo_switch.read(root)
    default_branch = facts.get("default_branch") or context.read_default_branch(root)
    return repo_switch.rule_file_branch(root, default_branch, facts.get("development_branch"))


def build(project: str, member: str, issued: dict, scope: str, write_mode: str, repo_root: Path) -> dict:
    """Kit text (holds the key) + the parts list and rule branch for the JSON output (no key)"""
    name = issued.get("mcp_server_name") or f"gbrain-{project}"
    rule = _rule_branch(repo_root)
    access = "read and write" if scope == "read_write" else "read-only"
    what_pro_brain_does = (
        "When an issue is finished, /pro-brain writes one note straight into the team brain (nothing to commit)."
        if write_mode == "direct" else
        "When an issue is finished, /pro-brain writes one note into knowledge/ and you commit it; the sync machine imports it.")
    pull_line = (f"   git fetch origin; git checkout {rule['branch']}; git pull   (the rule lives in {rule['file']})"
                 if rule["branch"] else
                 "   pull the branch that has the pro-brain rule (ask who set it up; it is not on the default branch yet)")
    lines = [
        f"{member}, here is your {access} key for the {project} team brain.",
        "Do not paste this message or the key into a chat or an AI assistant; ask for a new key if it leaks.",
        "",
        f"   key: {issued.get('secret')}",
        "",
        "1. Install the projectops-extras plugin if you do not have it:",
        "   claude plugin install projectops-extras@projectops-marketplace --scope user",
        "2. Store the key (pick one):",
        f"   in a terminal (hidden input): {CLI} launch cred set --name {name} --secret-field token --prompt",
        f"   or save only the key to a file, then: {CLI} launch cred set --name {name} --secret-field token --from-file FILE --delete-after",
        "3. Get the project rule so your agent knows when to write notes:",
        pull_line,
        "4. Open the project repo in Claude Code and say: /pro-brain connect the team brain",
        f"   (adds the MCP server {name} -> {issued.get('mcp_url')} for your user only)",
        "5. Restart Claude Code, then check that it reads and writes: /pro-brain doctor --to team",
        "",
        what_pro_brain_does,
    ]
    parts = ["key (this file only)", "store the key", "pull the rule branch", "connect with /pro-brain", "verify after restart"]
    return {"text": "\n".join(lines) + "\n", "parts": parts, "rule_branch": rule}


def write_private(project: str, member: str, text: str) -> Path:
    # Member name is free text: keep it out of the path shape (no separators or dots)
    safe_member = re.sub(r"[^A-Za-z0-9_-]+", "-", member).strip("-") or "member"
    path = common.state_directory() / SHARE_FOLDER_NAME / f"{project}-{safe_member}-{common.compact_timestamp()}.txt"
    common.ensure_private_directory(path.parent)
    # Created 600 from the first byte (the file holds the key)
    file_descriptor = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, common.PRIVATE_FILE_MODE)
    with os.fdopen(file_descriptor, "w", encoding="utf-8") as handle:
        handle.write(text)
    os.chmod(path, common.PRIVATE_FILE_MODE)
    return path
