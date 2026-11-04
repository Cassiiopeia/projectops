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


# 링크 종류 > 에이전트가 이어서 할 일 (사람마다 파일 전체 · 페이지 · 섹션 · 화면 · 부품 링크를 줌)
LINK_KIND_BY_TYPE = {"DOCUMENT": "file", "CANVAS": "page", "SECTION": "section"}


def _link_kind(root: dict) -> str:
    """file · page · section · screen · element (화면 안 부품: 인스턴스 안쪽 id 'I…' · 글자 · 도형 등)"""
    root_type = root.get("type")
    if root_type in LINK_KIND_BY_TYPE:
        return LINK_KIND_BY_TYPE[root_type]
    if root_type in SCREEN_TYPES and not str(root.get("id", "")).startswith("I"):
        return "screen"
    return "element"


def _next_for(link_kind: str, file_key: str, node_id: str | None, screen_count: int) -> str:
    fetch_hint = f"fetch --file-key {file_key} --node {{id}} --dump-dir <dump> --design-dir <design>"
    if link_kind in ("screen", "element"):
        target = "this screen" if link_kind == "screen" else "this element (part of a screen)"
        return (f"The link points to {target}: do not ask which screen, fetch it now with "
                + fetch_hint.format(id=node_id)
                + (". If the user meant the whole screen, ask for the screen link" if link_kind == "element" else ""))
    if screen_count == 0:
        return "No screens here. Ask the user for another link (a page, section or screen)"
    return ("Show the user the groups and screen names, let them pick one, then " + fetch_hint.format(id="<screen id>"))


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

    # 링크 종류별: 화면·부품은 그 자체 1건, 묶음(파일·페이지·섹션)은 안쪽 화면 목록
    link_kind = _link_kind(root)
    screens: list[dict] = []
    if link_kind in ("screen", "element"):
        box = root.get("absoluteBoundingBox") or {}
        screens.append({"id": root.get("id"), "name": root.get("name"), "type": root.get("type"),
                        "group": "", "width": box.get("width"), "height": box.get("height"),
                        "hidden": root.get("visible") is False})
    else:
        _collect_screens(root, [root.get("name") or ""] if args.node else [], screens)
    groups = _group_counts(screens)
    return emit({
        "file": body.get("name"), "file_key": args.file_key, "node_id": args.node,
        "link_kind": link_kind, "last_modified": body.get("lastModified"),
        "screen_count": len(screens), "groups": groups, "screens": screens,
        "summary": f"Link is a {link_kind}: {len(screens)} screen(s) in {len(groups)} group(s)",
        "next": _next_for(link_kind, args.file_key, args.node, len(screens)),
    })
