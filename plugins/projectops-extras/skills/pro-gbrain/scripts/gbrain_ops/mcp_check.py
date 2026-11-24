"""End-to-end check of a team brain with a throwaway read-only token:
initialize 200 > search answers (hit when notes exist) > write refused > revoke > initialize 401.
The token lives in memory only; output carries statuses and verdicts, never a body or the token.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from . import common

REQUEST_TIMEOUT_SECONDS = 30
USER_AGENT = "projectops-pro-gbrain-verify/1"
PROTOCOL_VERSION = "2025-06-18"
# Tool names tried in order (gbrain versions differ); the first one tools/list offers wins
SEARCH_TOOL_NAMES = ("search", "query", "recall")
WRITE_TOOL_NAMES = ("put_page", "remember")
# Page the write probe would create if the token wrongly allowed writes (reported so the admin can remove it)
WRITE_PROBE_SLUG = "pro-gbrain/verify-write-probe"


class McpSession:
    def __init__(self, url: str, token: str):
        self.url = url
        self.token = token
        self.session_id = None
        self.next_id = 1

    def call(self, method: str, params: dict | None = None, is_notification: bool = False) -> tuple[int | None, dict]:
        message = {"jsonrpc": "2.0", "method": method, **({"params": params} if params is not None else {})}
        if not is_notification:
            message["id"] = self.next_id
            self.next_id += 1
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
                   "User-Agent": USER_AGENT, "Authorization": f"Bearer {self.token}"}
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
            headers["MCP-Protocol-Version"] = PROTOCOL_VERSION
        request = urllib.request.Request(self.url, data=json.dumps(message).encode("utf-8"), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                self.session_id = response.headers.get("Mcp-Session-Id") or self.session_id
                return response.status, _parse_body(response.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as error:
            return error.code, {}
        except (urllib.error.URLError, OSError, ValueError):
            return None, {}


def _parse_body(text: str) -> dict:
    """JSON body or the last `data:` line of an SSE stream"""
    text = text.strip()
    if not text:
        return {}
    if text.startswith("{"):
        try:
            return json.loads(text)
        except ValueError:
            return {}
    payloads = [line[5:].strip() for line in text.splitlines() if line.startswith("data:")]
    for payload in reversed(payloads):
        try:
            return json.loads(payload)
        except ValueError:
            continue
    return {}


def _is_tool_error(body: dict) -> bool:
    return "error" in body or bool((body.get("result") or {}).get("isError"))


def _has_content(body: dict) -> bool:
    content = (body.get("result") or {}).get("content") or []
    text = " ".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
    return bool(text.strip()) and text.strip() not in ("[]", "{}", "No results", "no results")


def check_team_brain(url: str, token: str, query: str) -> dict:
    """Checks with a valid read-only token (before revoking). Each check: passed true/false + short detail"""
    session = McpSession(url, token)
    checks = {}
    status, body = session.call("initialize", {"protocolVersion": PROTOCOL_VERSION, "capabilities": {},
                                               "clientInfo": {"name": USER_AGENT, "version": "1"}})
    checks["initialize"] = {"passed": status == 200 and "result" in body, "status": status}
    if not checks["initialize"]["passed"]:
        return checks
    session.call("notifications/initialized", is_notification=True)
    _, listed = session.call("tools/list", {})
    tool_names = [tool.get("name") for tool in (listed.get("result") or {}).get("tools") or [] if isinstance(tool, dict)]

    # Search: a hit is expected once notes exist (a new brain is empty > warning only)
    search_tool = next((name for name in SEARCH_TOOL_NAMES if name in tool_names), None)
    if search_tool:
        _, found = session.call("tools/call", {"name": search_tool, "arguments": {"query": query}})
        checks["search"] = {"passed": not _is_tool_error(found), "tool": search_tool, "has_hit": _has_content(found)}
    else:
        checks["search"] = {"passed": False, "detail": "no search tool offered", "tools_offered": len(tool_names)}

    # Write refused: passes when the tool is not offered or the call errors (on success, report the probe page)
    write_tool = next((name for name in WRITE_TOOL_NAMES if name in tool_names), WRITE_TOOL_NAMES[0])
    write_arguments = ({"slug": WRITE_PROBE_SLUG, "content": "pro-gbrain write probe"} if write_tool == "put_page"
                       else {"fact": "pro-gbrain write probe", "visibility": "world"})
    write_status, written = session.call("tools/call", {"name": write_tool, "arguments": write_arguments})
    refused = write_status in (401, 403) or _is_tool_error(written) or write_tool not in tool_names
    checks["write_refused"] = {"passed": refused, "tool": write_tool, "listed": write_tool in tool_names}
    if not refused:
        checks["write_refused"]["probe_slug"] = WRITE_PROBE_SLUG
    return checks


def check_revoked(url: str, token: str) -> dict:
    status, _ = McpSession(url, token).call("initialize", {"protocolVersion": PROTOCOL_VERSION, "capabilities": {},
                                                          "clientInfo": {"name": USER_AGENT, "version": "1"}})
    return {"passed": status == 401, "status": status}


def run_verification(provisioner, project: str, mcp_url: str) -> dict:
    """Issue a throwaway token > checks > revoke (always, even after a failed check) > 401 check"""
    token_name = f"pro-gbrain-verify-{common.compact_timestamp()}"
    issued = provisioner.issue_read_only_token(project, token_name)
    secret, token_id = issued.get("secret"), issued.get("token_id")
    if not secret or not token_id:
        raise common.StepError("verify_token_missing", "the brain server returned no token",
                               "check the token API of the brain server")
    url = mcp_url or issued.get("mcp_url")
    checks = {}
    try:
        checks = check_team_brain(url, secret, project)
    finally:
        provisioner.revoke_token(project, token_id)   # (success and failure alike)
    checks["revoked_refused"] = check_revoked(url, secret)
    is_passed = all(check.get("passed") for check in checks.values())
    return {"passed": is_passed, "token_name": token_name, "scopes": issued.get("scopes"), "checks": checks,
            "warnings": ([] if checks.get("search", {}).get("has_hit")
                         else ["search answered but found nothing: normal for a brain with no synced notes yet"])}
