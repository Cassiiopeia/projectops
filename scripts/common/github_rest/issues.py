"""Issues: create, edit, get, list, search, assignees, comments."""

from __future__ import annotations

import urllib.error
import urllib.parse

from common import gh_client as client
from common.github_rest.transport import _API_BASE, GitHubAPIError, is_transient_error


def create_issue(
    owner: str, repo: str, title: str, body: str,
    labels: list[str], pat: str, assignees: list[str] | None = None,
) -> dict:
    """Create an issue and return {number, url, title}."""
    # Nonexistent labels cause 422, so filter them first, but return the dropped list so the caller can report it
    skipped_labels: list[str] = []
    if labels:
        existing = client.list_labels(owner, repo, pat)
        labels = client.resolve_label_aliases(labels, existing)
        skipped_labels = [l for l in labels if l not in existing]
        labels = [l for l in labels if l in existing]
    payload: dict = {"title": title, "body": body, "labels": labels}
    if assignees:
        payload["assignees"] = assignees
    data = client._request("POST", f"{_API_BASE}/repos/{owner}/{repo}/issues", payload, pat)
    # Also return the assignees actually applied. Invalid assignees (not repo collaborators, etc.)
    # are silently dropped by GitHub, so the caller can compare request vs result and warn.
    return {
        "number": data["number"],
        "url": data["html_url"],
        "title": data["title"],
        "assignees": [u["login"] for u in data.get("assignees", [])],
        "skipped_labels": skipped_labels,
    }


def update_issue(
    owner: str, repo: str, issue_number: int, pat: str,
    title: str | None = None, body: str | None = None,
    state: str | None = None, labels: list[str] | None = None,
    assignees: list[str] | None = None,
    state_reason: str | None = None,
) -> dict:
    """Edit an issue and return {number, url, title}.

    state_reason: completed | not_planned | reopened; distinguishes done vs cancelled when closing (#819).
    """
    payload: dict = {}
    if title is not None:
        payload["title"] = title
    if body is not None:
        payload["body"] = body
    if state is not None:
        payload["state"] = state
    if state_reason is not None:
        payload["state_reason"] = state_reason
    if labels is not None:
        # PATCH creates missing labels, so first replace them with an alias name that exists in the repo (#776)
        labels = client.resolve_label_aliases(labels, client.list_labels(owner, repo, pat))
        payload["labels"] = labels
    if assignees is not None:
        payload["assignees"] = assignees
    data = client._request("PATCH", f"{_API_BASE}/repos/{owner}/{repo}/issues/{issue_number}", payload, pat)
    return {"number": data["number"], "url": data["html_url"], "title": data["title"]}


def add_assignees(
    owner: str, repo: str, issue_number: int, assignees: list[str], pat: str,
) -> dict:
    """Add assignees to an issue (existing ones kept). Up to 10.

    GitHub silently drops users without permission or that do not exist,
    so return the actual assignee list from the response for the caller to check against the request.
    """
    data = client._request(
        "POST",
        f"{_API_BASE}/repos/{owner}/{repo}/issues/{issue_number}/assignees",
        {"assignees": assignees},
        pat,
    )
    return {
        "number": data["number"],
        "url": data["html_url"],
        "assignees": [u["login"] for u in data.get("assignees", [])],
    }


def remove_assignees(
    owner: str, repo: str, issue_number: int, assignees: list[str], pat: str,
) -> dict:
    """Remove only the given assignees from an issue (others kept).

    This DELETE needs a body. Assignees not in the given list stay.
    """
    data = client._request(
        "DELETE",
        f"{_API_BASE}/repos/{owner}/{repo}/issues/{issue_number}/assignees",
        {"assignees": assignees},
        pat,
    )
    return {
        "number": data["number"],
        "url": data["html_url"],
        "assignees": [u["login"] for u in data.get("assignees", [])],
    }


def add_comment(
    owner: str, repo: str, issue_number: int, body: str, pat: str,
) -> dict:
    """Add a comment to an issue/PR and return {id, url}.

    The GitHub API treats PRs as issues, so a PR number works too.
    """
    try:
        data = client._request(
            "POST",
            f"{_API_BASE}/repos/{owner}/{repo}/issues/{issue_number}/comments",
            {"body": body},
            pat,
        )
    except (GitHubAPIError, urllib.error.URLError, TimeoutError, ConnectionError) as error:
        # Resending a POST would duplicate it, so instead of retrying, check whether it was posted despite the failure response (#941)
        posted = _find_just_posted_comment(owner, repo, issue_number, body, pat) \
            if is_transient_error(error) else None
        if posted is None:
            raise
        return {**posted, "reconciled": True}
    return {"id": data["id"], "url": data["html_url"]}


# Window for accepting a same-body comment posted just before a failure response (seconds)
_JUST_POSTED_WINDOW_SECONDS = 180


def _find_just_posted_comment(owner, repo, issue_number, body, pat) -> dict | None:
    """{id, url} if a comment with the same body was just posted (within 180 seconds). Lookup failures count as not found"""
    import datetime as dt
    try:
        items = client._request(
            "GET", f"{_API_BASE}/repos/{owner}/{repo}/issues/{issue_number}/comments?per_page=100", None, pat)
    except (GitHubAPIError, urllib.error.URLError, TimeoutError, ConnectionError):
        return None
    now = dt.datetime.now(dt.timezone.utc)
    for item in reversed(items):
        if (item.get("body") or "").strip() != body.strip():
            continue
        try:
            created = dt.datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
        except (KeyError, ValueError):
            continue
        if (now - created).total_seconds() <= _JUST_POSTED_WINDOW_SECONDS:
            return {"id": item["id"], "url": item["html_url"]}
    return None


def update_comment(
    owner: str, repo: str, comment_id: int, body: str, pat: str,
) -> dict:
    """Edit the body of one issue/PR comment and return {id, url}.

    The endpoint uses only comment_id, without issue_number (shared by issues and PRs).
    """
    data = client._request(
        "PATCH",
        f"{_API_BASE}/repos/{owner}/{repo}/issues/comments/{comment_id}",
        {"body": body},
        pat,
    )
    return {"id": data["id"], "url": data["html_url"]}


def delete_comment(
    owner: str, repo: str, comment_id: int, pat: str,
) -> dict:
    """Delete one issue/PR comment. The response is 204 (empty body), so it is not parsed."""
    client._request(
        "DELETE",
        f"{_API_BASE}/repos/{owner}/{repo}/issues/comments/{comment_id}",
        None,
        pat,
    )
    return {"comment_id": comment_id, "status": "deleted"}


def get_issue(owner: str, repo: str, issue_number: int, pat: str) -> dict:
    """Get an issue and return the summary fields the agent needs to decide."""
    data = client._request(
        "GET",
        f"{_API_BASE}/repos/{owner}/{repo}/issues/{issue_number}",
        None,
        pat,
    )
    return {
        "number": data["number"],
        "title": data["title"],
        "url": data["html_url"],
        "state": data["state"],
        "body": data.get("body", ""),
        "labels": [item["name"] for item in data.get("labels", [])],
        "assignees": [item["login"] for item in data.get("assignees", [])],
        "created_at": data.get("created_at"),
        "updated_at": data.get("updated_at"),
        "comments_count": data.get("comments", 0),
    }


def get_issue_comments(owner: str, repo: str, issue_number: int, pat: str) -> list[dict]:
    """Return issue comments in a form the agent can read directly (id · url: targets for edit-comment · delete-comment)."""
    items = client._request(
        "GET",
        f"{_API_BASE}/repos/{owner}/{repo}/issues/{issue_number}/comments?per_page=100",
        None,
        pat,
    )
    return [
        {
            "id": item.get("id"),
            "url": item.get("html_url"),
            "author": (item.get("user") or {}).get("login"),
            "body": item.get("body", ""),
            "created_at": item.get("created_at"),
        }
        for item in items
    ]


def list_issues(
    owner: str, repo: str, pat: str, state: str = "open",
    labels: str = "", limit: int = 50,
) -> list[dict]:
    """List issues (pull requests are excluded).

    labels: comma-separated, an issue must carry all of them.
    limit: maximum number of issues, 0 means all (follows pagination).
    """
    per_page = 100 if limit == 0 or limit > 50 else max(limit, 1)
    query = f"state={state}&per_page={per_page}"
    if labels:
        query += "&labels=" + urllib.parse.quote(labels, safe=",")
    found: list[dict] = []
    page = 1
    while True:
        items = client._request("GET", f"{_API_BASE}/repos/{owner}/{repo}/issues?{query}&page={page}", None, pat)
        for i in items:
            if "pull_request" in i:
                continue
            found.append({
                "number": i["number"], "title": i["title"], "url": i["html_url"], "state": i["state"],
                "labels": [lb["name"] for lb in i.get("labels", [])],
            })
        if len(items) < per_page or (limit and len(found) >= limit):
            break
        page += 1
    return found[:limit] if limit else found




def search_issues(
    owner: str, repo: str, keyword: str, pat: str, per_page: int = 5,
) -> list[dict]:
    """Search issues in the repo whose title contains keyword (for duplicate-issue checks)."""
    q = urllib.parse.quote(f"is:issue repo:{owner}/{repo} in:title {keyword}", safe="")
    data = client._request(
        "GET", f"{_API_BASE}/search/issues?q={q}&per_page={per_page}", None, pat
    )
    items = data.get("items", []) if isinstance(data, dict) else []
    return [
        {
            "number": i["number"],
            "title": i["title"],
            "url": i["html_url"],
            "state": i["state"],
            "labels": [label["name"] for label in i.get("labels", [])],
        }
        for i in items
    ]
