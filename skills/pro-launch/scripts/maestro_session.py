"""Resident iOS Maestro session (#894 phase 2) — state file · client that calls the relay · response reading.

The CLI is a process that ends on every call, so nothing can hold a STDIO MCP server. So one relay process
owns the stdio of `maestro mcp` and forwards requests received over 127.0.0.1 TCP (standard library only).

  app session start   > start relay > check tool names (tools/list) > warm up device connection > state file ready
  app tap·swipe·tree·run > call() > relay > tools/call (warm: run 0.7-1 s · inspect_screen 0.1 s, observed)
  idle N min · app session stop > relay exits together with maestro mcp

State file: {PROJECTOPS_HOME}/launch/maestro-sessions/<UDID>.json (mode 600 — holds the access token)
Secret input (type) does not go this way: maestro mcp echoes env values in plaintext in run responses (observed on 2.10.0),
and a resident process's log location cannot be redirected to a temp folder per call.

The relay process itself is maestro_session_relay.py (runs standalone). This module is state file · client · response reading.
This module also imports only the standard library at top level — the relay imports it.
"""
from __future__ import annotations

import json
import os
import re
import socket
from pathlib import Path

import maestro_runs
# app_input calls it only via maestro_session (app_input line count is frozen — no room for a new import)
from maestro_runs import run_recorded  # noqa: F401

# State file folder name (under the launch state root, one file per device)
SESSION_FOLDER_NAME = "maestro-sessions"
DEFAULT_IDLE_MINUTES = 20
# logical name > candidate tool names per version (names differed by Maestro version: run_flow → run)
TOOL_CANDIDATES = {"run": ("run", "run_flow"), "inspect": ("inspect_screen", "inspect_view_hierarchy")}
# Client connect wait (s)
CLIENT_CONNECT_TIMEOUT_SECONDS = 3


# ── State file (client side) ─────────────────────────────────────────────

def session_folder() -> Path:
    from common.state import base_dir   # the relay is standalone, so import only here
    return base_dir() / "launch" / SESSION_FOLDER_NAME


def session_file(device: str) -> Path:
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", device)
    return session_folder() / f"{safe_name}.json"


def read_session(device: str) -> dict | None:
    """Session state of the device. None if the file is missing or broken."""
    try:
        data = json.loads(session_file(device).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def write_session(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.chmod(temporary, 0o600)   # access token — owner-readable only
    os.replace(temporary, path)


def is_ready(session: dict | None) -> bool:
    return bool(session and session.get("status") == "ready" and session.get("port") and session.get("token"))


# ── Client ───────────────────────────────────────────────────────────

def request(session: dict, payload: dict, timeout_seconds: float) -> dict:
    """One-line JSON request to the relay > one-line JSON response. Connect failures and timeouts raise as OSError."""
    with socket.create_connection(("127.0.0.1", int(session["port"])), timeout=CLIENT_CONNECT_TIMEOUT_SECONDS) as conn:
        conn.settimeout(timeout_seconds)
        conn.sendall((json.dumps({**payload, "token": session["token"]}) + "\n").encode("utf-8"))
        received = b""
        while not received.endswith(b"\n"):
            chunk = conn.recv(65536)
            if not chunk:
                break
            received += chunk
    if not received.strip():
        raise ConnectionError("relay closed the connection without a reply")
    return json.loads(received.decode("utf-8"))


def call(device: str, tool: str, arguments: dict, timeout_seconds: float) -> tuple[dict | None, str | None]:
    """Call a tool through the session > (result, None). No session gives (None, None) — the current path as is.

    If a session exists but could not be used, (None, reason) — the caller falls back to the per-call path and keeps the reason in the response.
    Result: {"is_error": bool, "text": str, "reconnected": bool}
    """
    session = read_session(device)
    if session is None:
        return None, None
    if not is_ready(session):
        return None, "session_not_ready"
    try:
        with maestro_runs.recording():
            reply = request(session, {"op": "call", "tool": tool, "arguments": arguments,
                                      "timeout_seconds": timeout_seconds}, timeout_seconds + 30)
    except ConnectionRefusedError:
        # No relay (killed · rebooted) — clear the leftover state file
        try:
            session_file(device).unlink()
        except OSError:
            pass
        return None, "session_gone"
    except socket.timeout:
        return None, "session_timeout"
    except (OSError, ValueError):
        return None, "session_unreachable"
    if not reply.get("ok"):
        return None, str(reply.get("reason") or "session_call_failed")
    return {"is_error": bool(reply.get("is_error")), "text": str(reply.get("text") or ""),
            "reconnected": bool(reply.get("reconnected"))}, None


def flow_outcome(result: dict) -> tuple[bool, list[str]]:
    """run tool result > (success, output lines). Failure text example: 'Failed to run flow: Element not found: ...'"""
    text = result["text"]
    if result["is_error"]:
        return False, [line for line in text.splitlines() if line.strip()] or ["maestro mcp run failed"]
    try:
        body = json.loads(text)
    except ValueError:
        return True, [text]
    # Responses sometimes carry env_vars — never emit them as lines
    is_success = bool(body.get("success", True)) if isinstance(body, dict) else True
    message = body.get("message", "") if isinstance(body, dict) else ""
    return is_success, [message] if message else []


def resolve_tool_names(available: list[str]) -> tuple[dict[str, str], list[str]]:
    """Tool names the server has > ({logical name: actual name}, logical names not found)."""
    mapping, missing = {}, []
    for logical, candidates in TOOL_CANDIDATES.items():
        found = next((name for name in candidates if name in available), None)
        if found:
            mapping[logical] = found
        else:
            missing.append(logical)
    return mapping, missing


def inspect_screen_to_hierarchy(json_text: str) -> str:
    """inspect_screen response (short keys b·txt·rid·a11y·c) > JSON shaped like `maestro hierarchy`. Empty string if unreadable."""
    try:
        body = json.loads(json_text)
    except ValueError:
        return ""
    if not isinstance(body, dict):
        return ""
    # The short-key table comes from the response's ui_schema — follows changes across versions
    full_name_by_short = {"b": "bounds", "txt": "text", "rid": "resource-id", "a11y": "accessibilityText", "c": "children"}
    full_name_by_short.update((body.get("ui_schema") or {}).get("abbreviations") or {})

    def expand(element: dict) -> dict:
        named = {full_name_by_short.get(k, k): v for k, v in element.items()}
        children = named.pop("children", None) or []
        return {"attributes": named, "children": [expand(c) for c in children if isinstance(c, dict)]}

    return json.dumps({"attributes": {}, "children": [expand(e) for e in body.get("elements") or [] if isinstance(e, dict)]})
