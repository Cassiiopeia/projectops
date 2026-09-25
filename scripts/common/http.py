"""단건 HTTP 요청 (pro-launch `http` · pro-agent-test `api` 공용, #631).

표준 라이브러리만 쓴다 — 폐쇄망에서도 pip 없이 돌아야 한다.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request


def request(method: str, url: str, headers: dict | None = None,
            data: bytes | None = None, timeout: int = 30) -> dict:
    """한 요청을 보낸다. 실패 응답(4xx·5xx)도 결과다 — 예외로 끝내지 않는다.

    권한 없음·토큰 만료 같은 실패 응답 자체가 검증 대상인 경우가 많다.
    반환: ok(응답을 받았나) · status · headers · json · text · raw · elapsed_ms
    """
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    started = time.time()
    try:
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
