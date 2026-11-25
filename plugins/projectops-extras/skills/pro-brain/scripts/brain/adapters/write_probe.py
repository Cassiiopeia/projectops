"""Reversible write probe for a remote brain: put a fixed test page > read it back > delete it
One fixed slug per project (pro-brain/<project>/_doctor), so a brain without a delete tool keeps one page, never a pile.
"""
from __future__ import annotations

import uuid

from .. import collect, http_client, mcp_http, note_file
from .base import check

PROBE_NOTE_ID = "_doctor"
DELETE_TOOL = "delete_page"


def probe_slug(project: str) -> str:
    return note_file.note_slug(project, PROBE_NOTE_ID)


def _probe_content(checked_at: str) -> str:
    return ("---\ntitle: pro-brain doctor write check\ntype: doctor-probe\n---\n"
            f"Written by brain_cli.py doctor at {checked_at} to prove this token can write. Safe to delete.\n")


def _has_delete_tool(session, tool_names: list[str], can_request_tools: bool) -> bool:
    """delete_page listed, or unlocked through request_tools (starter surfaces hide it)"""
    if DELETE_TOOL in tool_names:
        return True
    if not can_request_tools:
        return False
    try:
        answer = session.call_tool("request_tools", {"tools": [DELETE_TOOL]})
    except mcp_http.McpError:
        return False
    tools = (answer.get("data") or {}).get("tools") if isinstance(answer.get("data"), dict) else None
    return isinstance(tools, list) and any(isinstance(tool, dict) and tool.get("name") == DELETE_TOOL for tool in tools)


def run_write_probe(session, project: str, tool_names: list[str], can_request_tools: bool, revision_of) -> dict:
    """{check row, verified (bool)}: put_page > get_page > delete_page; revision_of(session, slug) > (revision, error)"""
    slug = probe_slug(project)
    revision, error = revision_of(session, slug)
    if error:
        return {"verified": False, "check": check("write_probe", "fail", f"get_page before the probe failed ({error})",
                                                  "brain_cli.py doctor again; check the brain server logs",
                                                  code="write_probe_failed", slug=slug)}
    arguments = {"slug": slug, "content": _probe_content(collect.now_seoul().isoformat(timespec="seconds")),
                 "content_origin": "inferred", "reason": "pro-brain doctor write check", "request_id": str(uuid.uuid4())}
    if revision:
        arguments["expected_revision"] = revision
    try:
        answer = session.call_tool("put_page", arguments)
    except mcp_http.McpError as problem:
        return {"verified": False, "check": check("write_probe", "fail", f"put_page failed: {problem.message}",
                                                  "ask the brain admin for a read+write key, or read via sync "
                                                  "(setup --team-model sync)", code="read_only_token", slug=slug)}
    if answer["is_error"]:
        text = http_client.mask_text(answer["text"][:200], [])
        return {"verified": False, "check": check("write_probe", "fail", f"put_page refused: {text}",
                                                  "ask the brain admin for a read+write key, or read via sync "
                                                  "(setup --team-model sync)", code="read_only_token", slug=slug)}
    read_back, read_error = revision_of(session, slug)
    if read_error or not read_back:
        return {"verified": False, "check": check("write_probe", "fail", "put_page answered, but the page could not be read back",
                                                  "check the brain server logs (write may not persist)",
                                                  code="write_not_persisted", slug=slug)}
    cleanup = "left"
    if _has_delete_tool(session, tool_names, can_request_tools):
        try:
            deleted = session.call_tool(DELETE_TOOL, {"slug": slug})
            cleanup = "deleted" if not deleted["is_error"] else "delete_refused"
        except mcp_http.McpError:
            cleanup = "delete_refused"
    detail = {"deleted": f"wrote, read back and deleted the test page {slug}",
              "left": f"wrote and read back {slug}; the brain offers no delete tool, so that one page stays "
                      "(the next probe overwrites it; skip with --no-write-probe)",
              "delete_refused": f"wrote and read back {slug}; delete was refused, so that one page stays "
                                "(the next probe overwrites it)"}[cleanup]
    return {"verified": True, "check": check("write_probe", "ok", detail, slug=slug, cleanup=cleanup)}
