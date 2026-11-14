"""GitHub API access: error classification, single HTTP gateway (_call), listing/file/label/README lookups, PAT lookup
Tests replace this module's _call·_pat (command modules reach them as module attributes, so the replacement applies)
"""
from __future__ import annotations

import base64
import time
import urllib.parse

from common import gh_client

_API = "https://api.github.com"
# Applied to every HTTP call so a dropped connection never waits forever
_TIMEOUT = 20

# ── Error classification (pure — under test) ───────────────────────────────────────

def _reset_when(reset: str | None) -> str | None:
    try:
        return time.strftime("%H:%M:%S", time.localtime(int(reset)))
    except (TypeError, ValueError):
        return None


def classify_api_error(e: Exception) -> dict:
    """Unpack a GitHub error into code/summary/next. Tells rate limits apart from permission errors."""
    if isinstance(e, gh_client.GitHubNetworkError):
        return {"code": "network", "summary": f"Network error: {e}",
                "next": "Check the network connection and run the same command again"}
    status = getattr(e, "status_code", 0)
    h = getattr(e, "headers", None) or {}
    msg = str(getattr(e, "message", e))
    if status in (403, 429) and (h.get("x-ratelimit-remaining") == "0" or "retry-after" in h
                                 or "rate limit" in msg.lower() or status == 429):
        when = _reset_when(h.get("x-ratelimit-reset"))
        wait = h.get("retry-after")
        hint = f"After {when}," if when else (f"In {wait} seconds," if wait else "In a moment,")
        return {"code": "rate_limited", "summary": f"GitHub API rate limit exceeded: {msg}",
                "next": f"{hint} run the same command again. Split the target repos to make fewer calls"}
    nxt = {
        401: "The PAT has expired or is wrong. Register the PAT again with /pro-github",
        403: "The PAT has no permission to read this repo (repo scope). Check the permissions",
        404: "The repo name has a typo, or the repo is private and the PAT has no access. Check both",
        410: "This feature is turned off for the repo (for example, issues disabled). Treat the fact as 'turned off', not 'missing'",
    }.get(status, "Read the error message, fix the input and run again")
    return {"code": f"http_{status}", "summary": f"{msg}", "next": nxt}


# ── Network ─────────────────────────────────────────────────────────────

def _call(method: str, path: str, pat: str, data: dict | None = None):
    """Single gateway for every HTTP call — separates timeouts and network errors. Tests replace this function."""
    return gh_client.request_json(method, f"{_API}{path}", data, pat, timeout=_TIMEOUT)


def _get(path: str, pat: str):
    return _call("GET", path, pat)


def _listing(owner: str, repo: str, sub: str, pat: str) -> dict:
    try:
        items = _get(f"/repos/{owner}/{repo}/contents/{urllib.parse.quote(sub)}" if sub
                     else f"/repos/{owner}/{repo}/contents/", pat)
    except gh_client.GitHubAPIError as e:
        if e.status_code == 404:
            return {}
        raise
    if not isinstance(items, list):
        return {}
    return {it["name"]: it["type"] for it in items}


def _file_text(owner: str, repo: str, path: str, pat: str) -> str | None:
    try:
        d = _get(f"/repos/{owner}/{repo}/contents/{urllib.parse.quote(path)}", pat)
    except gh_client.GitHubAPIError as e:
        if e.status_code == 404:
            return None
        raise
    if not isinstance(d, dict) or "content" not in d:
        return None
    return base64.b64decode(d.get("content", "")).decode("utf-8", "replace")


_LABEL_PAGES = 5


def _label_records(owner: str, repo: str, pat: str) -> tuple[list[dict], bool]:
    """All label records. capped=True when the page cap (500) is hit."""
    rows: list[dict] = []
    for page in range(1, _LABEL_PAGES + 1):
        items = _get(f"/repos/{owner}/{repo}/labels?per_page=100&page={page}", pat)
        rows += items
        if len(items) < 100:
            return rows, False
    return rows, True


def _pat(owner: str | None, repo: str | None) -> str | None:
    from common.config import get_github_pat
    return get_github_pat(owner, repo)


def _readme(owner: str, repo: str, pat: str) -> str | None:
    try:
        rd = _get(f"/repos/{owner}/{repo}/readme", pat)
    except gh_client.GitHubAPIError as e:
        if e.status_code == 404:
            return None
        raise
    return base64.b64decode(rd.get("content", "")).decode("utf-8", "replace")
