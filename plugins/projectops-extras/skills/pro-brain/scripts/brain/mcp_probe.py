"""Team brain URL probe: does the URL answer like a real brain? (catches a mistyped brain key before anyone uses it)
Two MCP initialize calls: no token (expect 401) and a dummy token (expect 401 invalid token, not 404 unknown brain).
Never sends a real token; only status codes and a short matched phrase are returned, never the response body.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

PROBE_TIMEOUT_SECONDS = 10
# Deliberately invalid bearer value: a real brain must reject it with 401
PROBE_DUMMY_TOKEN = "projectops-probe-not-a-real-token"
# Phrases in a 401 body that mean "the brain exists, the token is wrong"
INVALID_TOKEN_PHRASES = ("invalid token", "invalid_token", "invalid bearer", "unauthorized")
RESPONSE_BYTES_READ = 2048
# Named client: some proxies (e.g. Cloudflare bot rules) answer 403 to the default Python-urllib agent
PROBE_USER_AGENT = "projectops-pro-brain-probe/1"
INITIALIZE_REQUEST = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                      "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                                 "clientInfo": {"name": "projectops-pro-brain-probe", "version": "1"}}}


def send_initialize(url: str, bearer: str | None) -> tuple[int | None, str]:
    """POST initialize > (status or None when unreachable, first bytes of the body lower-cased)"""
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
               "User-Agent": PROBE_USER_AGENT}
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    request = urllib.request.Request(url, data=json.dumps(INITIALIZE_REQUEST).encode("utf-8"), headers=headers,
                                     method="POST")
    try:
        with urllib.request.urlopen(request, timeout=PROBE_TIMEOUT_SECONDS) as response:
            return response.status, response.read(RESPONSE_BYTES_READ).decode("utf-8", "replace").lower()
    except urllib.error.HTTPError as error:
        try:
            body = error.read(RESPONSE_BYTES_READ).decode("utf-8", "replace").lower()
        except OSError:
            body = ""
        return error.code, body
    except (urllib.error.URLError, OSError, ValueError):
        return None, ""


def _name_hints(url: str, mcp_name: str | None, project: str | None) -> list[str]:
    """Soft hint: the URL names neither the project nor the MCP name suffix (typo-prone brain keys)"""
    if not mcp_name:
        return []
    suffix = mcp_name.split("-", 1)[1] if "-" in mcp_name else mcp_name
    lowered = url.lower()
    if suffix.lower() in lowered or (project and project.lower() in lowered):
        return []
    return [f"the URL contains neither '{suffix}' nor the project name: check the brain key in the URL"]


def probe_team_brain(url: str, mcp_name: str | None = None, project: str | None = None, send=send_initialize) -> dict:
    """Verdict: brain_answers | unknown_brain | no_auth | blocked | unreachable | unexpected (+ statuses and hints)"""
    anonymous_status, _ = send(url, None)
    dummy_status, dummy_body = send(url, PROBE_DUMMY_TOKEN)
    result = {"url": url, "status_without_token": anonymous_status, "status_with_dummy_token": dummy_status,
              "hints": _name_hints(url, mcp_name, project)}
    if anonymous_status is None and dummy_status is None:
        return {**result, "verdict": "unreachable", "ok": False,
                "summary": "the URL did not answer (DNS, network or TLS): check the host part"}
    if 404 in (anonymous_status, dummy_status):
        return {**result, "verdict": "unknown_brain", "ok": False,
                "summary": "the URL answers 404: wrong path or brain key; compare it with the brain admin's URL"}
    if anonymous_status is not None and 200 <= anonymous_status < 300:
        return {**result, "verdict": "no_auth", "ok": False,
                "summary": "the URL answers without a token: the brain is open to anyone, tell the brain admin"}
    if anonymous_status == 403 and dummy_status == 403:
        return {**result, "verdict": "blocked", "ok": False,
                "summary": "403 for both calls: a proxy or firewall in front of the brain refused the probe; check by hand"}
    if anonymous_status == 401 and dummy_status == 401:
        phrase = next((text for text in INVALID_TOKEN_PHRASES if text in dummy_body), None)
        return {**result, "verdict": "brain_answers", "ok": True, "matched_phrase": phrase,
                "summary": "the URL answers like a brain: 401 without a token and 401 for an invalid token"}
    return {**result, "verdict": "unexpected", "ok": False,
            "summary": f"unexpected answers ({anonymous_status} / {dummy_status}): check the URL with the brain admin"}
