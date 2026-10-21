"""속성 대조 판정: 모서리 · 칠 · 그림자를 렌더 픽셀로 확인"""
from __future__ import annotations

import re

from figma_tools.dump_reader import _is_hidden, _split_shadows


# =========================================================================
# corners — 속성으로 대조한다 (#626)
#
# 픽셀 퍼센트는 **어디가** 다른지만 말하고 **무엇이 어떻게** 다른지를 말하지 않는다.
# 실제 사고: 바텀시트 상단 모서리가 각져 있었는데, 도구는 그 자리를
# `476~519 / 0~785 / 평균차 77` 로 리포트했다. 전체 5.5% 다름에 덩어리 22개 —
# 진짜 결함이 잡음에 묻혔다. 사람은 22줄짜리 좌표표를 읽지 않는다.
#
# 속성은 단정적이다: `좌상 r=16 인데 렌더가 각졌다`.
# =========================================================================

# 꼭짓점에서 대각선으로 t 만큼 들어간 점 (t,t) 는, 호 중심 (r,r) 까지의 거리가
# (r-t)·√2 다. 이게 r 보다 커야 **도형 바깥**이다:
#     (r-t)·√2 > r  ⟺  t < r(1 - 1/√2) = 0.2929r
# 즉 0.3r 은 임계값을 넘어 **안쪽**이다 — 그 자리를 찍으면 둥근 모서리에서도
# 면 색이 나와 언제나 "각졌다"가 된다. 여유를 두고 0.15r 을 쓴다.
_CORNER_PROBE = 0.15
_CORNER_LIMIT = 1.0 - 1.0 / (2 ** 0.5)      # 0.2929… — 이 값 이상은 의미가 없다

_CORNER_NAMES = ("top-left", "top-right", "bottom-right", "bottom-left")


def _parse_radius(value) -> list[float]:
    """borderRadius 를 네 귀 값으로 편다.

    실측: `20px` 처럼 하나로 오기도, `0px 0px 0px 0px` 처럼 넷으로 오기도 한다.
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


def _rects(node, styles: dict, want_id, ox=0.0, oy=0.0, inside=False, out=None,
           skipped=None):
    """절대 좌표를 가진 사각형을 모은다.

    위치는 layout 참조 안의 `locationRelativeToParent` 에 있다. 자동배치
    (auto-layout) 자식은 그 값이 없어 흐름을 계산해야 하는데, 추측으로 좌표를
    지어내면 **엉뚱한 자리를 검사하고 결함이라 우긴다.** 그래서 모르면
    건너뛰고 **몇 개를 건너뛰었는지 밝힌다.**
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
            x, y = 0.0, 0.0          # 대조 기준 노드는 렌더의 원점이다
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
            })

    for k, v in node.items():
        if isinstance(v, (dict, list)) and k not in ("fills", "strokes", "effects"):
            _rects(v, styles, want_id, x if known else ox, y if known else oy,
                   here, out, skipped)
    return out, skipped


_HEX = re.compile(r"^#([0-9a-fA-F]{6})$")
_RGBA = re.compile(r"rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)(?:[,\s/]+([\d.]+))?\s*\)")


def _as_color(entry):
    """칠 한 겹을 (rgb, alpha) 로 읽는다. 색이 아니면 None."""
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
    """칠을 (종류, 값) 으로 정리한다.

    실측 분포: 단색 hex 72 · rgba 14 · 그라디언트 28 · 이미지 2.
    **맨 위 겹이 화면에 보이는 것**이라 그것을 기준으로 삼는다.
    """
    layers = value if isinstance(value, list) else [value]
    for entry in layers:                      # 목록의 앞이 위 겹이다
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
    """바깥 그림자들의 (dx, dy, blur). inset 은 뺀다 — 밖에서 안 보인다."""
    out = []
    if not isinstance(effects, dict):
        return out
    for line in _split_shadows(str(effects.get("boxShadow") or "")):
        if not line or line.startswith("inset"):
            continue
        nums = re.findall(r"(-?[\d.]+)px", line)
        if len(nums) >= 3:
            out.append((float(nums[0]), float(nums[1]), float(nums[2])))
    return out


def _node_width(node, styles: dict, want_id):
    """기준 노드의 논리 폭. 배율을 여기서 뽑는다.

    ⚠️ 모서리를 가진 사각형들에서 최댓값을 쓰면 안 된다 — 기준 프레임은 대개
    둥근 모서리가 없어 그 목록에 없고, 그러면 배율이 통째로 어긋나 **멀쩡한
    모서리를 각졌다고 우긴다.** (실측으로 1.0 대신 1.25 가 나왔다.)
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


def _probe_corners(img, rect: dict, scale: float, tol: int) -> list[dict]:
    """모서리 네 곳을 찍어 각졌는지 본다.

    바깥이어야 할 자리가 **안쪽과 같은 색**이면 각진 것이다. 칠 값을 따로 알
    필요가 없다 — 같은 사각형 안쪽을 기준으로 삼는다.
    """
    W, H = img.size
    findings = []
    x0, y0 = rect["x"] * scale, rect["y"] * scale
    w, h = rect["width"] * scale, rect["height"] * scale

    def at(px, py):
        px, py = int(round(px)), int(round(py))
        if not (0 <= px < W and 0 <= py < H):
            return None
        return img.getpixel((px, py))[:3]

    for i, r_logical in enumerate(rect["radii"]):
        r = r_logical * scale
        if r <= 1:
            continue
        t = r * _CORNER_PROBE
        # i: 0 좌상 · 1 우상 · 2 우하 · 3 좌하
        vx = x0 if i in (0, 3) else x0 + w
        vy = y0 if i in (0, 1) else y0 + h
        sx = 1 if i in (0, 3) else -1
        sy = 1 if i in (0, 1) else -1
        outside = at(vx + sx * t, vy + sy * t)          # 둥글면 배경이어야 한다
        inside = at(vx + sx * r * 1.6, vy + sy * r * 1.6)   # 확실히 면 안쪽
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


def _label(rect) -> str:
    return (f"{rect['name'] or rect['ref']} {rect['width']:.0f}x{rect['height']:.0f} "
            f"@{rect['x']:.0f},{rect['y']:.0f}")


def _check_fills(sample, rect, tol) -> list[dict]:
    """칠이 시안대로 칠해졌는가.

    잡는 것: 색 자체가 다름 · **투명도가 빠짐**(hex 는 맞는데 그대로 불투명) ·
    **그라디언트를 단색으로 깔음**. 셋 다 화면에서는 "비슷해" 보인다.
    """
    kind, value = _fill_kind(rect.get("fills"))
    if kind in ("unknown", "image"):
        return []                       # 사진은 색으로 판정할 수 없다
    w, h = rect["width"], rect["height"]
    mid = sample(rect["x"] + w / 2, rect["y"] + h / 2)
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
            # 반투명인데 원색 그대로 = 투명도를 안 준 것이다
            out.append({"check": "fills", "severity": "high", "ref": rect["ref"],
                        "says": (f"{_label(rect)} transparency is missing — design "
                                 f"alpha={alpha:g} but the render is the solid rgb{want}")})
    elif kind == "gradient":
        # 축을 몰라도 된다 — 세로·가로 양쪽 끝을 재서 **어느 쪽도 안 변하면** 단색이다
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
    """바깥 그림자가 실제로 그려졌는가.

    시안이 치우친 그림자를 말하면, 그 방향 바깥이 **먼 배경과 달라야** 한다.
    같으면 그림자가 통째로 빠진 것이다 — 작고 은은해서 눈으로는 안 보인다.
    """
    offsets = _shadow_offsets(rect.get("effects"))
    out = []
    for dx, dy, blur in offsets:
        reach = max(abs(dx), abs(dy), blur / 2.0)
        if reach < 2:
            continue                     # 너무 얕아 픽셀로 가릴 수 없다
        w, h = rect["width"], rect["height"]
        cx, cy = rect["x"] + w / 2, rect["y"] + h / 2
        # 그림자가 지는 쪽 바로 바깥
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
_ALL_CHECKS = ("corners", "fills", "shadows")


def _has_node(data, node_id: str) -> bool:
    """덤프 어딘가에 id 가 node_id 인 노드가 있나 (꺼 둔 레이어도 포함)."""
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
