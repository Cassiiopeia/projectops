"""HTTP for pro-brain: one named User-Agent, Authorization stripped on redirect, proxy refusal detection, value masking
Every brain HTTP call (probe, MCP session) goes through post_json so a proxy rule or a leaked secret is handled once.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from pathlib import Path

HTTP_TIMEOUT_SECONDS = 20
RESPONSE_BYTES_READ = 1_000_000
# plugin.json of projectops-extras: scripts/brain/http_client.py > parents[4]
PLUGIN_MANIFEST = Path(__file__).resolve().parents[4] / ".claude-plugin" / "plugin.json"
# Cloudflare "error code: 1010" = the browser signature (User-Agent) was banned by the site owner
PROXY_BAN_PATTERNS = (re.compile(r"error code:?\s*1010"), re.compile(r"cloudflare"), re.compile(r"access denied"))
USERINFO_PATTERN = re.compile(r"(//)[^/@\s]+@")
SECRET_QUERY_PATTERN = re.compile(r"((?:token|key|secret|password|passwd|apikey|api_key)=)[^&\s\"']+", re.IGNORECASE)


def plugin_version() -> str:
    try:
        return str(json.loads(PLUGIN_MANIFEST.read_text(encoding="utf-8")).get("version") or "dev")
    except (OSError, ValueError):
        return "dev"


# Named generic client: Cloudflare bot rules answer 403 / 1010 to the default Python-urllib agent
USER_AGENT = f"projectops-pro-brain/{plugin_version()}"


def mask_url(url: str | None) -> str | None:
    """Connection URL > same URL with the whole userinfo and secret query values replaced (never partial)"""
    if not url:
        return url
    return SECRET_QUERY_PATTERN.sub(r"\1<secret>", USERINFO_PATTERN.sub(r"\1<userinfo>@", str(url)))


def mask_text(text: str | None, secret_values: list[str]) -> str:
    """Free text > secrets, URL userinfo and bearer values replaced"""
    masked = str(text or "")
    for value in secret_values:
        if value:
            masked = masked.replace(value, "<token>")
    masked = re.sub(r"(Bearer\s+)[A-Za-z0-9._~+/=-]{8,}", r"\1<token>", masked)
    return mask_url(masked) or ""


class _StripAuthRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None:
            new.headers.pop("Authorization", None)
            new.unredirected_hdrs.pop("Authorization", None)
        return new


_OPENER = urllib.request.build_opener(_StripAuthRedirect)


def is_proxy_refusal(status: int | None, body: str) -> bool:
    """403 (or 1010 body) from a proxy in front of the brain rather than the brain itself"""
    lowered = (body or "").lower()
    if "error code: 1010" in lowered or "error code 1010" in lowered:
        return True
    return status == 403 and any(pattern.search(lowered) for pattern in PROXY_BAN_PATTERNS)


def post_json(url: str, payload: dict, bearer: str | None = None, extra_headers: dict | None = None,
              timeout: int = HTTP_TIMEOUT_SECONDS) -> dict:
    """POST JSON > {status, headers, body, error}; status None when unreachable (body never includes the token)"""
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
               "User-Agent": USER_AGENT, **(extra_headers or {})}
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    request = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    try:
        with _OPENER.open(request, timeout=timeout) as response:
            body = response.read(RESPONSE_BYTES_READ).decode("utf-8", "replace")
            return {"status": response.status, "headers": {key.lower(): value for key, value in response.headers.items()},
                    "body": body, "error": None}
    except urllib.error.HTTPError as error:
        try:
            body = error.read(RESPONSE_BYTES_READ).decode("utf-8", "replace")
        except OSError:
            body = ""
        return {"status": error.code, "headers": {key.lower(): value for key, value in (error.headers or {}).items()},
                "body": body, "error": f"HTTP {error.code}"}
    except (urllib.error.URLError, OSError, ValueError) as error:
        return {"status": None, "headers": {}, "body": "", "error": mask_text(str(getattr(error, "reason", error)), [bearer or ""])}
