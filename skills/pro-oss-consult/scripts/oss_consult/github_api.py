"""GitHub API 통로: 오류 분류, HTTP 호출 단일 통로(_call), 목록·파일·라벨·README 조회, PAT 조회
테스트는 이 모듈의 _call·_pat 을 대체한다 (명령 모듈은 모듈 속성으로 불러 대체가 반영됨)
"""
from __future__ import annotations

import base64
import time
import urllib.parse

from common import gh_client

_API = "https://api.github.com"
# 망이 끊기면 무한 대기하지 않도록 모든 HTTP 호출에 건다
_TIMEOUT = 20

# ── 오류 분류 (순수 — 테스트 대상) ───────────────────────────────────────

def _reset_when(reset: str | None) -> str | None:
    try:
        return time.strftime("%H:%M:%S", time.localtime(int(reset)))
    except (TypeError, ValueError):
        return None


def classify_api_error(e: Exception) -> dict:
    """GitHub 오류를 code/summary/next 로 풀어 준다. rate limit 과 권한 오류를 구분한다."""
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


# ── 네트워크 ─────────────────────────────────────────────────────────────

def _call(method: str, path: str, pat: str, data: dict | None = None):
    """모든 HTTP 호출의 단일 통로 — timeout·네트워크 오류 분리. 테스트는 이 함수를 대체한다."""
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
    """라벨 전체 레코드. 페이지 상한(500개)에 닿으면 capped=True."""
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
