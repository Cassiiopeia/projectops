"""PR: 목록·수정·생성(head 반영 지연 재시도)·머지·상세, deploy PR 찾기, 브랜치 HEAD."""

from __future__ import annotations

import time
import urllib.parse

from common import gh_client as client
from common.github_rest.transport import _API_BASE, GitHubAPIError


def list_pulls(
    owner: str, repo: str, pat: str, state: str = "open",
) -> list[dict]:
    """PR 목록을 조회한다."""
    items = client._request(
        "GET",
        f"{_API_BASE}/repos/{owner}/{repo}/pulls?state={state}&per_page=50",
        None,
        pat,
    )
    return [
        {"number": i["number"], "title": i["title"], "url": i["html_url"], "state": i["state"]}
        for i in items
    ]


def update_pull_request(
    owner: str, repo: str, pr_number: int, pat: str,
    title: str | None = None, body: str | None = None,
    state: str | None = None, base: str | None = None,
) -> dict:
    """PR을 수정하고 {number, url}을 반환한다. PR 본문(릴리스 노트) 업데이트 등에 사용."""
    payload: dict = {}
    if title is not None:
        payload["title"] = title
    if body is not None:
        payload["body"] = body
    if state is not None:
        payload["state"] = state
    if base is not None:
        payload["base"] = base
    data = client._request(
        "PATCH", f"{_API_BASE}/repos/{owner}/{repo}/pulls/{pr_number}", payload, pat
    )
    return {"number": data["number"], "url": data["html_url"]}


# push 직후 head 가 GitHub 쪽에 아직 반영되지 않아 나는 일시 오류의 재시도 횟수·간격(초) (#724)
_PR_HEAD_RETRIES = 3
_PR_HEAD_WAIT = 3
_sleep = time.sleep  # 테스트가 실제로 기다리지 않게 주입 가능하도록 분리


def create_pull_request(
    owner: str, repo: str, title: str, body: str,
    head: str, base: str, pat: str,
) -> dict:
    """PR을 생성하고 {number, url}을 반환한다.

    브랜치를 push 한 직후에는 `422 PullRequest/head/invalid` 가 일시적으로 나는 경우가 있어
    그 오류만 짧게 재시도한다. 이미 PR 이 있는 경우 등 다른 422 는 재시도하지 않는다.
    """
    attempt = 0
    while True:
        try:
            data = client._request(
                "POST",
                f"{_API_BASE}/repos/{owner}/{repo}/pulls",
                {"title": title, "body": body, "head": head, "base": base},
                pat,
            )
            return {"number": data["number"], "url": data["html_url"]}
        except GitHubAPIError as e:
            transient = e.status_code == 422 and "head/invalid" in e.message
            if not transient or attempt >= client._PR_HEAD_RETRIES:
                raise
            attempt += 1
            client._sleep(client._PR_HEAD_WAIT)


def merge_pull_request(
    owner: str, repo: str, pr_number: int, pat: str,
    merge_method: str = "merge", commit_title: str | None = None,
    commit_message: str | None = None, sha: str | None = None,
) -> dict:
    """PR을 머지한다.

    merge_method: merge(기본) / squash / rebase.
    머지 불가(405)·sha 불일치(409)·rebase 불허(422)는 GitHubAPIError로 올라오므로
    호출자(CLI 레이어)가 status_code로 verdict를 판정한다.
    반환: {sha, merged, message}.
    """
    payload: dict = {"merge_method": merge_method}
    if commit_title is not None:
        payload["commit_title"] = commit_title
    if commit_message is not None:
        payload["commit_message"] = commit_message
    if sha is not None:
        payload["sha"] = sha
    data = client._request(
        "PUT",
        f"{_API_BASE}/repos/{owner}/{repo}/pulls/{pr_number}/merge",
        payload,
        pat,
    )
    return {
        "sha": data.get("sha"),
        "merged": data.get("merged", False),
        "message": data.get("message"),
    }


def get_pull_detail(owner: str, repo: str, pr_number: int, pat: str) -> dict:
    """단일 PR 상세에서 머지 판정에 필요한 필드를 추출한다.

    list_pulls에는 body·mergeable_state가 없어 deploy-status 검증용으로 별도 조회한다.
    """
    pr = client._request("GET", f"{_API_BASE}/repos/{owner}/{repo}/pulls/{pr_number}", None, pat)
    return {
        "number": pr["number"],
        "state": pr["state"],
        "merged": pr.get("merged", False),
        "mergeable_state": pr.get("mergeable_state"),
        "body": pr.get("body") or "",
        "head_sha": pr.get("head", {}).get("sha"),
        "url": pr["html_url"],
        "created_at": pr.get("created_at"),
        "updated_at": pr.get("updated_at"),
    }


# deploy PR 후보에서 제외할 봇 브랜치 접두사. 의존성 봇 PR도 기본 브랜치(main)로 들어오므로
# base만 보면 deploy PR로 오인해 "기존 PR 재사용"이 그 PR 본문을 덮어쓴다.
_BOT_HEAD_PREFIXES = ("dependabot/", "renovate/")


def find_open_pr_by_base(owner: str, repo: str, base: str, pat: str, head: str | None = None) -> dict | None:
    """base 브랜치로 들어오는 open PR 중 deploy PR 하나의 상세를 반환한다. 없으면 None.

    deploy-status를 --pr 없이 호출할 때 deploy PR을 자동으로 찾기 위함.
    - head를 주면 그 브랜치에서 온 PR만 고른다 (가장 정확).
    - head가 없으면 의존성 봇(dependabot/, renovate/) PR을 제외한 첫 번째를 고른다.
    """
    items = client._request(
        "GET",
        f"{_API_BASE}/repos/{owner}/{repo}/pulls?state=open&base={base}&per_page=50",
        None, pat,
    )
    for it in items or []:
        ref = (it.get("head") or {}).get("ref", "")
        if head:
            if ref != head:
                continue
        elif ref.startswith(_BOT_HEAD_PREFIXES):
            continue
        return client.get_pull_detail(owner, repo, it["number"], pat)
    return None


def get_ahead_by(owner: str, repo: str, base: str, head: str, pat: str) -> int | None:
    """base 보다 head 가 앞선 커밋 수 (릴리스할 것이 있는지). 비교 못 하면 None (#945)"""
    pair = f"{urllib.parse.quote(base, safe='/')}...{urllib.parse.quote(head, safe='/')}"
    try:
        data = client._request("GET", f"{_API_BASE}/repos/{owner}/{repo}/compare/{pair}", None, pat)
    except GitHubAPIError:
        return None
    ahead = data.get("ahead_by")
    return ahead if isinstance(ahead, int) else None


def get_branch_head(owner: str, repo: str, branch: str, pat: str) -> str | None:
    """브랜치 HEAD SHA를 반환한다. 브랜치가 없으면 None (404를 None으로 흡수)."""
    enc = urllib.parse.quote(branch, safe="/")
    try:
        ref = client._request("GET", f"{_API_BASE}/repos/{owner}/{repo}/git/ref/heads/{enc}", None, pat)
    except GitHubAPIError as e:
        if e.status_code == 404:
            return None
        raise
    return ref.get("object", {}).get("sha")
