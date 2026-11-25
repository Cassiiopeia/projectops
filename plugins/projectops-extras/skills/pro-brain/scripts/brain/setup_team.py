"""setup team helpers: team model preset (direct | sync), existing team server (base URL + key), team model question
Turns the two answers a team owner actually knows into the lower-level --to / --team-write / --team-brain-* flags.
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit

from . import brain_usage

TEAM_MODELS = ("direct", "sync")
TEAM_BRAIN_DECLINED = "none"    # team_brain value when the user chose no team brain
# Admin-managed team servers serve one brain per project at <base>/team/<key>/mcp
TEAM_SERVER_PATH = "/team/{key}/mcp"
TEAM_KEY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$")
MODEL_EXPLANATIONS = {
    "direct": "every member writes notes straight into the team brain with their own read+write key; nothing is "
              "committed to the repo (repo_notes off)",
    "sync": "notes are committed to the repo knowledge folder; members get read-only keys and a sync host imports the folder",
}


def derive_team_server(base_url: str, key: str) -> tuple[dict | None, str | None]:
    """(base URL, project key) > ({mcp_url, mcp_name}, None) or (None, error)"""
    key = (key or "").strip()
    if not TEAM_KEY_PATTERN.match(key):
        return None, f"team key '{key}' must be letters, digits and ._- (the brain key the admin created)"
    parts = urlsplit((base_url or "").strip())
    if parts.scheme != "https" or not parts.hostname:
        return None, "team server must be an https URL such as https://brain.example.com"
    if parts.username or parts.password or parts.query:
        return None, "team server URL must not carry a user, password or query (no token in URLs)"
    # Accept the base, or a URL the admin pasted that already ends in /team/<key>/mcp or /mcp
    path = re.sub(r"/team/[^/]+/mcp/?$|/mcp/?$", "", parts.path.rstrip("/"))
    url = f"https://{parts.netloc}{path}{TEAM_SERVER_PATH.format(key=key)}"
    return {"mcp_url": url, "mcp_name": f"gbrain-{key.lower()}"}, None


def apply_team_server(args) -> str | None:
    """--team-server + --team-key > fill --team-brain-url / --team-brain-name (explicit flags win); error text or None"""
    if not (getattr(args, "team_server", None) or getattr(args, "team_key", None)):
        return None
    if not (args.team_server and args.team_key):
        return "--team-server and --team-key go together (base URL and the project's brain key)"
    derived, error = derive_team_server(args.team_server, args.team_key)
    if error:
        return error
    args.team_brain_url = args.team_brain_url or derived["mcp_url"]
    args.team_brain_name = args.team_brain_name or derived["mcp_name"]
    return None


def apply_team_model(args) -> str | None:
    """--team-model direct|sync > --to and --team-write presets (explicit --to / --team-write must agree)"""
    model = getattr(args, "team_model", None)
    if not model:
        return None
    wanted = [part.strip() for part in (args.to or "").split(",") if part.strip()]
    if model == "direct":
        if wanted and "team" not in wanted:
            return "--team-model direct writes to the team brain: add team to --to or drop --to"
        if args.team_write and args.team_write != "direct":
            return "--team-model direct conflicts with --team-write sync"
        args.to = args.to or "team"
        args.team_write = "direct"
    else:
        if "team" in wanted:
            return "--team-model sync reads the team brain through the repo: remove team from --to"
        if args.team_write and args.team_write != "sync":
            return "--team-model sync conflicts with --team-write direct"
        args.to = args.to or "repo"
        args.team_write = "sync"
    return None


def current_team_model(switch: dict) -> str | None:
    team = switch.get("team_brain") if isinstance(switch.get("team_brain"), dict) else None
    if not team and not switch.get("brain_mcp"):
        return None
    return str((team or {}).get("write") or "sync")


def team_model_question(context: dict, args) -> dict | None:
    """First setup question whenever a team brain is involved (switch, registry hint or team flags)"""
    switch = context["switch"]
    is_involved = bool(current_team_model(switch) or context.get("registry_mcp_hint") or args.team_brain_name
                       or getattr(args, "team_server", None))
    if not is_involved or switch.get("team_brain_declined"):
        return None
    current = current_team_model(switch)
    return {"id": "team_model", "recommended": "direct", "current": current,
            "why": "small teams: one place to write, no sync host to run; choose sync when a reviewer should see "
                   "every note in a PR first",
            "question": "Do members write notes directly to the team brain, or through the repo and a sync host? "
                        "Recommended: direct",
            "choices": [{"id": model, "means": MODEL_EXPLANATIONS[model]} for model in TEAM_MODELS],
            "answer_flag": "--team-model direct|sync"}


def apply_team_write(team_updates: dict, team_removals: tuple, switch: dict, team_write: str | None) -> tuple[dict, tuple]:
    """--team-write or --to with/without team > team_brain.write (legacy brain_mcp becomes a team_brain map)"""
    if not team_write or team_updates.get("team_brain") == TEAM_BRAIN_DECLINED:
        return team_updates, team_removals
    base = team_updates.get("team_brain") or (dict(switch["team_brain"]) if isinstance(switch.get("team_brain"), dict) else
                                              ({"mcp_name": switch["brain_mcp"]} if switch.get("brain_mcp") else None))
    if not base or base.get("write", "sync") == team_write and "team_brain" not in team_updates:
        return team_updates, team_removals
    return {**team_updates, "team_brain": {**base, "write": team_write}}, tuple(set(team_removals) | ({"brain_mcp"} if switch.get("brain_mcp") else set()))


def team_brain_updates(args, switch: dict) -> tuple[dict, tuple[str, ...], str | None]:
    """--team-brain-* flags > (switch updates, keys to remove, error); off records team_brain: "none" (never asked again)"""
    if args.team_brain_off:
        return {"team_brain": TEAM_BRAIN_DECLINED}, ("brain_mcp",), None
    if not (args.team_brain_name or args.team_brain_url or args.team_brain_contact):
        return {}, (), None
    current = dict(switch.get("team_brain") or {}) if isinstance(switch.get("team_brain"), dict) else {}
    if switch.get("brain_mcp") and "mcp_name" not in current:
        current["mcp_name"] = switch["brain_mcp"]
    for key, value in (("mcp_name", args.team_brain_name), ("mcp_url", args.team_brain_url),
                       ("contact", args.team_brain_contact)):
        if value:
            current[key] = value.strip()
    error = brain_usage.validate_team_brain(current)
    # team_brain.mcp_name replaces the legacy brain_mcp key
    return {"team_brain": current}, ("brain_mcp",) if switch.get("brain_mcp") else (), error
