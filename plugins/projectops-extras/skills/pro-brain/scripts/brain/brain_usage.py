"""Brain usage: how this repo's knowledge is read (repo only, own local or remote GBrain, team brain server)
Detection reads the gbrain CLI's engine-free status and source list; secret-shaped values are never kept or printed.
Personal brains are facts of this machine (detected each run); only the team brain lives in the shared repo switch.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

# Usage modes, in question order: 1 repo only, 2 own local GBrain, 3 own remote GBrain, 4 team brain, 5 install guide
USAGE_MODES = ("repo-only", "local-gbrain", "remote-gbrain", "team-brain", "install-guide")
PERSONAL_MODES = ("local-gbrain", "remote-gbrain")
GBRAIN_INSTALL_URL = "https://github.com/garrytan/gbrain"
GBRAIN_BINARY_ENV = "PRO_BRAIN_GBRAIN"   # optional path to the gbrain binary (default: gbrain on PATH)
GBRAIN_TIMEOUT_SECONDS = 60
# The name a personal GBrain usually registers; a team brain entry must never reuse it
PERSONAL_MCP_NAME = "gbrain"
MCP_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
ENGINE_FIELDS_SHOWN = ("effective_engine", "config_file_engine", "db_url_source", "thin_client")


def gbrain_binary() -> str | None:
    configured = os.environ.get(GBRAIN_BINARY_ENV)
    return configured if configured and Path(configured).is_file() else shutil.which("gbrain")


def run_gbrain(*arguments: str) -> tuple[int, str]:
    """gbrain command > (exit code, stdout); stderr is dropped because it can echo connection details"""
    binary = gbrain_binary()
    if not binary:
        return 127, ""
    try:
        completed = subprocess.run([binary, *arguments], capture_output=True, encoding="utf-8", errors="replace",
                                   timeout=GBRAIN_TIMEOUT_SECONDS, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return 1, ""
    return completed.returncode, completed.stdout or ""


def parse_json(text: str) -> dict | None:
    """Last JSON object in the output (gbrain may print progress lines before it)"""
    start = text.find("{")
    while start != -1:
        try:
            value = json.loads(text[start:])
            return value if isinstance(value, dict) else None
        except ValueError:
            start = text.find("{", start + 1)
    return None


def detect_gbrain() -> dict:
    """gbrain CLI on this machine: installed, engine (pglite | postgres), thin client (remote), brain ready, sources"""
    binary = gbrain_binary()
    if not binary:
        return {"installed": False, "brain_ready": False, "kind": "none", "sources": []}
    _, status_text = run_gbrain("engine", "status", "--json")
    status = parse_json(status_text) or {}
    engine = {field: status.get(field) for field in ENGINE_FIELDS_SHOWN}
    is_thin_client = status.get("thin_client") is True
    has_engine = bool(status.get("effective_engine"))
    detected = {"installed": True, "binary": binary, "engine": engine,
                "kind": "remote" if is_thin_client else ("local" if has_engine else "not-initialized"),
                "brain_ready": is_thin_client or has_engine, "sources": [], "sources_readable": False}
    if not has_engine:
        # A thin client has no local database: its sources live on the brain host
        return detected
    code, sources_text = run_gbrain("sources", "list", "--json")
    listed = (parse_json(sources_text) or {}).get("sources") if code == 0 else None
    if isinstance(listed, list):
        detected["sources_readable"] = True
        detected["sources"] = [{"id": str(item.get("id")), "local_path": item.get("local_path"),
                                "page_count": item.get("page_count"), "archived": item.get("archived") is True}
                               for item in listed if isinstance(item, dict) and item.get("id")]
    return detected


def is_inside(path_text: str | None, folder: Path) -> bool:
    if not path_text:
        return False
    try:
        candidate = Path(path_text).expanduser().resolve()
        base = folder.resolve()
    except OSError:
        return False
    return candidate == base or base in candidate.parents


def personal_sources_for_repo(detected: dict, repo_root: Path, source_id: str) -> list[dict]:
    """Sources of the local brain that read this repo: path inside the repo, or the standard id (a dedicated clone)"""
    return [source for source in detected.get("sources", [])
            if source["id"] == source_id or is_inside(source.get("local_path"), repo_root)]


def claude_mcp_server_names() -> list[str] | None:
    """MCP server names in the Claude Code user config (names only), None when unreadable"""
    config_folder = os.environ.get("CLAUDE_CONFIG_DIR")
    path = Path(config_folder) / ".claude.json" if config_folder else Path.home() / ".claude.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    servers = data.get("mcpServers") if isinstance(data, dict) else None
    return sorted(servers) if isinstance(servers, dict) else []


def validate_team_brain(team: dict) -> str | None:
    """Reason the team brain facts are unusable, or None"""
    name, url = team.get("mcp_name") or "", team.get("mcp_url") or ""
    if not MCP_NAME_PATTERN.match(name):
        return f"team brain MCP name '{name}' must be letters, digits, - or _ (for example gbrain-<project>)"
    if name.lower() == PERSONAL_MCP_NAME:
        return "team brain MCP name must differ from 'gbrain' so it never replaces anyone's personal brain entry"
    if not re.match(r"^https?://[^\s\"']+$", url):
        return f"team brain MCP URL '{url}' must be an http(s) URL"
    if re.search(r"(token|key|secret|password)=", url, re.IGNORECASE) or "@" in url.split("//", 1)[-1].split("/", 1)[0]:
        return "team brain MCP URL must not carry a credential: the token goes only into each member's own MCP entry"
    return None


def team_brain_instructions(team: dict, registered_names: list[str] | None, cred_name: str | None = None) -> dict:
    """What a teammate runs to read the team brain: get a read-only token, store it once, register one user-scope MCP entry"""
    name, url = team["mcp_name"], team["mcp_url"]
    contact = team.get("contact") or "the team brain admin"
    cred_name = cred_name or name
    return {
        "mcp_name": name, "mcp_url": url, "contact": contact, "cred_name": cred_name,
        "registered": (name in registered_names) if registered_names is not None else None,
        "steps": [f"ask {contact} for a personal read-only token for {name}",
                  f"store it once in a terminal (hidden input): python3 ~/.projectops/bin/projectops_cli.py launch cred set "
                  f"--name {cred_name} --secret-field token --prompt",
                  "brain_cli.py connect --team (plan), then connect --team --apply --yes: registers the user-scope MCP entry",
                  "restart the agent session, then search the team brain first for design and decision questions"],
        "manual_fallback": f'claude mcp add --scope user --transport http {name} {url} --header "Authorization: Bearer <token>"',
        "never": "put the token in the repo, a note, version.yml or the chat; replace or rename the personal 'gbrain' entry",
    }


def recommend_usage(detected: dict, team: dict | None, registry_hint: str | None, connected: list[dict]) -> dict:
    """Recommended answers (a personal mode can be combined with team-brain) with one-line reasons"""
    personal = None
    if detected.get("kind") == "local":
        personal = "local-gbrain"
    elif detected.get("kind") == "remote":
        personal = "remote-gbrain"
    reasons = []
    modes = []
    if personal:
        modes.append(personal)
        reasons.append(("a source of your local GBrain already reads this repo" if connected and personal == "local-gbrain"
                        else f"gbrain is set up on this machine ({detected['kind']} brain)"))
    if team:
        modes.append("team-brain")
        reasons.append(f"the repo switch names the team brain {team['mcp_name']}")
    elif registry_hint:
        modes.append("team-brain")
        reasons.append(f"your private registry names a team brain MCP {registry_hint} (record it to share it)")
    if not modes:
        modes = ["repo-only"]
        reasons.append("no brain found: the notes in the repo are enough" if not detected.get("installed")
                       else "gbrain is installed but has no brain yet: the notes in the repo are enough")
    return {"modes": modes, "reason": "; ".join(reasons)}


def current_usage(detected: dict, team: dict | None, connected: list[dict]) -> list[str]:
    """What is in effect now, from this machine and the repo switch"""
    modes = []
    if connected and detected.get("kind") == "local":
        modes.append("local-gbrain")
    if team:
        modes.append("team-brain")
    return modes or ["repo-only"]
