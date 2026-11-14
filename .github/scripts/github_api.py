#!/usr/bin/env python3
"""Shared GitHub REST calls (#914) — stdlib only.

Shared by the scripts workflows call (changelog_notice, issue_helper, close_issues_on_release,
pr_summary_comment, dispatch_downstream, store_deploy_config).
Decides auth headers, timeout, redirect handling and marker-comment updates in one place.

Copied file by file into user repos — it must also be in the copy list of src/core/copy/simple.js.
"""
from __future__ import annotations

import json
import urllib.request

API_ROOT = "https://api.github.com"
# Applied to every call so a workflow job never waits forever on no response
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_USER_AGENT = "projectops"
# Comment listing cap (100 x 10 pages) — so it stops even on issues with very many comments
COMMENTS_PER_PAGE = 100
DEFAULT_MAX_COMMENT_PAGES = 10


class StripAuthorizationOnRedirect(urllib.request.HTTPRedirectHandler):
    """Never pass the token to a redirect target (Azure Blob SAS URL, etc.) — doing so gives 403 and leaks the token."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is not None:
            redirected.headers.pop("Authorization", None)
            redirected.unredirected_hdrs.pop("Authorization", None)
        return redirected


_OPENER = urllib.request.build_opener(StripAuthorizationOnRedirect)


def send(method: str, url: str, token: str, payload: dict | None = None, *,
         user_agent: str = DEFAULT_USER_AGENT,
         timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS) -> tuple[int, object]:
    """One request > (HTTP status, JSON body or None). Non-2xx raises urllib.error.HTTPError."""
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": user_agent,
    }
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with _OPENER.open(req, timeout=timeout_seconds) as resp:
        raw = resp.read().decode("utf-8")
        return resp.status, (json.loads(raw) if raw else None)


def request(method: str, url: str, token: str, payload: dict | None = None, **options):
    """One request > JSON body (None for an empty response)."""
    return send(method, url, token, payload, **options)[1]


def list_issue_comments(repo: str, number: int, token: str, *, request_function=request,
                        max_pages: int = DEFAULT_MAX_COMMENT_PAGES) -> list:
    """All comments on an issue/PR (paged, capped at max_pages)."""
    comments: list = []
    for page in range(1, max_pages + 1):
        batch = request_function(
            "GET", f"{API_ROOT}/repos/{repo}/issues/{number}/comments"
                   f"?per_page={COMMENTS_PER_PAGE}&page={page}", token) or []
        comments.extend(batch)
        if len(batch) < COMMENTS_PER_PAGE:
            break
    return comments


def find_marker_comment(comments: list, marker: str):
    """First comment whose body contains marker. None if none."""
    return next((c for c in comments if marker in (c.get("body") or "")), None)


def upsert_marker_comment(repo: str, number: int, token: str, body: str, marker: str, *,
                          request_function=request, find_function=None,
                          max_pages: int = DEFAULT_MAX_COMMENT_PAGES) -> tuple[str, object]:
    """Update the marker comment, else create it > ("updated" | "created", comment id).

    Updates send no notification, so a repeated notice emails only the first time.
    request_function: injection point so callers' tests can use their mocked function as is
    find_function: (comments) > existing comment — for callers that must also find old markers
    """
    comments = list_issue_comments(repo, number, token,
                                   request_function=request_function, max_pages=max_pages)
    existing = find_function(comments) if find_function else find_marker_comment(comments, marker)
    if existing:
        request_function("PATCH", f"{API_ROOT}/repos/{repo}/issues/comments/{existing['id']}",
                         token, {"body": body})
        return "updated", existing["id"]
    created = request_function("POST", f"{API_ROOT}/repos/{repo}/issues/{number}/comments",
                               token, {"body": body})
    return "created", (created or {}).get("id")
