"""GitHub REST transport layer: error types, auth header stripped on redirect, JSON and binary requests."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from common import gh_client as client


_API_BASE = "https://api.github.com"


class GitHubAPIError(Exception):
    """Error raised during a GitHub API request."""
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(f"GitHub API {status_code}: {message}")
        self.status_code = status_code
        self.message = message
        # Response headers (lowercase keys). Used to detect rate limits; filled by request_json
        self.headers: dict[str, str] = {}


class GitHubNetworkError(Exception):
    """No HTTP response received at all, e.g. network drop or timeout."""


class PyNaClMissingError(Exception):
    """Raised when PyNaCl, needed for Actions secret encryption, is unavailable."""
    code = "pynacl_missing"


class _StripAuthRedirect(urllib.request.HTTPRedirectHandler):
    """Strip the Authorization header on redirect.

    Some endpoints, like GitHub job logs, 302-redirect to Azure Blob (SAS URL), and
    urllib by default forwards the Authorization header to the redirect target.
    Azure rejects that with 403 AuthenticationFailed, so the header must be removed.
    """
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None:
            new.headers.pop("Authorization", None)
            new.unredirected_hdrs.pop("Authorization", None)
        return new


_opener = urllib.request.build_opener(_StripAuthRedirect)



def _error_message(e: urllib.error.HTTPError, body_bytes: bytes) -> str:
    """Build a human-readable message from an HTTP error body.

    For 422 the message is just "Validation Failed" and the real cause is in the `errors` array (resource/field/code/message).
    Dropping it hides what was wrong, so it is appended (#700).
    """
    try:
        payload = json.loads(body_bytes)
    except Exception:
        return body_bytes.decode("utf-8", "replace")[:200] or str(e)
    if not isinstance(payload, dict):
        return body_bytes.decode("utf-8", "replace")[:200] or str(e)
    msg = payload.get("message", str(e))
    details = []
    for item in payload.get("errors") or []:
        if isinstance(item, dict):
            parts = [str(item[k]) for k in ("resource", "field", "code", "message") if item.get(k)]
            if parts:
                details.append("/".join(parts))
        elif item:
            details.append(str(item))
    if details:
        msg = f"{msg} ({'; '.join(details)})"
    return msg


# Request timeout (seconds): set on every request so a dropped network does not wait forever (#700)
_DEFAULT_TIMEOUT = 30

# Transient error retry (#941): how many extra tries and how many seconds to wait before each
_TRANSIENT_RETRY_WAITS_SECONDS = (1, 3)
# Server-side transient error status codes
_TRANSIENT_HTTP_STATUS = (500, 502, 503, 504)
# Methods that give the same result when resent; POST is excluded because it may create duplicates
_IDEMPOTENT_METHODS = ("GET", "HEAD", "PUT", "PATCH", "DELETE")


def is_transient_error(error: BaseException) -> bool:
    """5xx and network drops are transient, 4xx is permanent (#941)"""
    if isinstance(error, GitHubAPIError):
        return error.status_code in _TRANSIENT_HTTP_STATUS
    return isinstance(error, (urllib.error.URLError, TimeoutError, ConnectionError))


def _request(method: str, url: str, data: dict | None, pat: str, raw: bool = False,
             as_bytes: bool = False) -> Any:
    """Send a GitHub API request and return the response.

    raw=False: parse the response body as JSON and return it.
    raw=True: return the decoded text (str) as is (for non-JSON responses like logs).
    as_bytes=True: return the body bytes as is (binary like zip, takes precedence over raw, #987)
    """
    waits = _TRANSIENT_RETRY_WAITS_SECONDS if method in _IDEMPOTENT_METHODS else ()
    attempt = 0
    while True:
        try:
            return _send_once(method, url, data, pat, raw, as_bytes)
        except (GitHubAPIError, urllib.error.URLError, TimeoutError, ConnectionError) as error:
            if attempt >= len(waits) or not is_transient_error(error):
                raise
            client._sleep(waits[attempt])
            attempt += 1


def _send_once(method: str, url: str, data: dict | None, pat: str, raw: bool, as_bytes: bool = False) -> Any:
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {pat}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "projectops",
        },
    )
    try:
        with client._opener.open(req, timeout=client._DEFAULT_TIMEOUT) as resp:
            content = resp.read()
            if as_bytes:
                return content
            if not content:
                return {} if not raw else ""
            if raw:
                return content.decode("utf-8", "replace")
            return json.loads(content.decode())
    except urllib.error.HTTPError as e:
        body_bytes = e.fp.read() if e.fp else b""
        msg = _error_message(e, body_bytes)
        raise GitHubAPIError(e.code, msg) from e



def request_json(method: str, url: str, data: dict | None, pat: str, timeout: float = 20) -> Any:
    """Public request helper that sets a timeout and separates network errors into GitHubNetworkError.

    `_request` has no timeout, so it can wait forever on a dropped network, and it discards response headers,
    so rate limits cannot be told apart from permission errors. New callers use this function.
    """
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {pat}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "projectops",
        },
    )
    try:
        with client._opener.open(req, timeout=timeout) as resp:
            content = resp.read()
            return json.loads(content.decode()) if content else {}
    except urllib.error.HTTPError as e:
        body_bytes = e.fp.read() if e.fp else b""
        msg = _error_message(e, body_bytes)
        err = GitHubAPIError(e.code, msg)
        err.headers = {k.lower(): v for k, v in (e.headers or {}).items()}
        raise err from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        # The message never includes request headers (PAT)
        raise GitHubNetworkError(f"{type(e).__name__}: {e}") from e


def _upload_request(url: str, data: bytes, content_type: str, pat: str) -> dict:
    """Upload a binary body.

    _request fixes Content-Type to application/json, so it cannot be used for asset uploads.
    """
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={
            "Authorization": f"Bearer {pat}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": content_type,
            "Content-Length": str(len(data)),
            "User-Agent": "projectops",
        },
    )
    try:
        with client._opener.open(req) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.fp.read() if e.fp else b""
        raise GitHubAPIError(e.code, _error_message(e, body)) from e
