"""fetch: query REST directly with the saved Figma token > convert to MCP dump shape > save dump·meta (+ optional: design PNG)

Done with a single token, no MCP connection. Saving goes through the same function as ingest.
"""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote

from common.emit import emit
from common.http import request
from figma_tools.commands.ingest import save_dump
from figma_tools.figma_auth import TOKEN_MISSING_OPTIONS, fetch_json, find_token
from figma_tools.rest_dump import node_fingerprint, rest_nodes_to_dump

# Wait for node response · image export (Figma renders large screens slowly)
NODES_TIMEOUT_SECONDS = 120
EXPORT_TIMEOUT_SECONDS = 120


def _token_problem(code: str, error: str) -> dict:
    return {"ok": False, "code": code, "error": error, "options": TOKEN_MISSING_OPTIONS,
            "next": "Ask the user which option to take. Do not read or print any token yourself"}


def _rest_failure(response: dict, file_key: str) -> dict | None:
    """REST response failure > error payload (None on success)"""
    if not response.get("ok"):
        return {"ok": False, "code": "request_failed", "error": response.get("error", ""),
                "next": "Retry later; check the network"}
    status = response["status"]
    if status in (401, 403):
        return _token_problem("figma_token_rejected",
                              "Figma rejected the token (expired or lacks file read access)")
    if status == 404:
        return {"ok": False, "code": "figma_file_not_found",
                "error": f"Figma file {file_key} not found for this token",
                "next": "Check the file key and that the token's account can open the file"}
    if status != 200 or not isinstance(response.get("json"), dict):
        return {"ok": False, "code": "request_failed", "status": status,
                "error": (response.get("text") or "")[:300],
                "next": "429: wait a minute and retry. 5xx: Figma is failing, retry later. No status: check the network"}
    return None


def _version_query(version: str | None) -> str:
    """For fetching a past design (id from Figma version history). None means the current design"""
    return f"&version={quote(version)}" if version else ""


def _export_png(file_key: str, node: str, token: str, scale: float, design_dir: Path,
                version: str | None = None) -> dict:
    """Export design PNG: get URL from /images > download from it (no token on that URL)"""
    # use_absolute_bounds: node size as is, without content·effects overflowing the frame (same frame as the app screen)
    response = fetch_json(f"/images/{file_key}?ids={quote(node)}&format=png&scale={scale:g}"
                          "&use_absolute_bounds=true" + _version_query(version),
                          token, EXPORT_TIMEOUT_SECONDS)
    failure = _rest_failure(response, file_key)
    if failure:
        return failure
    image_url = (response["json"].get("images") or {}).get(node)
    if not image_url:
        return {"ok": False, "code": "export_failed",
                "error": response["json"].get("err") or "Figma returned no image for this node"}
    download = request("GET", image_url, timeout=EXPORT_TIMEOUT_SECONDS)
    if not download.get("ok") or download["status"] != 200 or not download.get("raw"):
        return {"ok": False, "code": "export_failed", "error": "Could not download the exported PNG"}
    design_dir.mkdir(parents=True, exist_ok=True)
    suffix = f"_v{version}" if version else ""
    target = design_dir / f"{node.replace(':', '-')}{suffix}@{scale:g}x.png"
    target.write_bytes(download["raw"])
    return {"ok": True, "path": str(target), "bytes": len(download["raw"]), "scale": scale}


def cmd_fetch(args) -> int:
    token, token_source = find_token()
    if not token:
        return emit(_token_problem("figma_token_missing",
                                   "No Figma token found (FIGMA_TOKEN or a saved figma credential)"))

    # Node query (no depth: a truncated dump has no truncation marker)
    response = fetch_json(f"/files/{args.file_key}/nodes?ids={quote(args.node)}"
                          + _version_query(args.version), token, NODES_TIMEOUT_SECONDS)
    failure = _rest_failure(response, args.file_key)
    if failure:
        return emit(failure)
    body = response["json"]
    if not (body.get("nodes") or {}).get(args.node):
        return emit({"ok": False, "code": "node_not_found",
                     "error": f"Node {args.node} is not in file {args.file_key}",
                     "hint": "Link node-id 238-1846 is node 238:1846. Check the id, or ask the user"})

    # Past versions get their own folder (so the current dump is not overwritten)
    dump_dir = Path(args.dump_dir) / f"v{args.version}" if args.version else Path(args.dump_dir)
    dump_dir.mkdir(parents=True, exist_ok=True)
    # Convert to MCP dump shape before saving (coverage · assets · conform read the same shape)
    text = json.dumps(rest_nodes_to_dump(body, args.node), ensure_ascii=False, indent=1)
    result = save_dump(text, "json", args.file_key, args.node, dump_dir, f"rest:{token_source}",
                       node_fingerprint(body, args.node))
    if result.get("ok") is False:
        return emit(result)

    # Optional: reference PNG for comparison (the dump stays even if this fails)
    if args.design_dir:
        export = _export_png(args.file_key, args.node, token, args.scale, Path(args.design_dir),
                             args.version)
        result["design_export"] = export
        if not export.get("ok"):
            result["warnings"].append({"code": export.get("code", "export_failed"),
                                       "message": export.get("error", "")})
    result["summary"] = f"Fetched {args.node} from Figma. " + result["summary"]
    return emit(result)
