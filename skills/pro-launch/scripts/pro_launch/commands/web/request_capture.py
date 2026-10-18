"""조작이 일으킨 요청 기록 — `--capture-requests` (click · press · type · script, #930).

"저장" 이 정말 서버로 갔는지(`POST 200 …/applications/…`) 보려고 agent 가 page.on("response") 훅을 손으로 썼다.
GET · HEAD · OPTIONS 는 뺀다(읽기 · 사전 확인이라 저장 여부와 무관하고 수가 많다).
주소: 조각(#) 버림 · 비밀스러운 이름의 쿼리 값 가림 · 길이 자름. 본문은 싣지 않는다.
"""
from __future__ import annotations

import re
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# 기록에서 빼는 메서드
_SKIPPED_METHODS = {"GET", "HEAD", "OPTIONS"}
# 이름에 이 글자가 든 쿼리 값은 가린다 (토큰 · 키 · 서명 · 인증 코드)
_SECRET_QUERY_NAME = re.compile(r"token|key|secret|pass|auth|code|sig|session|credential|otp", re.IGNORECASE)
MASK = "***"
MAXIMUM_URL_CHARS = 200
MAXIMUM_REQUESTS = 50
# 조작 뒤 진행 중인 요청이 끝나길 기다리는 상한(초) · 확인 간격(ms)
SETTLE_SECONDS = 3
SETTLE_POLL_MILLISECONDS = 100


def clean_url(url: str) -> str:
    """주소 > 기록용 주소 (조각 버림 · 비밀 쿼리 값 *** · 200자)"""
    try:
        parts = urlsplit(url)
        query = urlencode([(name, MASK if _SECRET_QUERY_NAME.search(name) else value)
                           for name, value in parse_qsl(parts.query, keep_blank_values=True)], safe="*")
        cleaned = urlunsplit((parts.scheme, parts.netloc, parts.path, query, ""))
    except ValueError:
        cleaned = url
    return cleaned if len(cleaned) <= MAXIMUM_URL_CHARS else cleaned[:MAXIMUM_URL_CHARS] + "…"


class RequestCapture:
    """페이지에 귀를 달고 GET 이 아닌 요청의 끝(응답 · 실패)을 모은다."""

    def __init__(self) -> None:
        self.records: list[dict] = []
        self.pending: set = set()
        self.page = None

    def attach(self, page) -> "RequestCapture":
        self.page = page
        page.on("request", self._on_request)
        page.on("response", self._on_response)
        page.on("requestfailed", self._on_failed)
        return self

    def _on_request(self, request) -> None:
        if request.method not in _SKIPPED_METHODS:
            self.pending.add(request)

    def _on_response(self, response) -> None:
        request = response.request
        if request.method in _SKIPPED_METHODS:
            return
        self.pending.discard(request)
        self._record({"method": request.method, "status": response.status, "url": clean_url(response.url)})

    def _on_failed(self, request) -> None:
        if request.method in _SKIPPED_METHODS:
            return
        self.pending.discard(request)
        self._record({"method": request.method, "status": None, "url": clean_url(request.url),
                      "failure": str(request.failure or "")[:120]})

    def _record(self, record: dict) -> None:
        if len(self.records) < MAXIMUM_REQUESTS:
            self.records.append(record)

    def finish(self) -> list[dict]:
        """진행 중인 요청이 끝나길 잠깐 기다리고 > 귀를 떼고 > 기록을 돌려준다 (끝나지 않은 것은 status None · pending)"""
        page = self.page
        deadline = time.monotonic() + SETTLE_SECONDS
        try:
            while self.pending and time.monotonic() < deadline:
                page.wait_for_timeout(SETTLE_POLL_MILLISECONDS)
        except Exception:
            pass  # 탭이 닫혔다 — 모은 것까지만
        for request in list(self.pending)[:MAXIMUM_REQUESTS - len(self.records)]:
            self.records.append({"method": request.method, "status": None, "url": clean_url(request.url),
                                 "pending": True})
        for event, handler in (("request", self._on_request), ("response", self._on_response),
                               ("requestfailed", self._on_failed)):
            try:
                page.remove_listener(event, handler)
            except Exception:
                pass  # 이미 닫힌 페이지
        return self.records
