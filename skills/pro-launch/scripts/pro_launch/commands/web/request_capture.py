"""Record of requests an action caused — `--capture-requests` (click, press, type, script, #930).

To see whether "save" really reached the server (`POST 200 …/applications/…`), the agent wrote page.on("response") hooks by hand.
GET, HEAD and OPTIONS are excluded (reads and preflights are unrelated to saving and numerous).
URL: fragment (#) dropped, query values with secret-looking names masked, length truncated. Bodies are not included.
"""
from __future__ import annotations

import re
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Methods excluded from the record
_SKIPPED_METHODS = {"GET", "HEAD", "OPTIONS"}
# Query values whose name contains these are masked (token, key, signature, auth code)
_SECRET_QUERY_NAME = re.compile(r"token|key|secret|pass|auth|code|sig|session|credential|otp", re.IGNORECASE)
MASK = "***"
MAXIMUM_URL_CHARS = 200
MAXIMUM_REQUESTS = 50
# Limit (seconds) for waiting on in-flight requests after the action, and poll interval (ms)
SETTLE_SECONDS = 3
SETTLE_POLL_MILLISECONDS = 100


def clean_url(url: str) -> str:
    """URL > URL for the record (fragment dropped, secret query values ***, 200 chars)"""
    try:
        parts = urlsplit(url)
        query = urlencode([(name, MASK if _SECRET_QUERY_NAME.search(name) else value)
                           for name, value in parse_qsl(parts.query, keep_blank_values=True)], safe="*")
        cleaned = urlunsplit((parts.scheme, parts.netloc, parts.path, query, ""))
    except ValueError:
        cleaned = url
    return cleaned if len(cleaned) <= MAXIMUM_URL_CHARS else cleaned[:MAXIMUM_URL_CHARS] + "…"


class RequestCapture:
    """Listen on the page and collect the end (response, failure) of non-GET requests."""

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
        """Briefly wait for in-flight requests to finish > stop listening > return the record (unfinished ones get status None, pending)"""
        page = self.page
        deadline = time.monotonic() + SETTLE_SECONDS
        try:
            while self.pending and time.monotonic() < deadline:
                page.wait_for_timeout(SETTLE_POLL_MILLISECONDS)
        except Exception:
            pass  # tab closed — keep what was collected
        for request in list(self.pending)[:MAXIMUM_REQUESTS - len(self.records)]:
            self.records.append({"method": request.method, "status": None, "url": clean_url(request.url),
                                 "pending": True})
        for event, handler in (("request", self._on_request), ("response", self._on_response),
                               ("requestfailed", self._on_failed)):
            try:
                page.remove_listener(event, handler)
            except Exception:
                pass  # page already closed
        return self.records
