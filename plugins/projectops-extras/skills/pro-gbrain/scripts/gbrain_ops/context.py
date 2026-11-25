"""Situation detection for add: repo, project key, default branch, the user's own brain, a configured provisioner,
and the single question (solo or team) with a recommended answer. Read only; engine fields only, never a database URL.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import common, registry_store, repo_switch

MODES = ("repo-only", "own", "team")
# Distinct commit authors above which the repo counts as a team repo (bots excluded by name)
TEAM_AUTHOR_THRESHOLD = 1
BOT_AUTHOR_MARKERS = ("[bot]", "github-actions", "dependabot", "renovate")


def git(repo_root: Path, *arguments: str) -> str:
    exit_code, output = common.run(["git", "-C", str(repo_root), *arguments])
    return output.strip() if exit_code == 0 else ""


def find_repo_root(start: Path) -> Path:
    root = git(start, "rev-parse", "--show-toplevel")
    if not root:
        raise common.StepError("not_a_repo", f"{start} is not inside a git repository",
                               "run inside the project repository or pass --repo")
    return Path(root)


def read_remote(repo_root: Path) -> tuple[str | None, str | None]:
    """(clone URL without credentials, owner/repo slug)"""
    url = git(repo_root, "config", "--get", "remote.origin.url")
    if not url:
        return None, None
    from .local_sync import strip_url_credentials
    clean = strip_url_credentials(url)
    slug = clean.rstrip("/").removesuffix(".git").replace(":", "/").split("/")[-2:]
    return clean, "/".join(slug) if len(slug) == 2 else None


def read_default_branch(repo_root: Path) -> str:
    head = git(repo_root, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    if head.startswith("origin/"):
        return head.split("/", 1)[1]
    for candidate in ("main", "master"):
        if git(repo_root, "rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{candidate}"):
            return candidate
    return "main"


def count_human_authors(repo_root: Path) -> int:
    names = {line.strip().lower() for line in git(repo_root, "log", "--format=%an", "-n", "500").splitlines() if line.strip()}
    return len([name for name in names if not any(marker in name for marker in BOT_AUTHOR_MARKERS)])


def detect_own_brain() -> dict:
    """The user's personal gbrain on this machine: installed? engine? (engine fields only)"""
    exit_code, version = common.run(["gbrain", "--version"], env=common.gbrain_environment())
    if exit_code != 0:
        return {"installed": False}
    from . import runtime
    status = runtime.engine()
    engine = status.get("effective_engine")
    kind = "thin-client" if status.get("thin_client") else ("local" if engine == "pglite" else "postgres" if engine == "postgres" else "uninitialized")
    return {"installed": True, "version": version.strip().split()[-1] if version.strip() else None,
            "engine": engine, "kind": kind, "engine_status": status,
            "connection": "not_probed"}



def detect(repo_path: Path, project_override: str | None = None) -> dict:
    repo_root = find_repo_root(repo_path)
    remote_url, remote_slug = read_remote(repo_root)
    section = registry_store.load_section()
    registry_key, registry_entry = registry_store.find_project(section, remote_slug, repo_root)
    switch_facts = repo_switch.read(repo_root)
    # Key priority: flag > the repo's team brain (version.yml) > registry > folder name, so pro-brain and pro-gbrain agree
    switch_key = switch_facts["team_key"] if switch_facts.get("team_key_valid") else None
    project = project_override or switch_key or registry_key or common.to_project_key(repo_root.name)
    project_from = ("flag" if project_override else "version.yml team_brain" if switch_key else
                    "registry" if registry_key else "folder name")
    provisioner_name, provisioner_block = registry_store.find_provisioner(section)
    own_brain = detect_own_brain()
    authors = count_human_authors(repo_root)
    team_entry = registry_store.brains(section).get(registry_store.team_brain_name(project)) if project else None
    recommended, why = recommend_mode(provisioner_block is not None, own_brain, authors, bool(team_entry))
    return {
        "repo_root": str(repo_root), "remote_slug": remote_slug, "remote_url": remote_url,
        "default_branch": read_default_branch(repo_root),
        "project": project, "project_from": project_from,
        "team_brain_key_in_switch": switch_facts["team_key"], "team_write": switch_facts["write_mode"],
        "has_registry": section is not None, "registry_project_known": bool(registry_entry),
        "team_brain_in_registry": bool(team_entry),
        "provisioner": {"name": provisioner_name, "type": provisioner_block.get("type"),
                        "supports_dry_run": bool(provisioner_block.get("supports_dry_run"))} if provisioner_block else None,
        "provisioner_hint": None if provisioner_block else provisioner_hint(),
        "own_brain": own_brain, "human_authors": authors,
        "question": {
            "text": "Will you use this brain alone, or with your team?",
            "options": [
                {"mode": "team", "label": "With my team", "means": "a team brain on the brain server shared by the team (then: do members write directly or through the repo?)"},
                {"mode": "own", "label": "Alone, in my own GBrain", "means": "this repo's notes become one source in your personal brain"},
                {"mode": "repo-only", "label": "Notes in the repo only", "means": "no brain; notes stay in the knowledge folder"},
            ],
            "recommended": recommended, "why": why,
        },
        # Asked right after a team answer: the team model decides the steps, the token scope and what verify expects
        "team_write_question": team_write_question(switch_facts["write_mode"]),
    }


def team_write_question(current: str | None) -> dict:
    return {
        "text": "Do members write notes straight into the team brain, or through the repo and one sync machine?",
        "options": [
            {"write": "direct", "label": "Everyone writes directly",
             "means": "each member gets a read+write key; notes go to the team brain, nothing is committed; no sync machine"},
            {"write": "sync", "label": "Through the repo",
             "means": "notes are committed to knowledge/; one machine imports them hourly; members get read-only keys"},
        ],
        "current": current,
        "recommended": current or "direct",
        "why": "already set in this repo's switch" if current else "small teams: one step less, no sync machine to keep running",
    }


def provisioner_hint() -> dict:
    """What a brain server (provisioner) entry enables and the two ways to get one on this machine"""
    return {
        "enables": "add --mode team creates the brain, issues member keys (share) and verifies it in one run",
        "without_it": "the brain admin creates the brain and keys in the server's admin page; pass --mcp-url/--mcp-name",
        "register": "registry add-provisioner --name brain-server --base-url https://<host>/api --credential <cred name>",
        "import": "registry export --out FILE on a machine that has it, copy the file over, then registry import --file FILE",
        # --prompt needs a real terminal; an agent saves the key to a file first and uses --from-file
        "store_admin_key": ("python3 ~/.projectops/bin/projectops_cli.py launch cred set --name <cred name> --secret-field token "
                            "--prompt (in a separate terminal) or --from-file FILE --delete-after"),
    }


def recommend_mode(has_provisioner: bool, own_brain: dict, authors: int, has_team_entry: bool) -> tuple[str, str]:
    if has_team_entry:
        return "team", "a team brain for this project is already in your registry (repair keeps it)"
    if has_provisioner and authors > TEAM_AUTHOR_THRESHOLD:
        return "team", f"{authors} people commit to this repo and a brain server is configured"
    if has_provisioner:
        return "team", "a brain server is configured, so teammates can join later with their own key"
    if own_brain.get("installed") and own_brain.get("kind") in ("local", "postgres"):
        return "own", "GBrain is installed on this machine and no team brain server is configured"
    return "repo-only", "no brain server and no GBrain here: notes stay in the repo until you set one up"


def dump(value) -> str:
    return json.dumps(value, ensure_ascii=False)
