"""이슈: 생성·수정·조회·목록·검색, 담당자, 댓글."""

from __future__ import annotations

import urllib.parse

from common import gh_client as client
from common.github_rest.transport import _API_BASE


def create_issue(
    owner: str, repo: str, title: str, body: str,
    labels: list[str], pat: str, assignees: list[str] | None = None,
) -> dict:
    """이슈를 생성하고 {number, url, title}을 반환한다."""
    # 존재하지 않는 라벨은 422를 유발하므로 사전에 필터링하되, 버린 목록은 호출자가 알리도록 반환한다
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
    # 실제 반영된 담당자를 함께 반환한다. 유효하지 않은 담당자(레포 협업자 아님 등)는
    # GitHub이 조용히 누락시키므로, 호출자가 요청 대비 반영 결과를 비교해 경고할 수 있게 한다.
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
    """이슈를 수정하고 {number, url, title}을 반환한다.

    state_reason: completed | not_planned | reopened — 닫을 때 완료/취소를 구분한다 (#819).
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
        # 없는 라벨은 PATCH가 새로 만들어 버리므로, 별칭 중 레포에 있는 이름으로 먼저 치환한다 (#776)
        labels = client.resolve_label_aliases(labels, client.list_labels(owner, repo, pat))
        payload["labels"] = labels
    if assignees is not None:
        payload["assignees"] = assignees
    data = client._request("PATCH", f"{_API_BASE}/repos/{owner}/{repo}/issues/{issue_number}", payload, pat)
    return {"number": data["number"], "url": data["html_url"], "title": data["title"]}


def add_assignees(
    owner: str, repo: str, issue_number: int, assignees: list[str], pat: str,
) -> dict:
    """이슈에 담당자를 추가한다 (기존 담당자 유지). 최대 10명.

    권한 없는/존재하지 않는 유저는 GitHub이 조용히 누락시키므로,
    응답의 실제 담당자 목록을 반환해 호출자가 요청 대비 확인할 수 있게 한다.
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
    """이슈에서 지정한 담당자만 제거한다 (나머지 담당자 유지).

    이 DELETE는 body가 필요하다. 지정 목록에 없는 담당자는 그대로 남는다.
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
    """이슈/PR에 댓글을 추가하고 {id, url}을 반환한다.

    PR도 GitHub API에서는 issue로 다뤄지므로 PR 번호로도 호출 가능하다.
    """
    data = client._request(
        "POST",
        f"{_API_BASE}/repos/{owner}/{repo}/issues/{issue_number}/comments",
        {"body": body},
        pat,
    )
    return {"id": data["id"], "url": data["html_url"]}


def update_comment(
    owner: str, repo: str, comment_id: int, body: str, pat: str,
) -> dict:
    """이슈/PR 댓글 하나의 본문을 수정하고 {id, url}을 반환한다.

    엔드포인트가 issue_number 없이 comment_id만 쓴다 (issue·PR 공용).
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
    """이슈/PR 댓글 하나를 삭제한다. 204(빈 본문) 응답이므로 파싱하지 않는다."""
    client._request(
        "DELETE",
        f"{_API_BASE}/repos/{owner}/{repo}/issues/comments/{comment_id}",
        None,
        pat,
    )
    return {"comment_id": comment_id, "status": "deleted"}


def get_issue(owner: str, repo: str, issue_number: int, pat: str) -> dict:
    """이슈를 조회하고 agent 판단에 필요한 요약 필드를 반환한다."""
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
    """이슈 댓글 목록을 agent가 바로 읽기 쉬운 형태로 반환한다."""
    items = client._request(
        "GET",
        f"{_API_BASE}/repos/{owner}/{repo}/issues/{issue_number}/comments?per_page=100",
        None,
        pat,
    )
    return [
        {
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
    """레포 내 제목에 keyword가 포함된 이슈를 검색한다 (중복 이슈 판단용)."""
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
