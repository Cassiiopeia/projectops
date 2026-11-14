"""Placement check · system nodes: is the box on the design lines / find OS-drawn nodes (status bar·keyboard)

Placement is checked before corners. If a box shifts as a whole, the corner probe hits inside the face and falsely reports "각짐"
(measured on the elum card-confirm screen).
"""
from __future__ import annotations

import re

from figma_tools.conform_probes import _GLYPH_TYPES, _color_under, _is_covered, _label, _solid_rgb

# Names of OS-drawn nodes (not drawn by the app). The keyboard floods 30-odd keys as false positives
SYSTEM_NODE_NAME = re.compile(r"status\s*bar|home\s*indicator|keyboard|키보드|상태\s*바", re.IGNORECASE)
# Box too small for a placement check (logical px)
MIN_PLACEMENT_SIZE = 20
# Probe distance inside · outside the face (logical px)
INNER_PROBE_INSET = 2
OUTER_PROBE_OFFSET = 3
# Probe positions per edge (ratio of edge length)
SIDE_PROBE_FRACTIONS = (0.35, 0.5, 0.65)


def system_node_ids(data: dict) -> set[str]:
    """Ids of nodes named as system nodes and all their descendants"""
    found: set[str] = set()

    def walk(node, is_inside_system: bool) -> None:
        if isinstance(node, list):
            for child in node:
                walk(child, is_inside_system)
            return
        if not isinstance(node, dict):
            return
        is_system = is_inside_system or bool(SYSTEM_NODE_NAME.search(str(node.get("name") or "")))
        if is_system and node.get("id"):
            found.add(node["id"])
        for child in node.get("children") or []:
            walk(child, is_system)

    walk(data.get("nodes", data), False)
    return found


def _distance(color_a, color_b) -> float:
    """Color distance (Euclidean). Max channel difference rates white sheet <-> light background as too close"""
    return sum((a - b) ** 2 for a, b in zip(color_a, color_b)) ** 0.5


def check_placement(sample, rect: dict, above: list[dict], below: list[dict], tolerance: int):
    """Are all four edges on the design lines > finding list · verdict (True / False / None undecidable)"""
    face = _solid_rgb(rect)
    x, y, width, height = rect["x"], rect["y"], rect["width"], rect["height"]
    # Only shapes that fill a face (text·icon fills are strokes only)
    if face is None or rect.get("type") in _GLYPH_TYPES or min(width, height) < MIN_PLACEMENT_SIZE:
        return [], None
    # A border eats into the face > that much further inside
    inset = INNER_PROBE_INSET + rect.get("stroke_width", 0)
    sides = {
        "top": [((x + width * f, y + inset), (x + width * f, y - OUTER_PROBE_OFFSET))
                for f in SIDE_PROBE_FRACTIONS],
        "bottom": [((x + width * f, y + height - inset), (x + width * f, y + height + OUTER_PROBE_OFFSET))
                   for f in SIDE_PROBE_FRACTIONS],
        "left": [((x + inset, y + height * f), (x - OUTER_PROBE_OFFSET, y + height * f))
                 for f in SIDE_PROBE_FRACTIONS],
        "right": [((x + width - inset, y + height * f), (x + width + OUTER_PROBE_OFFSET, y + height * f))
                  for f in SIDE_PROBE_FRACTIONS],
    }
    bad_sides, tested_sides = [], 0
    for side, probes in sides.items():
        votes = []
        for inner, outer in probes:
            # Spots covered by an upper layer · with a same-colored face outside (touching neighbor) are undecidable
            if _is_covered(*inner, above) or _is_covered(*outer, above):
                continue
            behind = _color_under(*outer, below)
            if behind is None or _distance(behind, face) <= tolerance * 2:
                continue
            inner_rgb, outer_rgb = sample(*inner), sample(*outer)
            if inner_rgb is None or outer_rgb is None:
                continue
            reaches = _distance(inner_rgb, face) < _distance(inner_rgb, behind)
            spills = _distance(outer_rgb, face) < _distance(outer_rgb, behind)
            votes.append(reaches and not spills)
        if not votes:
            continue
        tested_sides += 1
        if sum(votes) * 2 <= len(votes):
            bad_sides.append(side)
    if not tested_sides:
        return [], None
    if bad_sides:
        return [{"check": "placement", "severity": "high", "ref": rect["ref"],
                 "sides": bad_sides,
                 "says": f"{_label(rect)} {', '.join(bad_sides)} edge is not where the design puts it"}], False
    return [], True
