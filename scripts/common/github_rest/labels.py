"""라벨: 한글·영문 별칭 치환, 조회·추가·하나 제거·전체 교체."""

from __future__ import annotations

import urllib.parse

from common import gh_client as client
from common.github_rest.transport import _API_BASE


# 한글 상태 라벨과 영문 표준 라벨(#776)은 같은 라벨이다. 전환 기간에는 레포에 있는 쪽 이름으로 치환한다.
LABEL_ALIAS_GROUPS = [
    ("작업전", "status: todo"),
    ("작업중", "status: in progress"),
    ("담당자확인", "status: needs review"),
    ("피드백", "status: feedback"),
    ("작업완료", "status: done"),
    ("보류", "status: on hold"),
    ("취소", "status: cancelled"),
    ("긴급", "priority: urgent"),
    ("문서", "documentation"),
]

# 상태 라벨 이름 전부 (한글·영문, 위 표의 앞 7묶음): 완료 처리·라벨 교체 경고가 이것만 상태로 본다
STATUS_LABEL_NAMES = frozenset(name for group in LABEL_ALIAS_GROUPS[:7] for name in group)


def resolve_label_aliases(requested: list[str], existing) -> list[str]:
    """요청한 라벨 중 레포에 없는 것은 별칭(한글/영문) 중 레포에 있는 이름으로 바꿔 돌려준다.

    레포에 이미 있는 이름은 그대로 둔다(정확히 같은 이름 우선). 별칭도 없으면 원문을 유지해
    호출자의 기존 '없는 라벨 걸러내기' 경로가 그대로 동작한다. 중복은 제거한다.
    """
    existing = set(existing)
    out: list[str] = []
    for name in requested:
        resolved = name
        if name not in existing:
            for group in LABEL_ALIAS_GROUPS:
                if name in group:
                    resolved = next((a for a in group if a in existing), name)
                    break
        if resolved not in out:
            out.append(resolved)
    return out


def list_labels(owner: str, repo: str, pat: str) -> list[str]:
    """레포의 라벨 이름 목록을 반환한다."""
    items = client._request("GET", f"{_API_BASE}/repos/{owner}/{repo}/labels?per_page=100", None, pat)
    return [item["name"] for item in items]


def get_issue_labels(owner: str, repo: str, issue_number: int, pat: str) -> list[str]:
    """이슈/PR에 현재 붙어 있는 라벨 이름 목록을 반환한다."""
    items = client._request(
        "GET",
        f"{_API_BASE}/repos/{owner}/{repo}/issues/{issue_number}/labels?per_page=100",
        None,
        pat,
    )
    return [item["name"] for item in items]


def add_issue_labels(owner: str, repo: str, issue_number: int, labels: list[str], pat: str) -> list[str]:
    """이슈/PR(GitHub API에선 둘 다 issue)에 라벨을 추가한다 (덮어쓰기 아님).

    PR도 GitHub API에서는 issue로 다뤄지므로 `/issues/{n}/labels`로 호출 가능.
    레포에 존재하지 않는 라벨은 사전 필터링해 422를 방지한다.
    반환: 이슈/PR에 현재 붙어 있는 모든 라벨 이름 리스트.
    적용할 라벨이 없으면 POST 없이 현재 라벨을 그대로 돌려준다 (빈 목록으로 오보하지 않는다 — #698).
    """
    if not labels:
        return client.get_issue_labels(owner, repo, issue_number, pat)
    existing = set(client.list_labels(owner, repo, pat))
    labels = client.resolve_label_aliases(labels, existing)
    filtered = [l for l in labels if l in existing]
    if not filtered:
        return client.get_issue_labels(owner, repo, issue_number, pat)
    items = client._request(
        "POST",
        f"{_API_BASE}/repos/{owner}/{repo}/issues/{issue_number}/labels",
        {"labels": filtered},
        pat,
    )
    return [item["name"] for item in items]


def remove_issue_label(
    owner: str, repo: str, issue_number: int, name: str, pat: str,
) -> dict:
    """이슈에서 라벨 하나만 제거한다 (나머지 라벨은 유지).

    라벨명은 URL 경로에 들어가므로 반드시 인코딩한다 (한글 라벨 `작업중` 등).
    이슈에 그 라벨이 없으면 404가 나므로 호출자가 멱등 처리한다.
    반환: 제거 후 이슈에 남은 라벨 이름 리스트.
    """
    # 한글/영문 별칭: 이슈에 실제로 붙어 있는 쪽 이름으로 제거한다 (#776)
    for group in LABEL_ALIAS_GROUPS:
        if name in group:
            on_issue = client.get_issue_labels(owner, repo, issue_number, pat)
            if name not in on_issue:
                name = next((a for a in group if a in on_issue), name)
            break
    enc = urllib.parse.quote(name, safe="")
    items = client._request(
        "DELETE",
        f"{_API_BASE}/repos/{owner}/{repo}/issues/{issue_number}/labels/{enc}",
        None,
        pat,
    )
    return {"labels": [item["name"] for item in items]}


def set_issue_labels(
    owner: str, repo: str, issue_number: int, labels: list[str], pat: str,
) -> dict:
    """이슈의 라벨을 통째로 교체한다 (기존 라벨 전부 제거 후 새 배열 적용).

    빈 배열을 명시하면 모든 라벨을 제거한다. 존재하지 않는 라벨은 사전 필터링해 422를 방지한다.
    단, 요청한 라벨이 있는데 전부 레포에 없어 걸러졌다면 PUT 하지 않는다 —
    빈 배열로 PUT 하면 기존 라벨(상태 라벨 등)이 조용히 사라지기 때문이다 (#698).
    반환: {"labels": 교체 후(또는 변경 없이 유지된) 라벨, "skipped": 걸러진 라벨, "unchanged": 변경 여부}.
    """
    skipped: list[str] = []
    if labels:
        existing = set(client.list_labels(owner, repo, pat))
        labels = client.resolve_label_aliases(labels, existing)
        skipped = [l for l in labels if l not in existing]
        labels = [l for l in labels if l in existing]
        if not labels:
            # 데이터 보존: 적용할 것이 하나도 없으면 기존 라벨을 건드리지 않는다
            current = client.get_issue_labels(owner, repo, issue_number, pat)
            return {"labels": current, "skipped": skipped, "unchanged": True}
    items = client._request(
        "PUT",
        f"{_API_BASE}/repos/{owner}/{repo}/issues/{issue_number}/labels",
        {"labels": labels},
        pat,
    )
    return {"labels": [item["name"] for item in items], "skipped": skipped, "unchanged": False}
