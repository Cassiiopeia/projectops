"""Find·save Figma token and query REST: FIGMA_TOKEN > provider figma entry in config launch.credentials

No new store — the single token source is the config.json used by pro-launch cred.
The token value is never returned or printed (only the source name is reported).
"""
from __future__ import annotations

import os

from common import config
from common.http import request

TOKEN_ENV_NAME = "FIGMA_TOKEN"
DEFAULT_CRED_NAME = "projectops-pro-figma"
FIGMA_API = "https://api.figma.com/v1"
FIGMA_PROVIDER = "figma"
# Choices the agent shows the user when there is no token (shared by check-fresh and ingest)
TOKEN_MISSING_OPTIONS = [
    {"id": "register", "label": "Register a Figma token now (saved once, never asked again)",
     "command": "figma_cli.py token --prompt   # hidden input in your own terminal, or --from-env NAME"},
    {"id": "skip", "label": "Skip the change check this time (the result stays 'unknown')"},
    {"id": "user_confirmed", "label": "You confirm the design has not changed, and the work continues"},
]


def find_token() -> tuple[str | None, str | None]:
    """(token, source). Source is 'env:FIGMA_TOKEN' or 'cred:<name>' — the value never leaves."""
    env_value = os.environ.get(TOKEN_ENV_NAME, "").strip()
    if env_value:
        return env_value, f"env:{TOKEN_ENV_NAME}"
    data = config.load() or {}
    credentials = (data.get("launch") or {}).get("credentials") or {}
    for name, entry in credentials.items():
        if isinstance(entry, dict) and entry.get("provider") == FIGMA_PROVIDER and entry.get("token"):
            return str(entry["token"]), f"cred:{name}"
    return None, None


def save_token(token: str, cred_name: str | None = None) -> tuple[str | None, dict | None]:
    """(saved entry name, None) or (None, error payload). If a figma entry exists, only its token is replaced."""
    data, status = config.load_with_status()
    if status == "unreadable":
        # Overwriting a broken config would wipe other sections
        return None, {"ok": False, "code": "config_unreadable",
                      "error": "config.json exists but cannot be read; not overwriting it",
                      "hint": "Fix or restore ~/.projectops/config/config.json first"}
    data = data or {}
    credentials = data.setdefault("launch", {}).setdefault("credentials", {})
    existing = next((n for n, e in credentials.items()
                     if isinstance(e, dict) and e.get("provider") == FIGMA_PROVIDER), None)
    name = cred_name or existing or DEFAULT_CRED_NAME
    entry = credentials.get(name) if isinstance(credentials.get(name), dict) else {}
    entry.update({"kind": "http", "provider": FIGMA_PROVIDER, "token": token})
    entry.setdefault("scope", "readonly")
    entry.setdefault("use_when", "pro-figma design lookup, asset download and change check")
    credentials[name] = entry
    config.save(data)
    return name, None


def fetch_json(path: str, token: str, timeout: int = 20) -> dict:
    """GET {FIGMA_API}{path}. Returns the request() result as is (4xx·5xx are results too)."""
    return request("GET", f"{FIGMA_API}{path}", headers={"X-Figma-Token": token}, timeout=timeout)


def fetch_file_state(file_key: str, token: str) -> dict:
    """The file's current lastModified · version. depth=1, so almost no body is fetched.

    Returns: ok · lastModified · version · name  /  on failure ok False + code (figma_token_rejected ·
    figma_file_not_found · request_failed)
    """
    r = fetch_json(f"/files/{file_key}?depth=1", token)
    if not r.get("ok"):
        return {"ok": False, "code": r.get("code", "request_failed"), "error": r.get("error", "")}
    status = r["status"]
    if status in (401, 403):
        return {"ok": False, "code": "figma_token_rejected", "status": status}
    if status == 404:
        return {"ok": False, "code": "figma_file_not_found", "status": status}
    body = r.get("json")
    if status != 200 or not isinstance(body, dict):
        return {"ok": False, "code": "request_failed", "status": status,
                "next": "429: wait a minute and retry. 5xx: Figma is failing, retry later. No status: check the network"}
    return {"ok": True, "lastModified": body.get("lastModified"), "version": body.get("version"),
            "name": body.get("name")}
