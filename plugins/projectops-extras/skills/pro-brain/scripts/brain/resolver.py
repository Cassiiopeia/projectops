"""Where notes go: one resolution chain shared by status, doctor, write, connect and gaps (importable by other skills)
Chain: repo switch in version.yml (shared) > private config.json (pro-brain section, project-blueprint registry) >
credential store (secrets by name only). Every resolved value carries its origin; no secret value is ever read here.
"""
from __future__ import annotations

from pathlib import Path

from . import http_client, registry, user_config
from .repo_facts import TEAM_BRAIN_WRITE_MODES

REPO_SWITCH_SCHEMA = 2
DESTINATION_REPO = "repo"
DESTINATION_LOCAL = "local"
DESTINATION_TEAM = "team"
REMOTE_PREFIX = "remote:"
SWITCH_ORIGIN = "version.yml knowledge"
CONFIG_ORIGIN = "config.json pro-brain"


def registry_brain_for_mcp(section: dict | None, mcp_name: str | None) -> tuple[str | None, dict]:
    """project-blueprint infra.brains entry whose mcp_server_name is mcp_name (owner registry, optional)"""
    brains = ((section or {}).get("infra") or {}).get("brains") or {}
    for name, brain in brains.items() if isinstance(brains, dict) else []:
        if isinstance(brain, dict) and mcp_name and brain.get("mcp_server_name") == mcp_name:
            return name, brain
    return None, {}


def _team_destination(context: dict, personal: dict) -> dict | None:
    """Shared remote brain from the switch (team_brain, legacy brain_mcp) with URL and token name filled from the chain"""
    switch = context["switch"]
    team = switch.get("team_brain") if isinstance(switch.get("team_brain"), dict) else None
    legacy_name = switch.get("brain_mcp")
    if not team and not legacy_name:
        return None
    name = (team or {}).get("mcp_name") or legacy_name
    origin = f"{SWITCH_ORIGIN}.team_brain" if team else f"{SWITCH_ORIGIN}.brain_mcp (legacy)"
    registry_name, registry_brain = registry_brain_for_mcp(context.get("section"), name)
    url, url_origin = (team or {}).get("mcp_url"), f"{SWITCH_ORIGIN}.team_brain.mcp_url"
    if not url and registry_brain.get("mcp_url"):
        url, url_origin = registry_brain["mcp_url"], f"config.json project-blueprint infra.brains.{registry_name}.mcp_url"
    if not url:
        url_origin = "unknown (public repos may record the name only; ask the brain admin or add it to your registry)"
    write = str((team or {}).get("write") or "sync").lower()
    write = write if write in TEAM_BRAIN_WRITE_MODES else "sync"
    if personal.get("team_token_cred"):
        cred, cred_origin = personal["team_token_cred"], f"{CONFIG_ORIGIN} team_token_cred"
    elif registry_brain.get("token_cred"):
        cred, cred_origin = registry_brain["token_cred"], f"config.json project-blueprint infra.brains.{registry_name}.token_cred"
    else:
        cred, cred_origin = name, "default (the MCP name)"
    return {"id": DESTINATION_TEAM, "kind": "gbrain-remote", "scope": "shared", "name": name, "origin": origin,
            "mcp_url": url, "mcp_url_shown": http_client.mask_url(url), "url_origin": url_origin,
            "token_cred": cred, "token_cred_origin": cred_origin, "write": write,
            "contact": (team or {}).get("contact"), "is_write_target": write == "direct",
            "role": "write directly" if write == "direct" else "read (a sync job on the brain host imports the repo folder)"}


def resolve(context: dict) -> dict:
    """Effective destinations for one repo (context from commands.repo_context) with origins and legacy mapping"""
    switch, root = context["switch"], context["root"]
    personal, personal_state = user_config.read_repo_entry(context.get("remote"), root)
    raw_schema = switch.get("schema")
    schema = raw_schema if isinstance(raw_schema, int) else 1
    repo_notes = switch.get("repo_notes")
    is_repo_on = repo_notes is not False
    destinations = []
    if is_repo_on:
        destinations.append({"id": DESTINATION_REPO, "kind": "repo-files", "scope": "shared", "is_write_target": True,
                             "path": switch.get("path", "knowledge/"),
                             "origin": f"{SWITCH_ORIGIN}.repo_notes" if repo_notes is True else "default (repo_notes absent = on)"})
    if personal["local"]["enabled"]:
        destinations.append({"id": DESTINATION_LOCAL, "kind": "gbrain-local", "scope": "personal", "is_write_target": True,
                             "source_id": personal["local"].get("source_id"),
                             "origin": f"{CONFIG_ORIGIN}.repos[{user_config.repo_key(context.get('remote'), root)}].local"})
    team = _team_destination(context, personal)
    if team:
        destinations.append(team)
    for remote in personal["remotes"]:
        destinations.append({"id": REMOTE_PREFIX + remote["name"], "kind": "gbrain-remote", "scope": "personal",
                             "name": remote["name"], "mcp_url": remote.get("mcp_url"),
                             "mcp_url_shown": http_client.mask_url(remote.get("mcp_url")),
                             "url_origin": f"{CONFIG_ORIGIN} remotes[{remote['name']}]",
                             "token_cred": remote.get("token_cred") or remote["name"],
                             "token_cred_origin": f"{CONFIG_ORIGIN} remotes[{remote['name']}].token_cred"
                                                  if remote.get("token_cred") else "default (the remote name)",
                             "write": "direct", "is_write_target": True, "role": "write directly",
                             "origin": f"{CONFIG_ORIGIN} remotes"})
    sync_branch = switch.get("sync_branch")
    resolved = {"schema": {"repo_switch": schema, "repo_switch_current": REPO_SWITCH_SCHEMA,
                           "user_config": user_config.SCHEMA_VERSION if personal_state == "ok" else None},
                "user_config_state": personal_state,
                "repo_notes": {"value": is_repo_on, "origin": f"{SWITCH_ORIGIN}.repo_notes" if repo_notes is not None
                               else "default (absent = on)"},
                "sync_branch": {"value": sync_branch or context["default_branch"],
                                "origin": f"{SWITCH_ORIGIN}.sync_branch" if sync_branch else "default_branch (version.yml)"},
                "destinations": destinations,
                "write_targets": [item["id"] for item in destinations if item["is_write_target"]],
                "brain_targets": [item["id"] for item in destinations if item["kind"] != "repo-files" and item["is_write_target"]]}
    resolved["legacy_mapping"] = describe_mapping(switch, resolved)
    return resolved


def describe_mapping(switch: dict, resolved: dict) -> str:
    """One line on how an older switch form maps to destinations (empty when the switch is current)"""
    parts = []
    if switch.get("brain_mcp") and not switch.get("team_brain"):
        parts.append(f"legacy brain_mcp '{switch['brain_mcp']}' = repo files + shared remote brain read via sync")
    elif isinstance(switch.get("team_brain"), dict) and not switch["team_brain"].get("write"):
        parts.append("team_brain without write = shared remote brain read via sync")
    if resolved["schema"]["repo_switch"] < REPO_SWITCH_SCHEMA:
        parts.append(f"switch schema {resolved['schema']['repo_switch']} read as schema {REPO_SWITCH_SCHEMA} "
                     "(repo_notes absent = on); setup --apply --yes records it")
    return "; ".join(parts)


def select(resolved: dict, target: str | None) -> tuple[list[dict], str | None]:
    """--to all|repo|local|team|remote:NAME (comma list) > write-target destinations, or an error naming what exists"""
    targets = [item["id"] for item in resolved["destinations"] if item["is_write_target"]]
    wanted = [part.strip() for part in (target or "all").split(",") if part.strip()]
    if wanted == ["all"]:
        return [item for item in resolved["destinations"] if item["is_write_target"]], None
    by_id = {item["id"].lower(): item for item in resolved["destinations"]}
    chosen, unknown = [], []
    for name in wanted:
        item = by_id.get(name.lower())
        if item is None or not item["is_write_target"]:
            unknown.append(name)
        else:
            chosen.append(item)
    if unknown:
        return [], f"not a write destination of this repo: {', '.join(unknown)} (configured: {', '.join(targets) or 'none'})"
    return chosen, None


def resolve_for_repo(repo_path: str | Path | None = None) -> dict:
    """Convenience for other skills: build the repo context and resolve it"""
    from .commands import repo_context
    return resolve(repo_context(str(repo_path) if repo_path else None))
