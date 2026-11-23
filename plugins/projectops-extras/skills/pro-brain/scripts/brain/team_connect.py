"""Team brain connection for one member: repo switch team_brain + token from the credential store > one user-scope MCP entry
Plan by default; apply runs `claude mcp add` only after consent. The token goes to the claude process only, never to
stdout, a file, a note or version.yml. Optional project `.mcp.json` holds `${GBRAIN_<PROJECT>_TOKEN}`, never the token.
"""
from __future__ import annotations

import difflib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from . import brain_usage, credentials

CLAUDE_BINARY_ENV = "PRO_BRAIN_CLAUDE"     # optional path to the claude binary (default: claude on PATH)
CLAUDE_TIMEOUT_SECONDS = 60
TOKEN_FIELD = "token"
PROJECT_MCP_FILE = ".mcp.json"
# Placeholder shown instead of the token in every printed command
TOKEN_PLACEHOLDER = "<token>"
# Stable entry point of core projectops (pro-launch owns the credential store commands)
CRED_SET_COMMAND = ("python3 ~/.projectops/bin/projectops_cli.py launch cred set --name {name} --secret-field token "
                    "--prompt --json '{{\"kind\":\"token\",\"provider\":\"gbrain\",\"use_when\":\"team brain {mcp_name} MCP entry\"}}'")


def claude_binary() -> str | None:
    configured = os.environ.get(CLAUDE_BINARY_ENV)
    return configured if configured and Path(configured).is_file() else shutil.which("claude")


def token_env_name(project: str) -> str:
    """Project key > env var holding the token for the shared .mcp.json, e.g. secbrief > GBRAIN_SECBRIEF_TOKEN"""
    return "GBRAIN_" + re.sub(r"[^A-Za-z0-9]+", "_", project).strip("_").upper() + "_TOKEN"


def add_command(team: dict, token_text: str) -> list[str]:
    return ["claude", "mcp", "add", "--scope", "user", "--transport", "http", team["mcp_name"], team["mcp_url"],
            "--header", f"Authorization: Bearer {token_text}"]


def display_command(arguments: list[str]) -> str:
    """Shell-readable line for people (the token part is always the placeholder)"""
    return " ".join(f'"{part}"' if " " in part else part for part in arguments)


def _token_state(cred_name: str) -> str:
    """stored | missing | unreadable (the value itself is discarded here)"""
    try:
        credentials.read_secret(cred_name, TOKEN_FIELD)
        return "stored"
    except credentials.CredentialError as error:
        return "unreadable" if error.code == "config_unreadable" else "missing"


def project_mcp_entry(team: dict, project: str) -> dict:
    return {"type": "http", "url": team["mcp_url"],
            "headers": {"Authorization": f"Bearer ${{{token_env_name(project)}}}"}}


def plan_project_mcp_json(repo_root: Path, team: dict, project: str) -> dict:
    """Merge one server entry into .mcp.json (other servers kept); refuses a file that is not a JSON object"""
    path = repo_root / PROJECT_MCP_FILE
    old_text = path.read_text(encoding="utf-8") if path.is_file() else ""
    try:
        data = json.loads(old_text) if old_text.strip() else {}
    except ValueError:
        return {"state": "unreadable", "path": str(path), "summary": f"{PROJECT_MCP_FILE} is not valid JSON; not touched"}
    if not isinstance(data, dict) or not isinstance(data.setdefault("mcpServers", {}), dict):
        return {"state": "unreadable", "path": str(path), "summary": f"{PROJECT_MCP_FILE} has an unexpected shape; not touched"}
    entry = project_mcp_entry(team, project)
    state = "up_to_date" if data["mcpServers"].get(team["mcp_name"]) == entry else "write"
    data["mcpServers"][team["mcp_name"]] = entry
    new_text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    return {"state": state, "path": str(path), "env_var": token_env_name(project), "new_text": new_text,
            "diff": "".join(difflib.unified_diff(old_text.splitlines(keepends=True), new_text.splitlines(keepends=True),
                                                 fromfile=f"a/{PROJECT_MCP_FILE}", tofile=f"b/{PROJECT_MCP_FILE}", n=1))}


def plan(team: dict | None, cred_name: str | None, project: str, repo_root: Path, is_rotate: bool,
         wants_project_file: bool) -> dict:
    """Verdict code: ready | already_registered | token_missing | config_unreadable | claude_cli_missing | no_team_brain | bad_team_brain"""
    if not team:
        return {"code": "no_team_brain", "summary": "the repo switch records no team brain (version.yml team_brain)"}
    error = brain_usage.validate_team_brain(team)
    if error:
        return {"code": "bad_team_brain", "summary": error}
    cred_name = cred_name or team["mcp_name"]
    if not credentials.is_valid_credential_name(cred_name):
        return {"code": "bad_cred_name", "summary": f"credential name '{cred_name}' must use letters, digits and ._-"}
    registered_names = brain_usage.claude_mcp_server_names()
    is_registered = bool(registered_names) and team["mcp_name"] in registered_names
    result = {"team_brain": team, "cred_name": cred_name, "registered": is_registered,
              "token_state": _token_state(cred_name), "claude_cli": bool(claude_binary()), "rotate": is_rotate,
              "command": display_command(add_command(team, TOKEN_PLACEHOLDER)),
              "store_token_command": CRED_SET_COMMAND.format(name=cred_name, mcp_name=team["mcp_name"])}
    if wants_project_file:
        project_file = plan_project_mcp_json(repo_root, team, project)
        result["project_mcp_json"] = {key: value for key, value in project_file.items() if key != "new_text"}
    if result["token_state"] == "unreadable":
        return {**result, "code": "config_unreadable", "summary": "config.json exists but cannot be read; nothing done"}
    if result["token_state"] == "missing":
        return {**result, "code": "token_missing",
                "summary": f"no token stored under credential '{cred_name}': the user stores it once in a terminal"}
    if not result["claude_cli"]:
        return {**result, "code": "claude_cli_missing",
                "summary": "the claude CLI is not on PATH: the user runs the command with the token in place of <token>"}
    if is_registered and not is_rotate:
        return {**result, "code": "already_registered",
                "summary": f"{team['mcp_name']} is already registered for this user; --rotate re-registers it with the stored token"}
    return {**result, "code": "ready",
            "summary": f"ready to {'re-register' if is_registered else 'register'} {team['mcp_name']} "
                       f"(user scope) with the token stored as '{cred_name}'"}


def _run_claude(arguments: list[str], token: str) -> tuple[int, str]:
    """claude subcommand > (exit code, output with the token masked)"""
    binary = claude_binary()
    try:
        completed = subprocess.run([binary, *arguments[1:]], capture_output=True, encoding="utf-8", errors="replace",
                                   timeout=CLAUDE_TIMEOUT_SECONDS, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as error:
        return 1, credentials.mask_values(str(error), [token])
    output = (completed.stdout or "") + (completed.stderr or "")
    return completed.returncode, credentials.mask_values(output.strip()[-600:], [token])


def apply(plan_result: dict, repo_root: Path, project: str) -> dict:
    """Register (or rotate) the user-scope entry, then write .mcp.json when it was planned; stops at the first failure"""
    steps = []
    team = plan_result.get("team_brain")
    if plan_result["code"] == "ready":
        token = credentials.read_secret(plan_result["cred_name"], TOKEN_FIELD)
        if plan_result["registered"]:
            exit_code, output = _run_claude(["claude", "mcp", "remove", "--scope", "user", team["mcp_name"]], token)
            steps.append({"step": "claude mcp remove", "ok": exit_code == 0, "output": output})
            if exit_code != 0:
                return {"ok": False, "code": "remove_failed", "steps": steps,
                        "summary": f"could not remove the old {team['mcp_name']} entry; nothing else was run"}
        exit_code, output = _run_claude(add_command(team, token), token)
        steps.append({"step": "claude mcp add", "ok": exit_code == 0, "output": output})
        if exit_code != 0:
            return {"ok": False, "code": "add_failed", "steps": steps,
                    "summary": f"claude mcp add failed for {team['mcp_name']}; read steps[].output (token masked)"}
    project_file = plan_result.get("project_mcp_json")
    if project_file and project_file["state"] == "write":
        planned = plan_project_mcp_json(repo_root, team, project)
        Path(planned["path"]).write_text(planned["new_text"], encoding="utf-8")
        steps.append({"step": f"write {PROJECT_MCP_FILE}", "ok": True, "env_var": planned["env_var"]})
    if not steps:
        return {"ok": False, "code": "nothing_applied", "steps": steps, "summary": f"nothing applied: {plan_result['summary']}"}
    return {"ok": True, "code": "connected", "steps": steps,
            "summary": "; ".join(step["step"] for step in steps) + " done (token never printed)"}
