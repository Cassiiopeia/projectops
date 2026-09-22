#!/usr/bin/env python3
"""figma_verify_cli — 시안과 구현 화면을 대조한다 (projectops 3-layer Layer 2).

**눈으로는 못 잡는다.** 어떤 버튼에서 효과 네 줄 중 안쪽 세 줄이 통째로 빠진 채
배포된 일이 있었다. 전체 화면 골든을 만들어 놓고도 지나갔다 — 361x68 안의 10px
안쪽 그림자는 그 크기에서 몇 픽셀이라 있으나 없으나 비슷해 보인다.

값 단언(`expect(shadow.blur, 10)`)도 절반만 막는다. **단언하기로 생각한 것만**
지킨다. 빠뜨린 줄은 애초에 단언도 안 썼으니 아무도 세지 않는다.

그래서 두 가지를 한다.

  coverage — 덤프의 스타일 항목을 **하나도 빠짐없이 나열**해 분류를 강제한다.
             값을 못 옮긴 것과 안 옮기기로 한 것을 구분하는 것이 요점이다.
  diff     — 그림으로 맞대 어디가 다른지 덩어리로 뽑는다.

판단은 사람이 한다. 이 스크립트는 **세고 나열하고 그릴 뿐**이다.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_PROJECT_ROOT = _HERE.parents[3]
_SCRIPTS_ROOT = _PROJECT_ROOT / "scripts"
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from common.emit import emit  # noqa: E402


# =========================================================================
# coverage — 덤프의 스타일 항목을 전부 나열한다
# =========================================================================

# 시안에서 화면으로 옮겨져야 하는 것들. 덤프마다 키 이름이 조금씩 다르므로
# 별칭을 함께 본다 — 못 찾으면 "항목 0개"로 조용히 통과해 버린다.
_STYLE_KEYS = {
    "fills": ("fills", "fill", "background", "backgroundColor"),
    "strokes": ("strokes", "stroke", "border", "borders"),
    "effects": ("effects", "effect", "boxShadow", "shadow", "shadows"),
    "layout": ("layout", "layoutMode", "padding", "itemSpacing", "cornerRadius",
               "borderRadius", "gap"),
    "text": ("style", "textStyle", "fontSize", "fontWeight", "fontFamily",
             "lineHeight", "letterSpacing"),
}


def _describe(value) -> str:
    """항목 하나를 사람이 읽을 한 줄로. 값을 줄이되 **버리지 않는다.**"""
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


def _is_hidden(node: dict) -> bool:
    """화면에 안 그려지는 노드인가.

    덤프에는 **꺼 둔 레이어도 섞여 나온다.** 그것까지 세면 "분류할 항목 40개"
    같은 숫자가 나와 사람이 보다 지쳐 포기한다 — 그러면 세는 의미가 없다.
    """
    if node.get("visible") is False:
        return True
    try:
        if float(node.get("opacity", 1)) == 0:
            return True
    except (TypeError, ValueError):
        pass
    # 도구마다 이름이 다르다. 모르는 표기는 보이는 것으로 친다 —
    # 잘못 걸러 빠뜨리는 것보다 한 줄 더 세는 편이 낫다.
    return node.get("isVisible") is False or node.get("hidden") is True


def _walk(node, path, out, want_id=None, inside=False, hidden=None, elements=None,
          styles=None):
    """덤프를 훑어 스타일 항목을 모은다.

    덤프 모양이 도구·버전마다 달라서 키 이름을 고정하지 않고 재귀로 찾는다.
    구조를 단정하면 다음 버전에서 **조용히 0건**이 된다.
    """
    if hidden is None:
        hidden = []
    if elements is None:
        elements = []
    if styles is None:
        styles = {}
    if isinstance(node, list):
        for i, child in enumerate(node):
            _walk(child, f"{path}[{i}]", out, want_id, inside, hidden, elements, styles)
        return
    if not isinstance(node, dict):
        return

    # 꺼 둔 레이어는 자식까지 통째로 건너뛴다. 부모가 안 보이면 자식도 안 보인다.
    if _is_hidden(node):
        hidden.append(node.get("id") or node.get("name") or "?")
        return

    node_id = node.get("id")
    node_name = node.get("name")
    here = inside or want_id is None or (node_id == want_id)

    if here and (node_id or node_name):
        label = node_id or node_name
        # 스타일만 세면 **요소가 통째로 빠진 것**은 안 보인다. 시안에 있는데
        # 화면에 아예 없는 경우가 실제로 있었다 — 그건 스타일 문제가 아니다.
        #
        # id 가 있는 것만 요소로 친다. 컴포넌트 속성 선언(`Dark Mode` 같은 VARIANT)도
        # name 을 갖고 있어서, name 만 보면 화면 요소가 아닌 것이 목록에 섞인다.
        node_type = node.get("type") or node.get("nodeType")
        if node_id and node_type != "VARIANT":
            elements.append({"ref": node_id, "name": node_name, "type": node_type})
        for kind, aliases in _STYLE_KEYS.items():
            for key in aliases:
                if key not in node:
                    continue
                value = node[key]
                # 참조면 실제 값으로 바꾼다. 안 바꾸면 "fill_B16QZY" 가 값이 되어
                # 분류할 수 없고, 여러 줄짜리 효과가 한 줄로 뭉개진다.
                if isinstance(value, str) and value in styles:
                    value = styles[value]
                if value in (None, [], {}, ""):
                    continue
                # 배열은 **원소마다 한 줄**로 쪼갠다. 통째로 한 줄이면
                # 네 줄짜리 effects 에서 한 줄이 빠져도 티가 안 난다.
                if isinstance(value, list):
                    for i, item in enumerate(value):
                        out.append({"ref": f"{label}/{key}[{i}]", "kind": kind,
                                    "name": node_name, "value": _describe(item)})
                elif isinstance(value, dict) and kind == "effects":
                    # 효과는 키 하나가 곧 하나의 연출이다 (그림자·블러…).
                    # 묶어 두면 둘 중 하나가 빠져도 안 보인다.
                    for k2, v2 in value.items():
                        out.append({"ref": f"{label}/{key}.{k2}", "kind": kind,
                                    "name": node_name, "value": _describe(v2)})
                else:
                    out.append({"ref": f"{label}/{key}", "kind": kind,
                                "name": node_name, "value": _describe(value)})

    for k, v in node.items():
        if isinstance(v, (dict, list)) and k not in ("fills", "strokes", "effects"):
            _walk(v, f"{path}.{k}", out, want_id, here, hidden, elements, styles)


def _load_dump(path: Path):
    """덤프를 읽는다. **실제 MCP 는 YAML 을 돌려준다** — JSON 만 받으면 못 쓴다.

    도구·버전에 따라 JSON 일 수도 있으므로 JSON 을 먼저 시도하고 YAML 로 내려간다.
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
                      "덤프가 JSON 이 아닙니다. YAML 로 읽으려면 PyYAML 이 필요합니다",
                      "python3 -m pip install pyyaml")
    try:
        return yaml.safe_load(text), None
    except yaml.YAMLError as e:
        return None, ("dump_unreadable", str(e), None)


def _style_table(data) -> dict:
    """`globalVars.styles` — 노드는 스타일을 **참조로만** 갖는다.

        nodes:  {fills: fill_B16QZY}          ← 이것만 보면 "fill_B16QZY" 가 값이 된다
        globalVars.styles: {fill_B16QZY: ['#737373']}   ← 진짜 값은 여기

    해소하지 않으면 효과 네 줄이 **참조 문자열 한 줄**로 세어져, 한 줄이 빠져도
    드러나지 않는다 — 이 도구가 막으려던 바로 그 일이다.
    """
    if not isinstance(data, dict):
        return {}
    gv = data.get("globalVars")
    if isinstance(gv, dict) and isinstance(gv.get("styles"), dict):
        return gv["styles"]
    return gv if isinstance(gv, dict) else {}


def cmd_coverage(args) -> int:
    path = Path(args.dump)
    if not path.is_file():
        return emit({"ok": False, "code": "dump_not_found",
                     "error": f"덤프 파일이 없습니다: {args.dump}",
                     "hint": "Figma MCP 로 받은 덤프를 파일로 저장한 뒤 넘기세요 (JSON·YAML 모두 받습니다)"})
    try:
        data, err = _load_dump(path)
    except OSError as e:
        return emit({"ok": False, "code": "dump_unreadable", "error": str(e)})
    if err:
        code, msg, hint = err
        out = {"ok": False, "code": code, "error": msg}
        if hint:
            out["hint"] = hint
        return emit(out)

    items: list[dict] = []
    hidden: list[str] = []
    elements: list[dict] = []
    styles = _style_table(data)
    _walk(data, "$", items, args.node, hidden=hidden, elements=elements, styles=styles)

    if not items:
        return emit({
            "ok": False, "code": "no_style_found",
            "error": "덤프에서 스타일 항목을 하나도 찾지 못했습니다",
            "hint": ("노드 id 가 맞는지, 덤프가 스타일을 포함하는지 확인하세요. "
                     "0건으로 조용히 통과하면 대조를 안 한 것과 같습니다"),
        })

    counts: dict[str, int] = {}
    for it in items:
        counts[it["kind"]] = counts.get(it["kind"], 0) + 1

    return emit({
        "node": args.node,
        "items": items,
        "counts": counts,
        "total": len(items),
        "elements": elements,
        "element_count": len(elements),
        "styles_resolved": len(styles),
        "hidden_skipped": hidden,
        "summary": (f"요소 {len(elements)}개 · 스타일 항목 {len(items)}개 " +
                    " · ".join(f"{k} {v}" for k, v in sorted(counts.items())) +
                    (f" (꺼 둔 레이어 {len(hidden)}개 제외)" if hidden else "")),
        "next": ("두 층으로 확인하세요. ① **요소**가 화면에 있는가 — 시안에 있는데 "
                 "화면에 아예 없는 것이 실제로 나옵니다. ② 각 **스타일 항목**을 "
                 "구현 / 근사(사유) / 생략(사유) 로 분류. 근사·생략은 사유를 반드시 "
                 "적습니다 — 적지 않으면 못 옮긴 것인지 안 옮기기로 한 것인지 "
                 "나중에 구분할 수 없습니다"),
    })


# =========================================================================
# diff — 그림으로 맞댄다
# =========================================================================

def _require_imaging():
    try:
        import numpy  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError:
        return emit({
            "ok": False, "code": "imaging_missing",
            "error": "Pillow 와 numpy 가 필요합니다",
            "hint": "python3 -m pip install pillow numpy",
        })
    return None


def _parse_bg(text, design_img):
    """합성 배경색을 정한다.

    앱 렌더는 바깥 발광이 반투명으로 남고 시안 export 는 배경이 합성된 채로 온다.
    같은 배경 위에 올려놓지 않으면 **발광 전체가 '다름'으로 잡혀** diff 가 의미를
    잃는다. 색을 고정값으로 박으면 남의 프로젝트에서 틀리므로 시안에서 읽는다.
    """
    if text and text != "auto":
        v = text.lstrip("#")
        if len(v) != 6:
            raise ValueError(f"--bg 는 RRGGBB 형식이어야 합니다: {text}")
        return tuple(int(v[i:i + 2], 16) for i in (0, 2, 4)), f"#{v.upper()}"
    corner = design_img.getpixel((0, 0))
    if len(corner) == 4 and corner[3] == 255:
        return corner[:3], "시안 좌상단 픽셀"
    return (255, 255, 255), "흰색 (시안 모서리가 투명)"


def _clusters(mask, min_area):
    """다른 픽셀이 뭉친 덩어리를 상자로 묶는다.

    한 픽셀씩 보고하면 안티에일리어싱 노이즈에 묻혀 못 읽는다. 행 단위로 훑어
    겹치는 상자를 합치는 정도면 사람이 어디를 볼지 정하기에 충분하다.
    """
    import numpy as np
    if not mask.any():
        return []
    boxes = []
    for y in range(mask.shape[0]):
        row = np.nonzero(mask[y])[0]
        if len(row) == 0:
            continue
        x0, x1 = int(row.min()), int(row.max())
        if boxes and y - boxes[-1][3] <= 2:
            b = boxes[-1]
            boxes[-1] = [min(b[0], x0), b[1], max(b[2], x1), y]
        else:
            boxes.append([x0, y, x1, y])
    return [b for b in boxes if (b[2] - b[0] + 1) * (b[3] - b[1] + 1) >= min_area]


def _shift_probe(design, render, threshold, span):
    """렌더를 조금씩 옮겨 보며 **통째로 밀린 것인지** 가린다.

    실사고: 시트 윗변이 35px 아래에 뜨자 안의 단계·보상·버튼이 **전부 두 겹**으로
    보였다. 덩어리가 열 개 나왔지만 틀린 것은 하나 — 컨테이너 높이였다. 덩어리만
    세면 "열 군데가 어긋났다"로 읽혀 엉뚱한 데를 고치게 된다.

    세로를 먼저 본다. 화면은 세로로 쌓이므로 밀림도 대개 세로다.
    """
    import numpy as np

    def rate(dy, dx):
        h, w = design.shape[:2]
        y0, y1 = max(0, dy), min(h, h + dy)
        x0, x1 = max(0, dx), min(w, w + dx)
        if y1 - y0 < h // 2 or x1 - x0 < w // 2:
            return 1.0
        a_ = design[y0:y1, x0:x1]
        b_ = render[y0 - dy:y1 - dy, x0 - dx:x1 - dx]
        return float((np.abs(a_ - b_).max(axis=2) > threshold).mean())

    base = rate(0, 0)
    best_dy, best = 0, base
    for dy in range(-span, span + 1):
        r = rate(dy, 0)
        if r < best:
            best_dy, best = dy, r
    best_dx = 0
    for dx in range(-span, span + 1):
        r = rate(best_dy, dx)
        if r < best:
            best_dx, best = dx, r
    return {"dy": best_dy, "dx": best_dx,
            "before": round(base * 100, 2), "after": round(best * 100, 2)}


def cmd_diff(args) -> int:
    missing = _require_imaging()
    if missing is not None:
        return missing
    import numpy as np
    from PIL import Image

    for label, p in (("render", args.render), ("design", args.design)):
        if not Path(p).is_file():
            return emit({"ok": False, "code": "image_not_found",
                         "error": f"{label} 이미지가 없습니다: {p}"})

    design_img = Image.open(args.design).convert("RGBA")
    try:
        bg, bg_src = _parse_bg(args.bg, design_img)
    except ValueError as e:
        return emit({"ok": False, "code": "bad_bg", "error": str(e)})

    def flatten(img):
        base = Image.new("RGBA", img.size, (*bg, 255))
        return np.asarray(Image.alpha_composite(base, img).convert("RGB"), dtype=np.int16)

    design = flatten(design_img)
    render_img = Image.open(args.render).convert("RGBA")
    if render_img.size != design_img.size:
        render_img = render_img.resize(design_img.size, Image.LANCZOS)
    render = flatten(render_img)

    delta = np.abs(design - render).max(axis=2)
    if args.mask_top:
        delta[:args.mask_top] = 0
    if args.mask_bottom:
        delta[-args.mask_bottom:] = 0

    mask = delta > args.threshold
    compared = delta.size - (args.mask_top + args.mask_bottom) * delta.shape[1]
    pct = 100.0 * int(mask.sum()) / max(compared, 1)

    found = []
    for x0, y0, x1, y1 in _clusters(mask, args.min_area):
        region = delta[y0:y1 + 1, x0:x1 + 1]
        hot = region[region > args.threshold]
        found.append({"x": x0, "y": y0, "w": x1 - x0 + 1, "h": y1 - y0 + 1,
                      "mean_delta": round(float(hot.mean()), 1)})

    # 덩어리가 여럿일 때 "낱낱이 틀림"인지 "하나가 밀림"인지 가린다.
    shift = None
    if found and args.probe_shift > 0:
        shift = _shift_probe(design, render, args.threshold, args.probe_shift)
        # 옮겨서 절반 아래로 떨어지면 밀림으로 본다. 조금 나아지는 정도는
        # 안티에일리어싱으로도 생기므로 신호로 치지 않는다.
        shift["looks_shifted"] = bool(
            (shift["dy"] or shift["dx"])
            and shift["after"] <= shift["before"] * 0.5)

    out_path = None
    if args.out:
        # 원본을 흐리게 깔고 다른 자리만 붉게 칠한다 — 어디가 틀렸는지 바로 보인다.
        canvas = (design * 0.35 + 255 * 0.65).astype(np.uint8)
        canvas[mask] = [255, 0, 0]
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(canvas).save(args.out)
        out_path = str(args.out)

    return emit({
        "size": f"{design.shape[1]}x{design.shape[0]}",
        "background": bg_src,
        "threshold": args.threshold,
        "different_pixels": int(mask.sum()),
        "compared_pixels": int(compared),
        "different_percent": round(pct, 2),
        "max_delta": int(delta.max()),
        "clusters": found,
        "shift_probe": shift,
        "diff_image": out_path,
        "summary": (f"다른 픽셀 {pct:.2f}% · 덩어리 {len(found)}개 "
                    f"(최대 채널차 {int(delta.max())})"),
        "next": (
            (f"덩어리가 {len(found)}개지만 렌더를 "
             f"({shift['dx']:+d}, {shift['dy']:+d}) 옮기면 "
             f"{shift['before']}% → {shift['after']}% 로 떨어집니다. "
             "**낱낱이 어긋난 것이 아니라 통째로 밀린 것**입니다 — 안의 요소가 아니라 "
             "그것을 담은 컨테이너(높이·여백·안전영역)를 먼저 보세요."
             if (shift or {}).get("looks_shifted") else
             "퍼센트가 아니라 **덩어리 위치**를 보세요. 글자 자리면 래스터라이즈 "
             "차이라 대개 무해하고, 도형·여백 자리면 실제로 틀린 것입니다. "
             "그림자·발광·1px 테두리는 전체 화면에서 사라지므로 component 로 다시 봅니다")),
    })


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="figma_verify_cli",
                                description="시안과 구현 화면을 대조한다")
    sub = p.add_subparsers(dest="command")

    c = sub.add_parser("coverage", help="덤프의 스타일 항목을 빠짐없이 나열한다")
    c.add_argument("--dump", required=True, help="Figma 덤프를 저장한 JSON 파일")
    c.add_argument("--node", default=None,
                   help="이 노드 아래만 본다 (생략하면 덤프 전체)")
    c.set_defaults(func=cmd_coverage)

    d = sub.add_parser("diff", help="시안 export 와 앱 렌더를 픽셀로 맞댄다")
    d.add_argument("--render", required=True, help="앱이 그린 PNG")
    d.add_argument("--design", required=True, help="Figma export PNG")
    d.add_argument("--out", default=None, help="차이를 칠한 PNG 저장 경로")
    d.add_argument("--bg", default="auto",
                   help="합성 배경색 RRGGBB. 기본 auto = 시안 모서리에서 읽는다")
    d.add_argument("--threshold", type=int, default=24,
                   help="채널당 이 값을 넘어야 '다르다'로 본다 (기본 24)")
    d.add_argument("--mask-top", type=int, default=0,
                   help="위에서 이만큼 제외 (상태바 — 앱이 안 그린다)")
    d.add_argument("--mask-bottom", type=int, default=0,
                   help="아래에서 이만큼 제외 (홈 인디케이터)")
    d.add_argument("--min-area", type=int, default=200,
                   help="이 넓이 미만 덩어리는 보고하지 않는다")
    d.add_argument("--probe-shift", type=int, default=40,
                   help="렌더를 ±이 픽셀만큼 옮겨 보며 '통째로 밀림'인지 가린다 (0=끄기)")
    d.set_defaults(func=cmd_diff)
    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help(sys.stderr)
        return 1
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
