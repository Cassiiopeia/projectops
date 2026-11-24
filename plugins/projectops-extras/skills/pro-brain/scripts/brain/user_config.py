"""Personal destinations in the private projectops config: config.json > "pro-brain" section (mode 600, never in a repo)
Shape (schema 1): {"schema": 1, "repos": {"<owner/name or repo path>": {"local": {...}, "remotes": [...], "team_token_cred": ...}}}
Holds names and URLs only; tokens stay in the credential store and are referenced by token_cred.
"""
from __future__ import annotations

import re
from pathlib import Path

from . import credentials

SECTION = "pro-brain"
SCHEMA_VERSION = 1
REMOTE_KEYS = ("name", "mcp_url", "token_cred")
REMOTE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


def repo_key(remote_slug: str | None, repo_root: Path) -> str:
    """owner/name (case kept as on GitHub, matched case-insensitively), else the absolute repo path"""
    return remote_slug or str(repo_root)


def _section(data: dict | None) -> dict:
    section = (data or {}).get(SECTION) if isinstance(data, dict) else None
    return section if isinstance(section, dict) else {}


def read_repo_entry(remote_slug: str | None, repo_root: Path) -> tuple[dict, str]:
    """(entry, state) where state is ok | missing | unreadable; entry is normalized (local, remotes, team_token_cred)"""
    data, status = credentials.load_config()
    if status == "unreadable":
        return {}, "unreadable"
    repos = _section(data).get("repos")
    repos = repos if isinstance(repos, dict) else {}
    wanted = repo_key(remote_slug, repo_root).lower()
    entry = next((value for key, value in repos.items() if str(key).lower() == wanted and isinstance(value, dict)), None)
    if entry is None:
        return {"local": {"enabled": False}, "remotes": []}, "missing"
    return normalize_entry(entry), "ok"


def normalize_entry(entry: dict) -> dict:
    """Migrate older shapes: local: true > {enabled: true}; remotes as a dict by name > list"""
    local = entry.get("local")
    if isinstance(local, bool):
        local = {"enabled": local}
    local = local if isinstance(local, dict) else {"enabled": False}
    remotes = entry.get("remotes") or []
    if isinstance(remotes, dict):
        remotes = [{"name": name, **(value if isinstance(value, dict) else {})} for name, value in remotes.items()]
    remotes = [{key: str(item[key]) for key in REMOTE_KEYS if item.get(key)} for item in remotes
               if isinstance(item, dict) and item.get("name")]
    normalized = {"local": {"enabled": local.get("enabled") is True, "source_id": local.get("source_id")},
                  "remotes": remotes}
    if entry.get("team_token_cred"):
        normalized["team_token_cred"] = str(entry["team_token_cred"])
    return normalized


def validate_remote(remote: dict) -> str | None:
    if not REMOTE_NAME_PATTERN.match(remote.get("name") or ""):
        return f"remote brain name '{remote.get('name')}' must be letters, digits, - or _"
    url = remote.get("mcp_url") or ""
    if not re.match(r"^https?://[^\s\"']+$", url):
        return f"remote brain URL '{url}' must be an http(s) URL"
    if re.search(r"(token|key|secret|password)=", url, re.IGNORECASE) or "@" in url.split("//", 1)[-1].split("/", 1)[0]:
        return "remote brain URL must not carry a credential: store the token with launch cred set and pass --remote-token-cred"
    if remote.get("token_cred") and not credentials.is_valid_credential_name(remote["token_cred"]):
        return f"credential name '{remote['token_cred']}' must use letters, digits and ._-"
    return None


def plan_entry_update(current: dict, set_local: bool | None, add_remote: dict | None, remove_remotes: list[str],
                      team_token_cred: str | None) -> dict:
    """New entry from the current one and the setup flags (pure, nothing written)"""
    updated = {"local": dict(current.get("local") or {"enabled": False}),
               "remotes": [dict(item) for item in current.get("remotes") or []]}
    if current.get("team_token_cred"):
        updated["team_token_cred"] = current["team_token_cred"]
    if set_local is not None:
        updated["local"]["enabled"] = set_local
    removed = {name.lower() for name in remove_remotes}
    updated["remotes"] = [item for item in updated["remotes"] if item["name"].lower() not in removed]
    if add_remote:
        updated["remotes"] = [item for item in updated["remotes"] if item["name"].lower() != add_remote["name"].lower()]
        updated["remotes"].append({key: add_remote[key] for key in REMOTE_KEYS if add_remote.get(key)})
    if team_token_cred:
        updated["team_token_cred"] = team_token_cred
    return updated


def write_repo_entry(remote_slug: str | None, repo_root: Path, entry: dict) -> Path:
    """Merge one repo entry into config.json (other sections and repos kept, mode 600)"""
    data = credentials._load_for_write()
    section = data.setdefault(SECTION, {})
    if not isinstance(section, dict):
        raise credentials.CredentialError("config_unreadable", f"config.json '{SECTION}' is not an object; not overwritten")
    section["schema"] = SCHEMA_VERSION
    repos = section.setdefault("repos", {})
    wanted = repo_key(remote_slug, repo_root)
    for key in [key for key in repos if str(key).lower() == wanted.lower() and key != wanted]:
        del repos[key]   # one spelling per repo
    repos[wanted] = entry
    return credentials.write_config_atomic(data)
