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
        return {"code": "network", "summary": f"네트워크 오류: {e}",
                "next": "네트워크 연결을 확인하고 같은 명령을 다시 실행한다"}
    status = getattr(e, "status_code", 0)
    h = getattr(e, "headers", None) or {}
    msg = str(getattr(e, "message", e))
    if status in (403, 429) and (h.get("x-ratelimit-remaining") == "0" or "retry-after" in h
                                 or "rate limit" in msg.lower() or status == 429):
        when = _reset_when(h.get("x-ratelimit-reset"))
        wait = h.get("retry-after")
        hint = f"{when} 이후" if when else (f"{wait}초 뒤" if wait else "잠시 뒤")
        return {"code": "rate_limited", "summary": f"GitHub API 호출 한도 초과: {msg}",
                "next": f"{hint} 같은 명령을 다시 실행한다. 대상 레포를 나눠 호출 수를 줄인다"}
    nxt = {
        401: "PAT 가 만료되었거나 잘못됐다. /pro-github 로 PAT 를 다시 등록한다",
        403: "PAT 에 이 레포를 읽을 권한(repo 범위)이 없다. 권한을 확인한다",
        404: "레포 이름에 오타가 있거나, 비공개 레포인데 PAT 에 접근 권한이 없다. 둘 다 확인한다",
        410: "이 기능이 꺼진 레포다 (예: 이슈 비활성). 해당 사실은 '없음'이 아니라 '꺼져 있음'으로 다룬다",
    }.get(status, "오류 메시지를 확인하고 입력을 고쳐 다시 실행한다")
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
