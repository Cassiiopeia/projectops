"""check-fresh: ingest 때 기록한 lastModified 와 Figma 의 현재 값을 비교"""
from __future__ import annotations

import json
from pathlib import Path

from common.emit import emit
from figma_tools.commands.ingest import META_SUFFIX
from figma_tools.figma_auth import TOKEN_MISSING_OPTIONS, fetch_file_state, find_token


def _token_problem(code: str, error: str) -> dict:
    """토큰이 없거나 거부됐을 때 — 에이전트가 사용자에게 방식을 묻도록 선택지를 싣는다."""
    return {"ok": False, "code": code, "verdict": "unknown", "error": error,
            "options": TOKEN_MISSING_OPTIONS,
            "next": "Ask the user which option to take. Do not read or print any token yourself"}


def cmd_check_fresh(args) -> int:
    dump = Path(args.dump)
    meta_path = Path(str(dump) + META_SUFFIX)
    if not meta_path.is_file():
        return emit({"ok": False, "code": "meta_not_found",
                     "error": f"No ingest metadata next to {args.dump}",
                     "hint": "The dump was not saved with ingest. Run ingest on the get_figma_data result first"})
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return emit({"ok": False, "code": "meta_unreadable", "error": str(e)})

    recorded = {"last_modified": meta.get("last_modified"), "version": meta.get("version")}
    if not recorded["last_modified"]:
        return emit({"verdict": "unknown", "recorded": recorded,
                     "summary": "No lastModified was recorded at ingest, so nothing to compare",
                     "next": "Register a token (token --prompt), then ingest again"})

    token, _source = find_token()
    if not token:
        return emit(_token_problem("figma_token_missing", "No Figma token found (FIGMA_TOKEN or a saved figma credential)"))
    state = fetch_file_state(meta["file_key"], token)
    if not state.get("ok"):
        code = state["code"]
        if code == "figma_token_rejected":
            return emit(_token_problem(code, "Figma rejected the token (expired or lacks file read access)"))
        if code == "figma_file_not_found":
            return emit({"ok": False, "code": code, "verdict": "unknown",
                         "error": f"Figma file {meta['file_key']} not found for this token",
                         "next": "Check the file key and that the token's account can open the file"})
        # 네트워크 문제로 작업을 막지 않는다 — 모른다고만 알린다
        return emit({"verdict": "unknown", "recorded": recorded, "reason": code,
                     "summary": "Could not reach Figma; the design may or may not have changed",
                     "next": "Retry later, or continue and say the change check was skipped"})

    current = {"last_modified": state["lastModified"], "version": state["version"]}
    is_changed = (current["last_modified"] != recorded["last_modified"]
                  or (recorded["version"] and current["version"] and current["version"] != recorded["version"]))
    if is_changed:
        node_arg = f" --node {meta['node_id']}" if meta.get("node_id") else ""
        return emit({"verdict": "design_changed", "recorded": recorded, "current": current,
                     "summary": "The Figma file changed after the dump was saved",
                     "next": f"Fetch get_figma_data again, ingest it again, then re-run coverage --dump <new dump>{node_arg}"})
    return emit({"verdict": "fresh", "recorded": recorded, "current": current,
                 "summary": "The design has not changed since the dump was saved",
                 "next": "Continue"})
