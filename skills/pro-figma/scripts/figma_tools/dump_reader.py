"""Figma dump reading: list style entries · resolve references · collect asset nodes"""
from __future__ import annotations

import json
import re
from pathlib import Path


# =========================================================================
# coverage — lists every style entry in the dump
# =========================================================================

# Things that must move from the design to the screen. Key names vary slightly per dump,
# so aliases are checked too — if nothing is found it silently passes as "0 entries".
_STYLE_KEYS = {
    "fills": ("fills", "fill", "background", "backgroundColor"),
    "strokes": ("strokes", "stroke", "border", "borders"),
    "effects": ("effects", "effect", "boxShadow", "shadow", "shadows"),
    "layout": ("layout", "layoutMode", "padding", "itemSpacing", "cornerRadius",
               "borderRadius", "gap"),
    "text": ("style", "textStyle", "fontSize", "fontWeight", "fontFamily",
             "lineHeight", "letterSpacing"),
}


# Shadows arrive as **several rows in one string**, joined by commas. Measured:
#   boxShadow: '0px 4px 20px 0px rgba(...), inset 0px 8px 24px -16px rgba(...),
#               inset 0px -24px 32px 0px rgba(...), inset 0px 0px 10px 2px rgba(...)'
# Counted as one row, three of four rows can be missing unnoticed — that was the actual incident.
# Commas inside rgba(...) must be left alone, so parenthesis depth is tracked.
def _split_shadows(css: str) -> list[str]:
    out, depth, cur = [], 0, ""
    for ch in css:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            if cur.strip():
                out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


# Name the kind. You notice **which kind keeps getting dropped** only if it is named.
_NO_OFFSET = re.compile(r"^(inset\s+)?0(px)?\s+0(px)?\s")


def _effect_kind(prop: str, value: str) -> str:
    v = str(value).strip()
    if prop == "backdropFilter":
        return "background blur"
    if prop == "filter":
        return "blur" if "blur" in v else "filter"
    if v.startswith("inset"):
        return "inner shadow"
    if _NO_OFFSET.match(v):
        # Spread with no offset — commonly called a "glow"
        return "glow"
    return "shadow"


def _describe(value) -> str:
    """One entry as one human-readable line. Values are shortened but **never dropped.**"""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)) or value is None:
        return str(value)
    if isinstance(value, list):
        return " / ".join(_describe(v) for v in value) or "[]"
    if isinstance(value, dict):
        parts = []
        for k, v in value.items():
            if isinstance(v, (dict, list)):
                parts.append(f"{k}={_describe(v)}")
            else:
                parts.append(f"{k}={v}")
        return "{" + ", ".join(parts) + "}"
    return str(value)


# Assets are in the dump **only as nodes, not images**. However well values are ported,
# the screen has no icons unless these nodes are downloaded separately.
_ASSET_TYPES = {"IMAGE-SVG", "IMAGE", "VECTOR"}

# download_figma_images fileName accepts only ^[a-zA-Z0-9_.-]+\.(png|svg)$.
# Measured: in one real file, 281 of 609 assets (46%) had names with Korean·spaces·'/', so
# passing layer names as is gets rejected. Also 592 were crowded into 45 names, so
# saving by name **overwrites each other**. So a safe name is made here.
def _slug(name, node_id: str) -> tuple[str, bool]:
    raw = re.sub(r"[^A-Za-z0-9]+", "-", str(name or "")).strip("-").lower()
    if raw:
        return raw[:48], False
    # Names with no ASCII left, like Korean — flag that the meaning was lost
    return "asset-" + re.sub(r"[^0-9]+", "-", str(node_id)).strip("-"), True


def _image_ref(node: dict, styles: dict):
    """Find photo fills and return download arguments.

    **Fills come as references too.** The node only has `fills: fill_JJ816G` and imageRef
    lives in the globalVars value — without resolving the reference, photo assets are missed entirely.
    The dump gives the needed arguments in `imageDownloadArguments`, so they are used as is.
    """
    for key in ("fills", "fill", "background"):
        blob = node.get(key)
        if isinstance(blob, str):
            blob = styles.get(blob)
        if blob is None:
            continue
        for entry in (blob if isinstance(blob, list) else [blob]):
            if not isinstance(entry, dict) or not entry.get("imageRef"):
                continue
            args = entry.get("imageDownloadArguments") or {}
            return {
                "imageRef": entry["imageRef"],
                "needsCropping": bool(args.get("needsCropping")),
                "requiresImageDimensions": bool(args.get("requiresImageDimensions")),
                "cropTransform": entry.get("imageTransform") or args.get("cropTransform"),
            }
    return None


def _is_hidden(node: dict) -> bool:
    """Is this node not drawn on screen.

    **Hidden layers are mixed into the dump.** Counting them gives numbers like "40 entries
    to classify" and people give up reviewing — then counting is pointless.
    """
    if node.get("visible") is False:
        return True
    try:
        if float(node.get("opacity", 1)) == 0:
            return True
    except (TypeError, ValueError):
        pass
    # Tools name it differently. Unknown notation counts as visible —
    # counting one extra row beats wrongly filtering and dropping one.
    return node.get("isVisible") is False or node.get("hidden") is True


def _walk(node, path, out, want_id=None, inside=False, hidden=None, elements=None,
          styles=None, assets=None):
    """Walk the dump and collect style entries.

    The dump shape differs per tool·version, so key names are found recursively, not fixed.
    Assuming a structure makes it **silently 0 items** in the next version.
    """
    if hidden is None:
        hidden = []
    if elements is None:
        elements = []
    if styles is None:
        styles = {}
    if assets is None:
        assets = []
    if isinstance(node, list):
        for i, child in enumerate(node):
            _walk(child, f"{path}[{i}]", out, want_id, inside, hidden, elements, styles,
                  assets)
        return
    if not isinstance(node, dict):
        return

    # Hidden layers are skipped with all children. If the parent is invisible, so are the children.
    if _is_hidden(node):
        hidden.append(node.get("id") or node.get("name") or "?")
        return

    node_id = node.get("id")
    node_name = node.get("name")
    here = inside or want_id is None or (node_id == want_id)

    if here and (node_id or node_name):
        label = node_id or node_name
        # Counting styles alone misses **elements missing entirely**. Things in the design
        # that were absent from the screen did happen — that is not a style problem.
        #
        # Only nodes with id count as elements. Component property declarations (VARIANTs like `Dark Mode`)
        # also have a name, so going by name alone mixes non-screen elements into the list.
        node_type = node.get("type") or node.get("nodeType")
        if node_id and node_type != "VARIANT":
            elements.append({"ref": node_id, "name": node_name, "type": node_type})
            if node_type in _ASSET_TYPES:
                # The dump has **no icon shape**. Even the size sits behind a layout reference.
                # So identity evidence is collected, and only evidenced ones are grouped.
                layout = node.get("layout")
                box = styles.get(layout) if isinstance(layout, str) else layout
                dims = (box or {}).get("dimensions") if isinstance(box, dict) else None
                # Assets with effects **arrive larger than drawn** — the blur is
                # baked into the image as a filter. Measured: a glow shape with layout 36x34
                # came as 96x94. Without warning, it gets placed at layout size, shrinking
                # the shape, or the effect is added again in code.
                fx = node.get("effects")
                fx = styles.get(fx) if isinstance(fx, str) else fx
                assets.append({
                    "node_id": node_id, "name": node_name, "type": node_type,
                    "width": (dims or {}).get("width"),
                    "height": (dims or {}).get("height"),
                    "baked_effect": _describe(fx) if fx else None,
                    "image": _image_ref(node, styles),
                    "component_id": node.get("componentId"),
                    # **Evidence** of the same image. With no shape info, this is the best available.
                    "_print": json.dumps(
                        {k: v for k, v in node.items() if k not in ("id", "children")},
                        sort_keys=True, ensure_ascii=False),
                })
        for kind, aliases in _STYLE_KEYS.items():
            for key in aliases:
                if key not in node:
                    continue
                value = node[key]
                # Replace references with real values. Otherwise "fill_B16QZY" becomes the value,
                # cannot be classified, and multi-row effects collapse into one row.
                if isinstance(value, str) and value in styles:
                    value = styles[value]
                if value in (None, [], {}, ""):
                    continue
                # Split arrays into **one row per element**. As one row,
                # a missing row in a four-row effects list goes unnoticed.
                if isinstance(value, list):
                    for i, item in enumerate(value):
                        out.append({"ref": f"{label}/{key}[{i}]", "kind": kind,
                                    "name": node_name, "value": _describe(item)})
                elif isinstance(value, dict) and kind == "effects":
                    # For effects each key is one treatment (shadow·blur…),
                    # and inside it **more rows joined by commas**. Both are split.
                    for k2, v2 in value.items():
                        lines = _split_shadows(str(v2)) if isinstance(v2, str) else [v2]
                        many = len(lines) > 1
                        for n2, line in enumerate(lines):
                            ref = f"{label}/{key}.{k2}" + (f"[{n2}]" if many else "")
                            out.append({"ref": ref, "kind": kind, "name": node_name,
                                        "effect": _effect_kind(k2, line),
                                        "value": _describe(line)})
                else:
                    out.append({"ref": f"{label}/{key}", "kind": kind,
                                "name": node_name, "value": _describe(value)})

    for k, v in node.items():
        if isinstance(v, (dict, list)) and k not in ("fills", "strokes", "effects"):
            _walk(v, f"{path}.{k}", out, want_id, here, hidden, elements, styles, assets)


def _load_dump(path: Path):
    """Read the dump. **The real MCP returns YAML** — JSON-only would not work.

    It may be JSON depending on tool·version, so JSON is tried first, then YAML.
    """
    text = path.read_text(encoding="utf-8")
    try:
        return json.loads(text), None
    except json.JSONDecodeError:
        pass
    try:
        import yaml
    except ImportError:
        return None, ("yaml_missing",
                      "The dump is not JSON. Reading it as YAML needs PyYAML",
                      "python3 -m pip install pyyaml")
    try:
        return yaml.safe_load(text), None
    except yaml.YAMLError as e:
        return None, ("dump_unreadable", str(e), None)


def _style_table(data) -> dict:
    """`globalVars.styles` — nodes hold styles **only as references**.

        nodes:  {fills: fill_B16QZY}          ← read alone, "fill_B16QZY" becomes the value
        globalVars.styles: {fill_B16QZY: ['#737373']}   ← the real value is here

    Unresolved, four effect rows count as **one reference-string row**, so a missing row
    goes unnoticed — exactly what this tool is meant to prevent.
    """
    if not isinstance(data, dict):
        return {}
    gv = data.get("globalVars")
    if isinstance(gv, dict) and isinstance(gv.get("styles"), dict):
        return gv["styles"]
    return gv if isinstance(gv, dict) else {}
