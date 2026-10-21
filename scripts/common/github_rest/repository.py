"""레포 탐색: owner 타입, 레포 목록·상세, README, 언어, 커밋, 공개 여부."""

from __future__ import annotations

import base64

from common import gh_client as client
from common.github_rest.transport import _API_BASE, GitHubAPIError


def get_user_type(owner: str, pat: str) -> str:
    """GitHub owner 타입을 user/org 중 하나로 반환한다."""
    data = client._request("GET", f"{_API_BASE}/users/{owner}", None, pat)
    return "org" if data.get("type") == "Organization" else "user"


def list_repos(owner: str, repo_type: str, pat: str) -> list[dict]:
    """사용자 또는 조직의 레포 목록을 반환한다."""
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
    """레포 상세 정보를 반환한다."""
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
        # 공개 여부: 증적 이미지 렌더링·오픈소스 점검 판단에 쓴다
        "private": data.get("private", False),
        "visibility": data.get("visibility"),
    }


def get_readme(owner: str, repo: str, pat: str) -> dict:
    """README 내용을 base64 디코딩해 반환한다. 없으면 content=None."""
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
    """언어별 비율을 내림차순으로 반환한다."""
    data = client._request("GET", f"{_API_BASE}/repos/{owner}/{repo}/languages", None, pat)
    total = sum(data.values())
    if total <= 0:
        return []
    return [
        {"lang": lang, "percent": round((size / total) * 100, 1)}
        for lang, size in sorted(data.items(), key=lambda item: item[1], reverse=True)
    ]


def list_commits(owner: str, repo: str, pat: str, limit: int = 10) -> list[dict]:
    """최근 커밋 목록을 반환한다."""
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
    """private 레포인지. private이면 익명 접근이 막혀 이미지가 렌더링되지 않는다."""
    return bool(client._request("GET", f"{_API_BASE}/repos/{owner}/{repo}", None, pat).get("private"))
