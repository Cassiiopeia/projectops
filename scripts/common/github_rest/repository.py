"""Repo exploration and admin: owner type, repo list and details, README, languages, commits, visibility, create, delete."""

from __future__ import annotations

import base64

from common import gh_client as client
from common.github_rest.transport import _API_BASE, GitHubAPIError


def get_user_type(owner: str, pat: str) -> str:
    """Return the GitHub owner type as either user or org."""
    data = client._request("GET", f"{_API_BASE}/users/{owner}", None, pat)
    return "org" if data.get("type") == "Organization" else "user"


def list_repos(owner: str, repo_type: str, pat: str) -> list[dict]:
    """Return the repo list of a user or organization."""
    endpoint = "orgs" if repo_type == "org" else "users"
    items = client._request("GET", f"{_API_BASE}/{endpoint}/{owner}/repos?per_page=100&sort=updated", None, pat)
    return [
        {
            "name": item["name"],
            "desc": item.get("description"),
            "lang": item.get("language"),
            "stars": item.get("stargazers_count", 0),
            "updated": item.get("updated_at"),
            "fork": item.get("fork", False),
            "private": item.get("private", False),
            "url": item.get("html_url"),
            "topics": item.get("topics", []),
        }
        for item in items
    ]


def get_repo_detail(owner: str, repo: str, pat: str) -> dict:
    """Return repo details."""
    data = client._request("GET", f"{_API_BASE}/repos/{owner}/{repo}", None, pat)
    return {
        "name": data["name"],
        "desc": data.get("description"),
        "lang": data.get("language"),
        "stars": data.get("stargazers_count", 0),
        "forks": data.get("forks_count", 0),
        "open_issues": data.get("open_issues_count", 0),
        "default_branch": data.get("default_branch"),
        "created_at": data.get("created_at"),
        "updated_at": data.get("updated_at"),
        "topics": data.get("topics", []),
        "url": data.get("html_url"),
        # Visibility: used for evidence image rendering and open-source audit decisions
        "private": data.get("private", False),
        "visibility": data.get("visibility"),
        # Shown before update-repo / delete-repo (size in KB)
        "full_name": data.get("full_name"),
        "size_kb": data.get("size", 0),
        "pushed_at": data.get("pushed_at"),
        "archived": data.get("archived", False),
        "fork": data.get("fork", False),
    }


def get_readme(owner: str, repo: str, pat: str) -> dict:
    """Return README content base64-decoded. content=None if missing."""
    try:
        data = client._request("GET", f"{_API_BASE}/repos/{owner}/{repo}/readme", None, pat)
    except GitHubAPIError as e:
        if e.status_code == 404:
            return {"content": None}
        raise
    content = data.get("content")
    if not content:
        return {"content": None}
    if data.get("encoding") == "base64":
        decoded = base64.b64decode(content).decode("utf-8", "replace")
        return {"content": decoded}
    return {"content": content}


def get_languages(owner: str, repo: str, pat: str) -> list[dict]:
    """Return per-language ratios in descending order."""
    data = client._request("GET", f"{_API_BASE}/repos/{owner}/{repo}/languages", None, pat)
    total = sum(data.values())
    if total <= 0:
        return []
    return [
        {"lang": lang, "percent": round((size / total) * 100, 1)}
        for lang, size in sorted(data.items(), key=lambda item: item[1], reverse=True)
    ]


def list_commits(owner: str, repo: str, pat: str, limit: int = 10) -> list[dict]:
    """Return the recent commit list."""
    limit = max(1, min(limit, 100))
    items = client._request("GET", f"{_API_BASE}/repos/{owner}/{repo}/commits?per_page={limit}", None, pat)
    commits = []
    for item in items:
        commit = item.get("commit") or {}
        author = commit.get("author") or {}
        message = (commit.get("message") or "").splitlines()[0]
        commits.append({
            "sha": item.get("sha", "")[:7],
            "date": author.get("date"),
            "author": author.get("name"),
            "msg": message,
        })
    return commits




def is_repo_private(owner: str, repo: str, pat: str) -> bool:
    """Whether the repo is private. Private repos block anonymous access, so images do not render."""
    return bool(client._request("GET", f"{_API_BASE}/repos/{owner}/{repo}", None, pat).get("private"))


def get_authenticated_login(pat: str) -> str:
    """Login of the PAT owner"""
    return client._request("GET", f"{_API_BASE}/user", None, pat).get("login", "")


def create_repo(owner: str, name: str, pat: str, *, is_private: bool, description: str | None,
                should_auto_init: bool) -> dict:
    """Create a new repo: /user/repos if the PAT owner, /orgs/{owner}/repos if an organization (#1007)"""
    body = {"name": name, "private": is_private, "auto_init": should_auto_init}
    if description:
        body["description"] = description
    is_pat_user = owner.lower() == get_authenticated_login(pat).lower()
    endpoint = f"{_API_BASE}/user/repos" if is_pat_user else f"{_API_BASE}/orgs/{owner}/repos"
    data = client._request("POST", endpoint, body, pat)
    return {
        "full_name": data.get("full_name"),
        "url": data.get("html_url"),
        "private": data.get("private", is_private),
        "default_branch": data.get("default_branch"),
        "clone_url": data.get("clone_url"),
    }


def update_repo_visibility(owner: str, repo: str, pat: str, *, is_private: bool) -> dict:
    """PATCH /repos/{owner}/{repo} with the private field only (#1241)"""
    data = client._request("PATCH", f"{_API_BASE}/repos/{owner}/{repo}", {"private": is_private}, pat)
    return {"full_name": data.get("full_name"), "private": data.get("private"),
            "visibility": data.get("visibility"), "url": data.get("html_url")}


def delete_repo(owner: str, repo: str, pat: str) -> None:
    """DELETE /repos/{owner}/{repo} — irreversible; needs delete_repo scope or Administration write (#1241)"""
    client._request("DELETE", f"{_API_BASE}/repos/{owner}/{repo}", None, pat)


def list_tree_paths(owner: str, repo: str, ref: str, pat: str) -> tuple[list[str], bool]:
    """File paths on ref (one recursive tree call) > (paths, truncated by GitHub)"""
    data = client._request("GET", f"{_API_BASE}/repos/{owner}/{repo}/git/trees/{ref}?recursive=1", None, pat)
    paths = [item["path"] for item in data.get("tree", []) if item.get("type") == "blob"]
    return paths, bool(data.get("truncated"))
