"""screens: 링크 노드(또는 파일 전체) 아래 화면 목록 > 묶음(페이지·섹션) 경로 + id·크기

사용자가 "무슨 화면이 있어?"라고 물을 때 쓰는 목록. 화면 하나를 고르면 fetch 로 가져온다.
"""
from __future__ import annotations

from urllib.parse import quote

from common.emit import emit
from figma_tools.commands.fetch import _rest_failure, _token_problem
from figma_tools.figma_auth import fetch_json, find_token

# 화면을 담는 묶음 노드 (안으로 들어가서 찾는다). GROUP 은 제외: 섹션 안 그룹은 아이콘·조각 묶음
CONTAINER_TYPES = ("DOCUMENT", "CANVAS", "SECTION")
# 화면으로 치는 노드
SCREEN_TYPES = ("FRAME", "COMPONENT", "COMPONENT_SET", "INSTANCE")
# 묶음 깊이 한도: 페이지 > 섹션 > 하위 섹션 > 화면
DEFAULT_DEPTH = 4
LIST_TIMEOUT_SECONDS = 120


def _collect_screens(node: dict, path: list[str], screens: list[dict]) -> None:
    """묶음은 안으로, 화면은 목록에 (화면 안쪽은 보지 않음)"""
    for child in node.get("children") or []:
        child_type = child.get("type")
        if child_type in SCREEN_TYPES:
            box = child.get("absoluteBoundingBox") or {}
            screens.append({"id": child.get("id"), "name": child.get("name"), "type": child_type,
                            "group": " / ".join(path), "width": box.get("width"),
                            "height": box.get("height"), "hidden": child.get("visible") is False})
        elif child_type in CONTAINER_TYPES:
            _collect_screens(child, path + [child.get("name") or child.get("id")], screens)


def _group_counts(screens: list[dict]) -> list[dict]:
    counts: dict[str, int] = {}
    for screen in screens:
        counts[screen["group"]] = counts.get(screen["group"], 0) + 1
    return [{"group": group, "screen_count": count} for group, count in counts.items()]


def cmd_screens(args) -> int:
    token, _source = find_token()
    if not token:
        return emit(_token_problem("figma_token_missing",
                                   "No Figma token found (FIGMA_TOKEN or a saved figma credential)"))
    # 노드 지정 > 그 노드만, 없으면 파일 전체 (depth 로 화면 안쪽은 받지 않음)
    if args.node:
        response = fetch_json(f"/files/{args.file_key}/nodes?ids={quote(args.node)}&depth={args.depth}",
                              token, LIST_TIMEOUT_SECONDS)
    else:
        response = fetch_json(f"/files/{args.file_key}?depth={args.depth}", token, LIST_TIMEOUT_SECONDS)
    failure = _rest_failure(response, args.file_key)
    if failure:
        return emit(failure)
    body = response["json"]
    if args.node:
        root = ((body.get("nodes") or {}).get(args.node) or {}).get("document")
        if not root:
            return emit({"ok": False, "code": "node_not_found",
                         "error": f"Node {args.node} is not in file {args.file_key}",
                         "hint": "Link node-id 238-1846 is node 238:1846"})
    else:
        root = body.get("document") or {}

    screens: list[dict] = []
    if root.get("type") in SCREEN_TYPES:
        _collect_screens({"children": [root]}, [], screens)
    else:
        _collect_screens(root, [root.get("name") or ""] if args.node else [], screens)
    groups = _group_counts(screens)
    return emit({
        "file": body.get("name"), "file_key": args.file_key, "node_id": args.node,
        "last_modified": body.get("lastModified"),
        "screen_count": len(screens), "groups": groups, "screens": screens,
        "summary": f"{len(screens)} screen(s) in {len(groups)} group(s)",
        "next": ("Show the user the groups and screen names, let them pick one, then "
                 f"fetch --file-key {args.file_key} --node <screen id> --dump-dir <dump> --design-dir <design>"),
    })
