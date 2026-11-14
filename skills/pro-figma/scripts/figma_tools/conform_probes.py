"""Property comparison verdicts: check corners · fills · shadows against render pixels"""
from __future__ import annotations

import re

from figma_tools.dump_reader import _is_hidden, _split_shadows


# =========================================================================
# corners — compare by property (#626)
#
# Pixel percentages say only **where** it differs, not **what differs and how**.
# Real incident: a bottom sheet's top corners were square, and the tool reported that spot
# as `476~519 / 0~785 / mean diff 77`. 5.5% different overall with 22 blobs —
# the real defect drowned in noise. Nobody reads a 22-row coordinate table.
#
# Properties are definite: `top-left r=16 but the render is square`.
# =========================================================================

# A point (t,t) moved t diagonally in from the vertex is (r-t)·√2 away from
# the arc center (r,r). It is **outside the shape** only if this exceeds r:
#     (r-t)·√2 > r  ⟺  t < r(1 - 1/√2) = 0.2929r
# So 0.3r is past the threshold, **inside** — probing there yields the face color
# even on a rounded corner, always reading "square". 0.15r is used for margin.
_CORNER_PROBE = 0.15
_CORNER_LIMIT = 1.0 - 1.0 / (2 ** 0.5)      # 0.2929… — values at or above this are meaningless

_CORNER_NAMES = ("top-left", "top-right", "bottom-right", "bottom-left")


def _parse_radius(value) -> list[float]:
    """Expand borderRadius into four corner values.

    Measured: arrives as one value like `20px` or as four like `0px 0px 0px 0px`.
    """
    if value is None:
        return [0.0] * 4
    if isinstance(value, (int, float)):
        return [float(value)] * 4
    nums = [float(m) for m in re.findall(r"-?\d+(?:\.\d+)?", str(value))]
    if not nums:
        return [0.0] * 4
    if len(nums) == 1:
        return nums * 4
    if len(nums) == 2:
        return [nums[0], nums[1], nums[0], nums[1]]
    return (nums + nums[-1:] * 4)[:4]


def _stroke_width(strokes, styles: dict) -> float:
    """Border width (logical px). Both MCP and converted dumps use {strokeWeight: '2px'}, 0 if absent"""
    strokes = styles.get(strokes) if isinstance(strokes, str) else strokes
    if not isinstance(strokes, dict):
        return 0.0
    numbers = re.findall(r"\d+(?:\.\d+)?", str(strokes.get("strokeWeight") or "0"))
    return float(numbers[0]) if numbers else 0.0


def _rects(node, styles: dict, want_id, ox=0.0, oy=0.0, inside=False, out=None,
           skipped=None):
    """Collect rectangles with absolute coordinates.

    Position is in `locationRelativeToParent` inside the layout reference. Auto-layout
    children lack it and need flow computation; inventing coordinates by guessing
    **probes the wrong spot and insists it is a defect.** So unknown ones are
    skipped and **the number skipped is reported.**
    """
    if out is None:
        out, skipped = [], []
    if isinstance(node, list):
        for c in node:
            _rects(c, styles, want_id, ox, oy, inside, out, skipped)
        return out, skipped
    if not isinstance(node, dict):
        return out, skipped
    if _is_hidden(node):
        return out, skipped

    node_id = node.get("id")
    here = inside or want_id is None or node_id == want_id

    layout = node.get("layout")
    box = styles.get(layout) if isinstance(layout, str) else layout
    box = box if isinstance(box, dict) else {}
    loc = box.get("locationRelativeToParent")
    dims = box.get("dimensions") or {}
    w, h = dims.get("width"), dims.get("height")

    x, y, known = ox, oy, True
    if here and node_id:
        if isinstance(loc, dict):
            x, y = ox + float(loc.get("x", 0)), oy + float(loc.get("y", 0))
        elif want_id is not None and node_id == want_id:
            x, y = 0.0, 0.0          # the reference node is the render origin
        else:
            known = False

        radii = _parse_radius(node.get("borderRadius"))
        fills = node.get("fills")
        fills = styles.get(fills) if isinstance(fills, str) else fills
        fx = node.get("effects")
        fx = styles.get(fx) if isinstance(fx, str) else fx
        interesting = any(r > 0 for r in radii) or fills is not None or fx is not None
        if interesting and w and h:
            (out if known else skipped).append({
                "ref": node_id, "name": node.get("name"), "type": node.get("type"),
                "x": x, "y": y, "width": float(w), "height": float(h),
                "radii": radii, "fills": fills, "effects": fx,
                "stroke_width": _stroke_width(node.get("strokes"), styles),
            })

    for k, v in node.items():
        if isinstance(v, (dict, list)) and k not in ("fills", "strokes", "effects"):
            _rects(v, styles, want_id, x if known else ox, y if known else oy,
                   here, out, skipped)
    return out, skipped


_HEX = re.compile(r"^#([0-9a-fA-F]{6})$")
_RGBA = re.compile(r"rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)(?:[,\s/]+([\d.]+))?\s*\)")


def _as_color(entry):
    """Read one fill layer as (rgb, alpha). None if not a color."""
    if not isinstance(entry, str):
        return None
    m = _HEX.match(entry.strip())
    if m:
        h = m.group(1)
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)), 1.0
    m = _RGBA.search(entry)
    if m:
        a = float(m.group(4)) if m.group(4) is not None else 1.0
        return (int(float(m.group(1))), int(float(m.group(2))),
                int(float(m.group(3)))), a
    return None


def _fill_kind(value):
    """Normalize fills into (kind, value).

    Measured distribution: solid hex 72 · rgba 14 · gradient 28 · image 2.
    **The top layer is what shows on screen**, so it is the basis.
    """
    layers = value if isinstance(value, list) else [value]
    for entry in layers:                      # list front is the top layer
        if isinstance(entry, dict):
            if entry.get("imageRef"):
                return "image", entry
            if "gradient" in str(entry):
                return "gradient", entry
            continue
        c = _as_color(entry)
        if c:
            return ("translucent" if c[1] < 1.0 else "solid"), c
    return "unknown", None


def _shadow_offsets(effects):
    """(dx, dy, blur, color alpha) of outer shadows. inset excluded — invisible from outside."""
    out = []
    if not isinstance(effects, dict):
        return out
    for line in _split_shadows(str(effects.get("boxShadow") or "")):
        if not line or line.startswith("inset"):
            continue
        nums = re.findall(r"(-?[\d.]+)px", line)
        if len(nums) >= 3:
            color = _as_color(line[line.find("rgb"):] if "rgb" in line else line.split()[-1])
            out.append((float(nums[0]), float(nums[1]), float(nums[2]), color[1] if color else 1.0))
    return out


def _node_width(node, styles: dict, want_id):
    """Logical width of the reference node. The scale is derived from it.

    ⚠️ Do not use the max over rectangles with corners — the reference frame usually
    has no rounded corners so it is not in that list, and then the scale is off entirely and
    **it insists healthy corners are square.** (Measured 1.25 instead of 1.0.)
    """
    if isinstance(node, list):
        for c in node:
            w = _node_width(c, styles, want_id)
            if w:
                return w
        return None
    if not isinstance(node, dict):
        return None
    if want_id is None or node.get("id") == want_id:
        layout = node.get("layout")
        box = styles.get(layout) if isinstance(layout, str) else layout
        w = ((box or {}).get("dimensions") or {}).get("width") if isinstance(box, dict) else None
        if w:
            return float(w)
        if want_id is not None:
            return None
    for k, v in node.items():
        if isinstance(v, (dict, list)) and k not in ("fills", "strokes", "effects"):
            w = _node_width(v, styles, want_id)
            if w:
                return w
    return None


def _probe_corners(img, rect: dict, scale: float, tol: int, above=None, below=None) -> list[dict]:
    """Probe all four corners to see if they are square.

    If a spot that should be outside has **the same color as inside**, it is square. No need
    to know the fill value — the inside of the same rectangle is the reference.
    """
    W, H = img.size
    findings = []
    if _fill_kind(rect.get("fills"))[0] in ("unknown", "image"):
        return findings                 # no fill · photo fills cannot be told by corner in/out color
    own_color = _solid_rgb(rect)
    # Same-colored upper layers do not hide shape differences (camera dot over the dynamic island)
    above = [q for q in above or [] if not own_color or _solid_rgb(q) != own_color]
    x0, y0 = rect["x"] * scale, rect["y"] * scale
    w, h = rect["width"] * scale, rect["height"] * scale

    def at(px, py):
        px, py = int(round(px)), int(round(py))
        if not (0 <= px < W and 0 <= py < H):
            return None
        return img.getpixel((px, py))[:3]

    for i, r_logical in enumerate(rect["radii"]):
        # Radius larger than half the short edge draws at that value (pill shape r=100 · height 37 > 18.5)
        r_logical = min(r_logical, rect["width"] / 2, rect["height"] / 2)
        r = r_logical * scale
        if r <= 1:
            continue
        t = r * _CORNER_PROBE
        # i: 0 top-left · 1 top-right · 2 bottom-right · 3 bottom-left
        vx = x0 if i in (0, 3) else x0 + w
        vy = y0 if i in (0, 1) else y0 + h
        sx = 1 if i in (0, 3) else -1
        sy = 1 if i in (0, 1) else -1
        if any(_is_covered((vx + sx * px) / scale, (vy + sy * px) / scale, above)
               for px in (t, r * 1.6)):
            continue                    # probe spot covered by an upper layer
        under = _color_under((vx + sx * t) / scale, (vy + sy * t) / scale, below or [])
        if own_color and under and max(abs(a - b) for a, b in zip(own_color, under)) <= tol:
            continue                    # lower layer same color > rounding invisible
        outside = at(vx + sx * t, vy + sy * t)          # must be background if rounded
        inside = at(vx + sx * r * 1.6, vy + sy * r * 1.6)   # surely inside the face
        if outside is None or inside is None:
            continue
        diff = max(abs(a - b) for a, b in zip(outside, inside))
        if diff <= tol:
            findings.append({
                "corner": _CORNER_NAMES[i], "radius": r_logical,
                "probe": [round(vx + sx * t, 1), round(vy + sy * t, 1)],
                "outside_rgb": list(outside), "inside_rgb": list(inside),
                "verdict": "각짐",
                "says": (f"{rect['name'] or rect['ref']} "
                         f"{rect['width']:.0f}x{rect['height']:.0f} "
                         f"@{rect['x']:.0f},{rect['y']:.0f} "
                         f"{_CORNER_NAMES[i]} r={r_logical:g} → the render is square"),
            })
    return findings


# Nodes whose fill is on strokes only (the center point is background)
_GLYPH_TYPES = ("TEXT", "IMAGE-SVG", "VECTOR")
# Candidate points to sample fill color (box ratio): center > inner top·bottom·left·right
_FILL_PROBE_POINTS = ((0.5, 0.5), (0.5, 0.15), (0.5, 0.85), (0.15, 0.5), (0.85, 0.5))


def _is_covered(lx: float, ly: float, above: list[dict]) -> bool:
    """Does an upper layer (a later-drawn filled rectangle) cover this logical point"""
    return any(q["x"] <= lx <= q["x"] + q["width"] and q["y"] <= ly <= q["y"] + q["height"]
               for q in above)


def _free_point(rect: dict, above: list[dict]):
    """First candidate point not covered by an upper layer (logical coords). None if all covered"""
    for fx, fy in _FILL_PROBE_POINTS:
        point = (rect["x"] + rect["width"] * fx, rect["y"] + rect["height"] * fy)
        if not _is_covered(*point, above):
            return point
    return None


def _solid_rgb(rect: dict):
    """(r, g, b) if the top fill is solid, else None"""
    kind, value = _fill_kind(rect.get("fills"))
    return value[0] if kind == "solid" else None


def _color_under(lx: float, ly: float, below: list[dict]):
    """Color of the layer just below the point (topmost earlier-drawn solid rectangle). None if unknown"""
    for q in reversed(below):
        if q["x"] <= lx <= q["x"] + q["width"] and q["y"] <= ly <= q["y"] + q["height"]:
            return _solid_rgb(q)
    return None


def layers_below(rects: list[dict], index: int) -> list[dict]:
    """Rectangles drawn before (below) the index rectangle"""
    return rects[:index]


def layers_above(rects: list[dict], index: int) -> list[dict]:
    """Filled rectangles drawn after (above) the index rectangle (list order = draw order)"""
    return [q for q in rects[index + 1:] if _fill_kind(q.get("fills"))[0] != "unknown"]


def _label(rect) -> str:
    return (f"{rect['name'] or rect['ref']} {rect['width']:.0f}x{rect['height']:.0f} "
            f"@{rect['x']:.0f},{rect['y']:.0f}")


def _check_fills(sample, rect, tol, above=None) -> list[dict]:
    """Is the fill painted as designed.

    Catches: a different color · **missing opacity** (hex right but left opaque) ·
    **a gradient laid as a solid**. All three look "close enough" on screen.
    """
    kind, value = _fill_kind(rect.get("fills"))
    if kind in ("unknown", "image"):
        return []                       # photos cannot be judged by color
    if rect.get("type") in _GLYPH_TYPES:
        return []                       # text·icon fills are strokes only, one point cannot measure
    w, h = rect["width"], rect["height"]
    point = _free_point(rect, above or [])
    if point is None:
        return []                       # fully covered by upper layers > fill not visible
    mid = sample(*point)
    if mid is None:
        return []
    out = []

    if kind in ("solid", "translucent"):
        want, alpha = value
        gap = max(abs(a - b) for a, b in zip(mid, want))
        if kind == "solid" and gap > tol:
            out.append({"check": "fills", "severity": "high", "ref": rect["ref"],
                        "says": (f"{_label(rect)} fill differs — design "
                                 f"rgb{want}, render rgb{tuple(mid)}")})
        elif kind == "translucent" and gap <= tol:
            # Semi-transparent yet the raw color as is = opacity was not applied
            out.append({"check": "fills", "severity": "high", "ref": rect["ref"],
                        "says": (f"{_label(rect)} transparency is missing — design "
                                 f"alpha={alpha:g} but the render is the solid rgb{want}")})
    elif kind == "gradient":
        # No need to know the axis — measure both vertical·horizontal ends; **if neither changes** it is solid
        pad = 0.12
        pts = [sample(rect["x"] + w / 2, rect["y"] + h * pad),
               sample(rect["x"] + w / 2, rect["y"] + h * (1 - pad)),
               sample(rect["x"] + w * pad, rect["y"] + h / 2),
               sample(rect["x"] + w * (1 - pad), rect["y"] + h / 2)]
        pts = [q for q in pts if q is not None]
        if len(pts) >= 2:
            spread = max(max(abs(a - b) for a, b in zip(p1, p2))
                         for p1 in pts for p2 in pts)
            if spread <= tol:
                out.append({"check": "fills", "severity": "high", "ref": rect["ref"],
                            "says": (f"{_label(rect)} gradient is painted as a solid color — "
                                     f"the whole area is the single color rgb{tuple(pts[0])}")})
    return out


def _check_shadows(sample, rect, tol) -> list[dict]:
    """Was the outer shadow actually drawn.

    If the design specifies an offset shadow, the outside in that direction **must differ from the far background**.
    If equal, the shadow is missing entirely — small and subtle, so the eye misses it.
    """
    offsets = _shadow_offsets(rect.get("effects"))
    out = []
    for dx, dy, blur, alpha in offsets:
        reach = max(abs(dx), abs(dy), blur / 2.0)
        if reach < 2:
            continue                     # too shallow to tell by pixels
        if alpha * 255 <= tol * 2:
            continue                     # too faint (e.g. 5%), difference from background within tolerance
        w, h = rect["width"], rect["height"]
        cx, cy = rect["x"] + w / 2, rect["y"] + h / 2
        # Just outside on the side the shadow falls
        if abs(dy) >= abs(dx):
            near = sample(cx, rect["y"] + h + max(dy, 1) if dy >= 0 else rect["y"] + min(dy, -1))
            far = sample(cx, rect["y"] + h + reach * 6 if dy >= 0 else rect["y"] - reach * 6)
        else:
            near = sample(rect["x"] + w + max(dx, 1) if dx >= 0 else rect["x"] + min(dx, -1), cy)
            far = sample(rect["x"] + w + reach * 6 if dx >= 0 else rect["x"] - reach * 6, cy)
        if near is None or far is None:
            continue
        if max(abs(a - b) for a, b in zip(near, far)) <= tol:
            out.append({"check": "shadows", "severity": "medium", "ref": rect["ref"],
                        "says": (f"{_label(rect)} shadow is not visible — design has "
                                 f"{dx:g},{dy:g} blur {blur:g} but just outside the edge "
                                 f"matches the far background")})
    return out


_SEVERITY_ORDER = {"none": 0, "low": 1, "medium": 2, "high": 3}
_ALL_CHECKS = ("placement", "corners", "fills", "shadows")


def _has_node(data, node_id: str) -> bool:
    """Is there a node with id node_id anywhere in the dump (hidden layers included)."""
    stack = [data]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            if cur.get("id") == node_id:
                return True
            stack.extend(v for v in cur.values() if isinstance(v, (dict, list)))
        elif isinstance(cur, list):
            stack.extend(cur)
    return False
