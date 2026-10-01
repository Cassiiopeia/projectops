"""단건 HTTP 요청 (pro-launch `http` · pro-agent-test `api` 공용, #631).

표준 라이브러리만 쓴다 — 폐쇄망에서도 pip 없이 돌아야 한다.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request

# 이미 인코딩된 %XX 는 건드리지 않도록 '%' 를 안전 문자에 넣는다
_PATH_SAFE = "/%:@!$&'()*+,;=~"
_QUERY_SAFE = "=&%+,;:@/?!$'()*~"


def encode_url(url: str) -> str:
    """경로·쿼리의 한글·공백을 퍼센트 인코딩한다 (#703).

    urllib 은 ascii 가 아닌 문자·공백이 든 URL 을 거부한다. 이미 인코딩된 %XX 는 유지한다.
    """
    parts = urllib.parse.urlsplit(url)
    netloc = parts.netloc
    if not netloc.isascii():
        # 한글 도메인은 퍼센트가 아니라 punycode 로 보낸다
        host, sep, port = netloc.rpartition(":")
        if not sep or not port.isdigit():
            host, port = netloc, ""
        try:
            host = host.encode("idna").decode("ascii")
        except UnicodeError:
            pass
        netloc = host + (":" + port if port else "")
    return urllib.parse.urlunsplit((
        parts.scheme, netloc,
        urllib.parse.quote(parts.path, safe=_PATH_SAFE),
        urllib.parse.quote(parts.query, safe=_QUERY_SAFE),
        urllib.parse.quote(parts.fragment, safe=_QUERY_SAFE)))


def request(method: str, url: str, headers: dict | None = None,
            data: bytes | None = None, timeout: int = 30) -> dict:
    """한 요청을 보낸다. 실패 응답(4xx·5xx)도 결과다 — 예외로 끝내지 않는다.

    권한 없음·토큰 만료 같은 실패 응답 자체가 검증 대상인 경우가 많다.
    반환: ok(응답을 받았나) · status · headers · json · text · raw · elapsed_ms
    """
    started = time.time()
    try:
        # 잘못된 주소(스킴 없음 등)는 여기서 ValueError 가 난다 — 결과 dict 로 돌려준다
        req = urllib.request.Request(encode_url(url), data=data, method=method,
                                     headers=headers or {})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            status, rh = resp.status, dict(resp.headers.items())
    except urllib.error.HTTPError as e:
        raw = e.fp.read() if e.fp else b""
        status, rh = e.code, dict(e.headers.items()) if e.headers else {}
    except Exception as e:  # 네트워크 자체가 안 될 때
        return {"ok": False, "code": "request_failed", "url": url, "error": str(e),
                "elapsed_ms": int((time.time() - started) * 1000)}
    text = raw.decode("utf-8", "replace")
    try:
        parsed = json.loads(text) if text.strip() else None
    except json.JSONDecodeError:
        parsed = None
    return {"ok": True, "url": url, "status": status, "headers": rh, "json": parsed,
            "text": None if parsed is not None else text[:4000], "raw": raw,
            "elapsed_ms": int((time.time() - started) * 1000)}
