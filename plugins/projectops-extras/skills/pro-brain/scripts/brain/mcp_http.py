"""Minimal MCP client over streamable HTTP: initialize > tools/list > tools/call (JSON or SSE answers, session header)
The token is only ever placed in the Authorization header; errors are masked before they leave this module.
"""
from __future__ import annotations

import json

from . import http_client

PROTOCOL_VERSION = "2025-06-18"
CLIENT_INFO = {"name": "projectops-pro-brain", "version": http_client.plugin_version()}
SESSION_HEADER = "mcp-session-id"


class McpError(Exception):
    """code: unreachable | proxy_refused | unauthorized | forbidden | not_found | http_error | rpc_error | bad_response"""

    def __init__(self, code: str, message: str, status: int | None = None):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def parse_rpc_body(body: str, request_id: int) -> dict | None:
    """JSON body or SSE 'data:' lines > the JSON-RPC message answering request_id"""
    text = body.strip()
    candidates = []
    if text.startswith("{"):
        candidates.append(text)
    else:
        candidates += [line[5:].strip() for line in text.splitlines() if line.startswith("data:")]
    for candidate in candidates:
        try:
            message = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(message, dict) and message.get("id") == request_id:
            return message
    return None


def classify_status(status: int | None, body: str) -> str | None:
    if status is None:
        return "unreachable"
    if http_client.is_proxy_refusal(status, body):
        return "proxy_refused"
    return {401: "unauthorized", 403: "forbidden", 404: "not_found"}.get(status) if status >= 400 else None


class McpSession:
    """One MCP session against url with bearer (token kept in memory only)"""

    def __init__(self, url: str, bearer: str | None, post=http_client.post_json):
        self.url, self._bearer, self._post = url, bearer, post
        self.session_id: str | None = None
        self._next_id = 0
        self.server_info: dict = {}

    def _send(self, method: str, params: dict | None = None, is_notification: bool = False) -> dict | None:
        payload = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        if not is_notification:
            self._next_id += 1
            payload["id"] = self._next_id
        extra = {SESSION_HEADER: self.session_id} if self.session_id else {}
        if self.session_id:
            extra["MCP-Protocol-Version"] = PROTOCOL_VERSION
        answer = self._post(self.url, payload, self._bearer, extra)
        code = classify_status(answer["status"], answer["body"])
        if code:
            detail = answer["error"] or f"HTTP {answer['status']}"
            raise McpError(code, http_client.mask_text(f"{method}: {detail}", [self._bearer or ""]), answer["status"])
        session = answer["headers"].get(SESSION_HEADER)
        if session:
            self.session_id = session
        if is_notification:
            return None
        message = parse_rpc_body(answer["body"], payload["id"])
        if message is None:
            raise McpError("bad_response", f"{method}: no JSON-RPC answer", answer["status"])
        if "error" in message:
            error = message["error"] or {}
            raise McpError("rpc_error", http_client.mask_text(f"{method}: {error.get('message')}", [self._bearer or ""]),
                           answer["status"])
        return message.get("result") or {}

    def initialize(self) -> dict:
        result = self._send("initialize", {"protocolVersion": PROTOCOL_VERSION, "capabilities": {},
                                           "clientInfo": CLIENT_INFO})
        self.server_info = result.get("serverInfo") or {}
        self._send("notifications/initialized", is_notification=True)
        return result

    def list_tool_names(self) -> list[str]:
        names, cursor = [], None
        for _ in range(20):   # pagination guard
            result = self._send("tools/list", {"cursor": cursor} if cursor else {})
            names += [tool.get("name") for tool in result.get("tools") or [] if isinstance(tool, dict)]
            cursor = result.get("nextCursor")
            if not cursor:
                break
        return names

    def call_tool(self, name: str, arguments: dict) -> dict:
        """tools/call > {is_error, data (parsed JSON text when possible), text}"""
        result = self._send("tools/call", {"name": name, "arguments": arguments})
        texts = [item.get("text", "") for item in result.get("content") or [] if isinstance(item, dict)]
        text = "\n".join(texts)
        data = result.get("structuredContent")
        if data is None:
            try:
                data = json.loads(text) if text.strip().startswith(("{", "[")) else None
            except ValueError:
                data = None
        return {"is_error": bool(result.get("isError")), "data": data, "text": text}
