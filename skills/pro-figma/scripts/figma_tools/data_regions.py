"""데이터 영역: 실제 데이터로 내용이 바뀌는 자리 (글자 내용 · 사진) > 그림 대조에서 뺄 상자

데이터가 들어가는 화면은 mock 데이터의 글자 길이·사진이 시안과 다를 수 있다.
그 자리만 빼고 나머지(배치·색·모양·간격)는 그대로 맞댄다.
"""
from __future__ import annotations

from figma_tools.conform_probes import _fill_kind, _node_width, _rects
from figma_tools.dump_reader import _style_table

# 뺄 수 있는 데이터 종류: text 글자 내용 · image 사진 칠
DATA_KINDS = ("text", "image")
# 글자 상자 여유 (논리 px): 안티에일리어싱·글꼴 차이로 상자 밖 1~2px 번짐
TEXT_PADDING_PIXELS = 2


def _kind_of(rect: dict) -> str | None:
    """사각형 > 데이터 종류 (text · image) 또는 None"""
    if rect.get("type") == "TEXT":
        return "text"
    if _fill_kind(rect.get("fills"))[0] == "image":
        return "image"
    return None


def find_data_regions(data: dict, node_id: str | None, kinds: tuple, image_width: int) -> dict:
    """덤프 > 이미지 픽셀 좌표의 데이터 상자 목록 + 배율

    반환: boxes [{kind, ref, name, x0, y0, x1, y1}] · scale · skipped (위치 모름)
    """
    styles = _style_table(data)
    rects, skipped = _rects(data, styles, node_id)
    base_width = _node_width(data.get("nodes", data), styles, node_id)
    scale = image_width / base_width if base_width else 1.0
    boxes = []
    for rect in rects:
        kind = _kind_of(rect)
        if kind not in kinds:
            continue
        padding = TEXT_PADDING_PIXELS if kind == "text" else 0
        boxes.append({"kind": kind, "ref": rect["ref"], "name": rect["name"],
                      "x0": int((rect["x"] - padding) * scale), "y0": int((rect["y"] - padding) * scale),
                      "x1": int((rect["x"] + rect["width"] + padding) * scale) + 1,
                      "y1": int((rect["y"] + rect["height"] + padding) * scale) + 1})
    skipped_data = [s["ref"] for s in skipped if _kind_of(s) in kinds]
    return {"boxes": boxes, "scale": scale, "skipped": skipped_data}


def find_node_regions(data: dict, origin_id: str | None, node_ids: list[str], image_width: int) -> dict:
    """지정한 노드들(디자이너의 사진 자리표시 등) > 이미지 픽셀 상자. 덤프에 없는 id 는 missing"""
    styles = _style_table(data)
    base_width = _node_width(data.get("nodes", data), styles, origin_id)
    scale = image_width / base_width if base_width else 1.0
    boxes, found = [], set()
    for rect in _all_boxes(data, origin_id, styles):
        if rect["ref"] in node_ids:
            found.add(rect["ref"])
            boxes.append({"kind": "node", "ref": rect["ref"], "name": rect["name"],
                          "x0": int(rect["x"] * scale), "y0": int(rect["y"] * scale),
                          "x1": int((rect["x"] + rect["width"]) * scale) + 1,
                          "y1": int((rect["y"] + rect["height"]) * scale) + 1})
    return {"boxes": boxes, "missing": [n for n in node_ids if n not in found]}


def _all_boxes(data: dict, origin_id: str | None, styles: dict) -> list[dict]:
    """칠 유무와 관계없이 위치를 아는 모든 노드 상자 (논리 좌표, origin 기준)"""
    boxes: list[dict] = []

    def walk(node, ox: float, oy: float, inside: bool) -> None:
        if isinstance(node, list):
            for child in node:
                walk(child, ox, oy, inside)
            return
        if not isinstance(node, dict):
            return
        here = inside or origin_id is None or node.get("id") == origin_id
        layout = node.get("layout")
        layout = styles.get(layout) if isinstance(layout, str) else layout   # MCP 덤프는 참조
        layout = layout if isinstance(layout, dict) else {}
        loc = layout.get("locationRelativeToParent")
        dims = layout.get("dimensions") or {}
        x, y = ox, oy
        if here and node.get("id") == origin_id:
            x, y = 0.0, 0.0
        elif here and isinstance(loc, dict):
            x, y = ox + float(loc.get("x", 0)), oy + float(loc.get("y", 0))
        if here and node.get("id") and dims.get("width") and dims.get("height"):
            boxes.append({"ref": node["id"], "name": node.get("name"), "x": x, "y": y,
                          "width": float(dims["width"]), "height": float(dims["height"])})
        for child in node.get("children") or []:
            walk(child, x, y, here)

    walk(data.get("nodes", data), 0.0, 0.0, False)
    return boxes


def parse_data_kinds(text: str) -> tuple | None:
    """'text,image' > ('text', 'image'). 모르는 값이 있으면 None"""
    kinds = tuple(k.strip() for k in text.split(",") if k.strip())
    return kinds if kinds and all(k in DATA_KINDS for k in kinds) else None
