"""GitHub REST 전송 계층: 오류 타입, redirect 시 인증 헤더 제거, JSON·바이너리 요청."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from common import gh_client as client


_API_BASE = "https://api.github.com"


class GitHubAPIError(Exception):
    """GitHub API 요청 중 발생하는 에러."""
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(f"GitHub API {status_code}: {message}")
        self.status_code = status_code
        self.message = message
        # 응답 헤더(소문자 키). rate limit 판별에 쓴다 — request_json 이 채운다
        self.headers: dict[str, str] = {}


class GitHubNetworkError(Exception):
    """네트워크 단절·타임아웃 등 HTTP 응답 자체를 받지 못한 경우."""


class PyNaClMissingError(Exception):
    """Actions Secret 암호화에 필요한 PyNaCl을 사용할 수 없을 때 발생."""
    code = "pynacl_missing"


class _StripAuthRedirect(urllib.request.HTTPRedirectHandler):
    """redirect 시 Authorization 헤더를 제거한다.

    GitHub job logs 등 일부 엔드포인트는 Azure Blob(SAS URL)로 302 redirect되는데,
    urllib 기본 동작은 Authorization 헤더를 redirect 대상까지 전달한다.
    Azure는 이를 거부하고 403 AuthenticationFailed를 반환하므로 헤더를 제거해야 한다.
    """
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None:
            new.headers.pop("Authorization", None)
            new.unredirected_hdrs.pop("Authorization", None)
        return new


_opener = urllib.request.build_opener(_StripAuthRedirect)



def _error_message(e: urllib.error.HTTPError, body_bytes: bytes) -> str:
    """HTTP 오류 본문에서 사람이 읽을 메시지를 만든다.

    422 는 message 가 "Validation Failed" 뿐이고 실제 원인은 `errors` 배열(resource/field/code/message)에
    있다. 버리면 무엇이 틀렸는지 알 수 없어 함께 이어 붙인다 (#700).
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


# 요청 timeout(초) — 망이 끊겼을 때 무한 대기하지 않도록 모든 요청에 건다 (#700)
_DEFAULT_TIMEOUT = 30

# 일시 오류 재시도 (#941): 몇 번 더 시도하고 각 회차 전에 몇 초 기다리는지
_TRANSIENT_RETRY_WAITS_SECONDS = (1, 3)
# 서버 쪽 일시 오류 상태 코드
_TRANSIENT_HTTP_STATUS = (500, 502, 503, 504)
# 같은 요청을 다시 보내도 결과가 같은 메서드 — POST 는 중복 생성될 수 있어 제외한다
_IDEMPOTENT_METHODS = ("GET", "HEAD", "PUT", "PATCH", "DELETE")


def is_transient_error(error: BaseException) -> bool:
    """5xx 와 네트워크 단절은 일시 오류, 4xx 는 영구 오류 (#941)"""
    if isinstance(error, GitHubAPIError):
        return error.status_code in _TRANSIENT_HTTP_STATUS
    return isinstance(error, (urllib.error.URLError, TimeoutError, ConnectionError))


def _request(method: str, url: str, data: dict | None, pat: str, raw: bool = False,
             as_bytes: bool = False) -> Any:
    """GitHub API 요청을 보내고 응답을 반환한다.

    raw=False: 응답 본문을 JSON으로 파싱해 반환.
    raw=True: 디코딩한 텍스트(str)를 그대로 반환 (로그 등 비 JSON 응답용).
    as_bytes=True: 본문 바이트 그대로 반환 (zip 등 바이너리, raw 보다 우선, #987)
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
    """timeout 을 주고 네트워크 오류를 GitHubNetworkError 로 분리하는 공개 요청 헬퍼.

    `_request` 는 timeout 이 없어 망이 끊기면 무한 대기할 수 있고, 응답 헤더를 버려
    rate limit 과 권한 오류를 구분할 수 없다. 새 호출부는 이 함수를 쓴다.
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
        # 메시지에 요청 헤더(PAT)는 들어가지 않는다
        raise GitHubNetworkError(f"{type(e).__name__}: {e}") from e


def _upload_request(url: str, data: bytes, content_type: str, pat: str) -> dict:
    """바이너리 본문을 올린다.

    _request는 Content-Type이 application/json으로 고정돼 있어 자산 업로드에 쓸 수 없다.
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
