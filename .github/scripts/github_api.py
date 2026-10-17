#!/usr/bin/env python3
"""GitHub REST 호출 공통 (#914) — stdlib 전용.

워크플로가 부르는 스크립트(changelog_notice·issue_helper·close_issues_on_release·
pr_summary_comment·dispatch_downstream·store_deploy_config)가 함께 쓴다.
인증 헤더·timeout·redirect 처리·마커 댓글 갱신을 한 곳에서 정한다.

사용자 레포로 파일 단위 복사된다 — src/core/copy/simple.js 복사 목록에 함께 있어야 한다.
"""
from __future__ import annotations

import json
import urllib.request

API_ROOT = "https://api.github.com"
# 응답이 없을 때 워크플로 job 이 무한 대기하지 않도록 모든 호출에 건다
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_USER_AGENT = "projectops"
# 댓글 목록 조회 상한 (100개 × 10쪽) — 댓글이 아주 많은 이슈에서도 멈추도록
COMMENTS_PER_PAGE = 100
DEFAULT_MAX_COMMENT_PAGES = 10


class StripAuthorizationOnRedirect(urllib.request.HTTPRedirectHandler):
    """redirect 대상(Azure Blob SAS URL 등)에 토큰을 넘기지 않는다 — 넘기면 403·토큰 노출."""

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
    """요청 1건 > (HTTP 상태, JSON 본문 또는 None). 2xx 가 아니면 urllib.error.HTTPError."""
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
    """요청 1건 > JSON 본문(빈 응답이면 None)."""
    return send(method, url, token, payload, **options)[1]


def list_issue_comments(repo: str, number: int, token: str, *, request_function=request,
                        max_pages: int = DEFAULT_MAX_COMMENT_PAGES) -> list:
    """이슈·PR 댓글 전체 (페이지 순회, max_pages 상한)."""
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
    """본문에 marker 가 든 첫 댓글. 없으면 None."""
    return next((c for c in comments if marker in (c.get("body") or "")), None)


def upsert_marker_comment(repo: str, number: int, token: str, body: str, marker: str, *,
                          request_function=request, find_function=None,
                          max_pages: int = DEFAULT_MAX_COMMENT_PAGES) -> tuple[str, object]:
    """마커 댓글 갱신, 없으면 생성 > ("updated" | "created", 댓글 id).

    갱신은 알림이 가지 않으므로 같은 안내가 반복돼도 이메일은 처음 한 번만 간다.
    request_function: 호출부 테스트가 모킹한 함수를 그대로 쓰기 위한 주입점
    find_function: (comments) > 기존 댓글 — 구 마커까지 찾아야 하는 호출부용
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
