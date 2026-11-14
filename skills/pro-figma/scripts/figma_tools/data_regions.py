"""Data regions: spots whose content changes with real data (text content · photos) > boxes excluded from image comparison

On data-filled screens, mock data text length·photos can differ from the design.
Only those spots are excluded; the rest (layout·color·shape·spacing) is compared as is.
"""
from __future__ import annotations

from figma_tools.conform_probes import _fill_kind, _node_width, _rects
from figma_tools.dump_reader import _style_table

# Excludable data kinds: text = text content · image = photo fill
DATA_KINDS = ("text", "image")
# Text box margin (logical px): anti-aliasing·font differences bleed 1-2px outside the box
TEXT_PADDING_PIXELS = 2


def _kind_of(rect: dict) -> str | None:
    """Rectangle > data kind (text · image) or None"""
    if rect.get("type") == "TEXT":
        return "text"
    if _fill_kind(rect.get("fills"))[0] == "image":
        return "image"
    return None


def find_data_regions(data: dict, node_id: str | None, kinds: tuple, image_width: int) -> dict:
    """Dump > list of data boxes in image pixel coords + scale

    Returns: boxes [{kind, ref, name, x0, y0, x1, y1}] · scale · skipped (position unknown)
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
    """Given nodes (designer's photo placeholders etc.) > image pixel boxes. Ids not in the dump are missing"""
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
    """Boxes of every node with a known position, filled or not (logical coords, relative to origin)"""
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
        layout = styles.get(layout) if isinstance(layout, str) else layout   # MCP dumps use references
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
    """'text,image' > ('text', 'image'). None if any value is unknown"""
    kinds = tuple(k.strip() for k in text.split(",") if k.strip())
    return kinds if kinds and all(k in DATA_KINDS for k in kinds) else None
