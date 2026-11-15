"""Single HTTP request (shared by pro-launch `http` and pro-agent-test `api`, #631).

Standard library only — must run on closed networks without pip.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request

# Put '%' in the safe set so already-encoded %XX stays untouched
_PATH_SAFE = "/%:@!$&'()*+,;=~"
_QUERY_SAFE = "=&%+,;:@/?!$'()*~"


def encode_url(url: str) -> str:
    """Percent-encode non-ASCII text (e.g. Hangul) and spaces in path and query (#703).

    urllib rejects URLs with non-ASCII characters or spaces. Already-encoded %XX is kept.
    """
    parts = urllib.parse.urlsplit(url)
    netloc = parts.netloc
    if not netloc.isascii():
        # Non-ASCII domains go out as punycode, not percent-encoding
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
    """Send one request. Failure responses (4xx/5xx) are results too — not exceptions.

    Failure responses such as no permission or expired token are often what is being checked.
    Returns: ok (got a response) · status · headers · json · text · raw · elapsed_ms
    """
    started = time.time()
    try:
        # A bad address (no scheme etc.) raises ValueError here — return it as a result dict
        req = urllib.request.Request(encode_url(url), data=data, method=method,
                                     headers=headers or {})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            status, rh = resp.status, dict(resp.headers.items())
    except urllib.error.HTTPError as e:
        raw = e.fp.read() if e.fp else b""
        status, rh = e.code, dict(e.headers.items()) if e.headers else {}
    except Exception as e:  # when the network itself fails
        return {"ok": False, "code": "request_failed", "url": url, "error": str(e),
                "next": "The network call itself failed (no HTTP status). Check the connection, proxy or VPN, then retry once",
                "elapsed_ms": int((time.time() - started) * 1000)}
    text = raw.decode("utf-8", "replace")
    try:
        parsed = json.loads(text) if text.strip() else None
    except json.JSONDecodeError:
        parsed = None
    return {"ok": True, "url": url, "status": status, "headers": rh, "json": parsed,
            "text": None if parsed is not None else text[:4000], "raw": raw,
            "elapsed_ms": int((time.time() - started) * 1000)}
