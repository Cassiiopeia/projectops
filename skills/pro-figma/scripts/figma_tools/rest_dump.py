"""Figma REST node response > MCP (get_figma_data) dump shape conversion

coverage · assets · conform read the MCP dump shape (layout.dimensions · locationRelativeToParent ·
borderRadius · boxShadow strings · IMAGE-SVG). Feeding raw REST in would make
corner·shadow comparison silently find 0 items, so fetch converts it once before saving.
Values go directly on nodes without references (globalVars) (readers accept both).
"""
from __future__ import annotations

# Vector nodes with shape info only > IMAGE-SVG like MCP (targets to download as assets)
VECTOR_TYPES = {"VECTOR", "BOOLEAN_OPERATION", "STAR", "REGULAR_POLYGON", "LINE"}
# Groups that become IMAGE-SVG as a whole when everything inside is vector
VECTOR_WRAPPER_TYPES = {"FRAME", "GROUP", "INSTANCE", "COMPONENT"}


def _number(value: float) -> str:
    """12.0 > '12', 0.5 > '0.5'"""
    return f"{value:g}"


def _css_color(color: dict, opacity: float = 1.0) -> str:
    """{r,g,b,a}(0~1) > '#RRGGBB' (opaque) or 'rgba(r, g, b, a)'"""
    red, green, blue = (round(color.get(k, 0) * 255) for k in ("r", "g", "b"))
    alpha = round(color.get("a", 1) * opacity, 3)
    if alpha >= 1:
        return f"#{red:02X}{green:02X}{blue:02X}"
    return f"rgba({red}, {green}, {blue}, {_number(alpha)})"


def _convert_paint(paint: dict):
    """One fill layer: solid > color string, image > imageRef dict, gradient > gradient dict"""
    paint_type = paint.get("type")
    opacity = paint.get("opacity", 1)
    if paint_type == "SOLID":
        return _css_color(paint.get("color") or {}, opacity)
    if paint_type == "IMAGE":
        return {"type": "IMAGE", "imageRef": paint.get("imageRef"), "scaleMode": paint.get("scaleMode"),
                "imageTransform": paint.get("imageTransform")}
    if paint_type and paint_type.startswith("GRADIENT_"):
        stops = ", ".join(f"{_css_color(s.get('color') or {}, opacity)} {_number(s.get('position', 0) * 100)}%"
                          for s in paint.get("gradientStops") or [])
        return {"type": paint_type, "gradient": f"{paint_type.lower()}({stops})"}
    return {"type": paint_type}


def _visible_paints(paints) -> list:
    """Visible fills only, top layer first (REST puts the bottom layer first, MCP the top)"""
    return [_convert_paint(p) for p in reversed(paints or []) if p.get("visible", True)]


def _convert_effects(effects) -> dict:
    """Effect list > {boxShadow, filter, backdropFilter} (multiple shadows joined by commas)"""
    shadows, filters, backdrops = [], [], []
    for effect in effects or []:
        if not effect.get("visible", True):
            continue
        effect_type = effect.get("type")
        if effect_type in ("DROP_SHADOW", "INNER_SHADOW"):
            offset = effect.get("offset") or {}
            line = (f"{_number(offset.get('x', 0))}px {_number(offset.get('y', 0))}px "
                    f"{_number(effect.get('radius', 0))}px {_number(effect.get('spread', 0))}px "
                    f"{_css_color(effect.get('color') or {})}")
            shadows.append(("inset " if effect_type == "INNER_SHADOW" else "") + line)
        elif effect_type == "LAYER_BLUR":
            filters.append(f"blur({_number(effect.get('radius', 0))}px)")
        elif effect_type == "BACKGROUND_BLUR":
            backdrops.append(f"blur({_number(effect.get('radius', 0))}px)")
    converted = {}
    if shadows:
        converted["boxShadow"] = ", ".join(shadows)
    if filters:
        converted["filter"] = " ".join(filters)
    if backdrops:
        converted["backdropFilter"] = " ".join(backdrops)
    return converted


def _border_radius(node: dict) -> str | None:
    """cornerRadius > '20px' · rectangleCornerRadii (top-left·top-right·bottom-right·bottom-left) > '0px 0px 16px 16px'"""
    corners = node.get("rectangleCornerRadii")
    if isinstance(corners, list) and len(corners) == 4 and len(set(corners)) > 1:
        return " ".join(f"{_number(c)}px" for c in corners)
    radius = node.get("cornerRadius")
    return f"{_number(radius)}px" if radius else None


def _layout(node: dict, parent_box: dict | None) -> dict:
    """Size · position relative to parent · auto layout values"""
    box = node.get("absoluteBoundingBox") or {}
    layout = {"dimensions": {"width": box.get("width"), "height": box.get("height")}}
    if parent_box and box:
        layout["locationRelativeToParent"] = {"x": box.get("x", 0) - parent_box.get("x", 0),
                                              "y": box.get("y", 0) - parent_box.get("y", 0)}
    if node.get("layoutMode") and node["layoutMode"] != "NONE":
        layout["mode"] = "row" if node["layoutMode"] == "HORIZONTAL" else "column"
        layout["gap"] = f"{_number(node.get('itemSpacing', 0))}px"
        padding = [node.get(k, 0) for k in ("paddingTop", "paddingRight", "paddingBottom", "paddingLeft")]
        if any(padding):
            layout["padding"] = " ".join(f"{_number(p)}px" for p in padding)
    return layout


def _text_style(style: dict) -> dict:
    """REST text style > only values used for comparison"""
    converted = {k: style[k] for k in ("fontFamily", "fontWeight", "fontSize", "textAlignHorizontal")
                 if k in style}
    if style.get("lineHeightPx"):
        converted["lineHeight"] = f"{_number(round(style['lineHeightPx'], 2))}px"
    if style.get("letterSpacing"):
        converted["letterSpacing"] = f"{_number(round(style['letterSpacing'], 2))}px"
    return converted


def _is_partial_ellipse(node: dict) -> bool:
    """Arc-shaped ellipse such as a half circle·ring (not a full circle > fetched as an image)"""
    arc = node.get("arcData") or {}
    if node.get("type") != "ELLIPSE" or not arc:
        return False
    sweep = abs(arc.get("endingAngle", 0) - arc.get("startingAngle", 0))
    return arc.get("innerRadius", 0) > 0 or sweep < 6.28


def _first_paints(node: dict) -> list:
    """Representative fill of a vector group: own fill > stroke > first descendant's (for cover checks)"""
    for key in ("fills", "strokes"):
        paints = _visible_paints(node.get(key))
        if paints:
            return paints
    for child in node.get("children") or []:
        if child.get("visible", True):
            paints = _first_paints(child)
            if paints:
                return paints
    return []


def _is_vector_only(node: dict) -> bool:
    """A vector (including arc ellipses), or a group whose visible children are all vectors"""
    if node.get("type") in VECTOR_TYPES or _is_partial_ellipse(node):
        return True
    children = [c for c in node.get("children") or [] if c.get("visible", True)]
    return (node.get("type") in VECTOR_WRAPPER_TYPES and bool(children)
            and all(_is_vector_only(c) for c in children))


def convert_node(node: dict, parent_box: dict | None = None) -> dict:
    """Convert one node (+children): basics > fill·stroke·effect·corner > text > children (vector groups become IMAGE-SVG without children)"""
    is_vector = _is_vector_only(node)
    converted = {"id": node.get("id"), "name": node.get("name"),
                 "type": "IMAGE-SVG" if is_vector else node.get("type")}
    if node.get("visible") is False:
        converted["visible"] = False
    if node.get("opacity", 1) != 1:
        converted["opacity"] = node["opacity"]
    if node.get("componentId"):
        converted["componentId"] = node["componentId"]
    converted["layout"] = _layout(node, parent_box)

    fills = _first_paints(node) if is_vector else _visible_paints(node.get("fills"))
    if fills:
        converted["fills"] = fills
    strokes = _visible_paints(node.get("strokes"))
    if strokes:
        converted["strokes"] = {"colors": strokes,
                                "strokeWeight": f"{_number(node.get('strokeWeight', 1))}px"}
    effects = _convert_effects(node.get("effects"))
    if effects:
        converted["effects"] = effects
    radius = _border_radius(node)
    if radius:
        converted["borderRadius"] = radius

    if node.get("type") == "TEXT":
        converted["text"] = node.get("characters", "")
        converted["textStyle"] = _text_style(node.get("style") or {})
    if not is_vector and node.get("children"):
        own_box = node.get("absoluteBoundingBox")
        converted["children"] = [convert_node(c, own_box) for c in node["children"]]
    return converted


def node_fingerprint(body: dict, node_id: str) -> str | None:
    """Content fingerprint of one screen (sha256 of the converted result). Unchanged when other parts of the file change"""
    import hashlib
    import json
    document = ((body.get("nodes") or {}).get(node_id) or {}).get("document")
    if not document:
        return None
    text = json.dumps(convert_node(document), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def rest_nodes_to_dump(body: dict, node_id: str) -> dict:
    """REST /files/:key/nodes response > MCP dump shape (lastModified·version kept in metadata)"""
    document = ((body.get("nodes") or {}).get(node_id) or {}).get("document") or {}
    return {
        "metadata": {"name": body.get("name"), "lastModified": body.get("lastModified"),
                     "version": body.get("version"), "source": "figma-rest"},
        "nodes": [convert_node(document)],
        "globalVars": {"styles": {}},
    }
