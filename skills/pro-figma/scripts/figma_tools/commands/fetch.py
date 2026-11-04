"""fetch: 저장된 Figma 토큰으로 REST 직접 조회 > MCP 덤프 모양 변환 > 덤프·메타 저장 (+ 선택: 시안 PNG)

MCP 연결 없이 토큰 하나로 끝난다. 저장은 ingest 와 같은 함수를 거친다.
"""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote

from common.emit import emit
from common.http import request
from figma_tools.commands.ingest import save_dump
from figma_tools.figma_auth import TOKEN_MISSING_OPTIONS, fetch_json, find_token
from figma_tools.rest_dump import rest_nodes_to_dump

# 노드 응답·이미지 내보내기 대기 (큰 화면은 Figma 쪽 렌더가 느림)
NODES_TIMEOUT_SECONDS = 120
EXPORT_TIMEOUT_SECONDS = 120


def _token_problem(code: str, error: str) -> dict:
    return {"ok": False, "code": code, "error": error, "options": TOKEN_MISSING_OPTIONS,
            "next": "Ask the user which option to take. Do not read or print any token yourself"}


def _rest_failure(response: dict, file_key: str) -> dict | None:
    """REST 응답 실패 > 오류 payload (성공이면 None)"""
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
                "error": (response.get("text") or "")[:300]}
    return None


def _export_png(file_key: str, node: str, token: str, scale: float, design_dir: Path) -> dict:
    """시안 PNG 내보내기: /images 로 주소 받기 > 받은 주소에서 내려받기 (주소에는 토큰 안 붙임)"""
    # use_absolute_bounds: 프레임 밖으로 넘친 내용·효과를 빼고 노드 크기 그대로 (앱 화면과 같은 틀)
    response = fetch_json(f"/images/{file_key}?ids={quote(node)}&format=png&scale={scale:g}"
                          "&use_absolute_bounds=true",
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
    target = design_dir / f"{node.replace(':', '-')}@{scale:g}x.png"
    target.write_bytes(download["raw"])
    return {"ok": True, "path": str(target), "bytes": len(download["raw"]), "scale": scale}


def cmd_fetch(args) -> int:
    token, token_source = find_token()
    if not token:
        return emit(_token_problem("figma_token_missing",
                                   "No Figma token found (FIGMA_TOKEN or a saved figma credential)"))

    # 노드 조회 (depth 없음: 잘린 덤프는 잘렸다는 표시가 없다)
    response = fetch_json(f"/files/{args.file_key}/nodes?ids={quote(args.node)}", token,
                          NODES_TIMEOUT_SECONDS)
    failure = _rest_failure(response, args.file_key)
    if failure:
        return emit(failure)
    body = response["json"]
    if not (body.get("nodes") or {}).get(args.node):
        return emit({"ok": False, "code": "node_not_found",
                     "error": f"Node {args.node} is not in file {args.file_key}",
                     "hint": "Link node-id 238-1846 is node 238:1846. Check the id, or ask the user"})

    dump_dir = Path(args.dump_dir)
    dump_dir.mkdir(parents=True, exist_ok=True)
    # 저장 전 MCP 덤프 모양으로 (coverage · assets · conform 이 같은 모양을 읽음)
    text = json.dumps(rest_nodes_to_dump(body, args.node), ensure_ascii=False, indent=1)
    result = save_dump(text, "json", args.file_key, args.node, dump_dir, f"rest:{token_source}")
    if result.get("ok") is False:
        return emit(result)

    # 선택: 대조 기준 PNG (실패해도 덤프는 남긴다)
    if args.design_dir:
        export = _export_png(args.file_key, args.node, token, args.scale, Path(args.design_dir))
        result["design_export"] = export
        if not export.get("ok"):
            result["warnings"].append({"code": export.get("code", "export_failed"),
                                       "message": export.get("error", "")})
    result["summary"] = f"Fetched {args.node} from Figma. " + result["summary"]
    return emit(result)
