"""자리 검사 · 시스템 노드: 상자가 시안 선 위에 있나 / OS 가 그리는 노드(상태바·키보드) 찾기

자리를 모서리보다 먼저 본다. 상자가 통째로 밀리면 모서리 탐침이 면 안쪽을 찍어 "각졌다"고 거짓말한다
(elum 카드확인 화면 실측).
"""
from __future__ import annotations

import re

from figma_tools.conform_probes import _GLYPH_TYPES, _color_under, _is_covered, _label, _solid_rgb

# OS 가 그리는 노드 이름 (앱이 안 그림). 키보드는 자판 30여 개가 오탐으로 쏟아짐
SYSTEM_NODE_NAME = re.compile(r"status\s*bar|home\s*indicator|keyboard|키보드|상태\s*바", re.IGNORECASE)
# 자리 검사를 하기엔 작은 상자 (논리 px)
MIN_PLACEMENT_SIZE = 20
# 면 안쪽 · 바깥쪽 탐침 거리 (논리 px)
INNER_PROBE_INSET = 2
OUTER_PROBE_OFFSET = 3
# 변마다 찍는 위치 (변 길이 비율)
SIDE_PROBE_FRACTIONS = (0.35, 0.5, 0.65)


def system_node_ids(data: dict) -> set[str]:
    """이름이 시스템 노드인 것과 그 자손 id 전부"""
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
    """색 거리 (유클리드). 채널 최대차는 흰 시트 <-> 연한 배경을 너무 가깝게 봄"""
    return sum((a - b) ** 2 for a, b in zip(color_a, color_b)) ** 0.5


def check_placement(sample, rect: dict, above: list[dict], below: list[dict], tolerance: int):
    """네 변이 시안 선 위에 있나 > finding 목록 · 판정(True / False / None 판정 불가)"""
    face = _solid_rgb(rect)
    x, y, width, height = rect["x"], rect["y"], rect["width"], rect["height"]
    # 면을 채우는 도형만 (글자·아이콘 칠은 획에만 있음)
    if face is None or rect.get("type") in _GLYPH_TYPES or min(width, height) < MIN_PLACEMENT_SIZE:
        return [], None
    # 테두리는 면을 갉아먹음 > 그 두께만큼 더 안쪽
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
            # 위 겹이 덮은 자리 · 바깥이 같은 색 면(맞닿은 이웃)인 자리는 판정 불가
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
