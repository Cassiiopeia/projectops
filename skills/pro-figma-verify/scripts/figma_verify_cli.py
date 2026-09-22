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


def _walk(node, path, out, want_id=None, inside=False):
    """덤프를 훑어 스타일 항목을 모은다.

    덤프 모양이 도구·버전마다 달라서 키 이름을 고정하지 않고 재귀로 찾는다.
    구조를 단정하면 다음 버전에서 **조용히 0건**이 된다.
    """
    if isinstance(node, list):
        for i, child in enumerate(node):
            _walk(child, f"{path}[{i}]", out, want_id, inside)
        return
    if not isinstance(node, dict):
        return

    node_id = node.get("id")
    node_name = node.get("name")
    here = inside or want_id is None or (node_id == want_id)

    if here and (node_id or node_name):
        label = node_id or node_name
        for kind, aliases in _STYLE_KEYS.items():
            for key in aliases:
                if key not in node:
                    continue
                value = node[key]
                if value in (None, [], {}, ""):
                    continue
                # 배열은 **원소마다 한 줄**로 쪼갠다. 통째로 한 줄이면
                # 네 줄짜리 effects 에서 한 줄이 빠져도 티가 안 난다.
                if isinstance(value, list):
                    for i, item in enumerate(value):
                        out.append({"ref": f"{label}/{key}[{i}]", "kind": kind,
                                    "name": node_name, "value": _describe(item)})
                else:
                    out.append({"ref": f"{label}/{key}", "kind": kind,
                                "name": node_name, "value": _describe(value)})

    for k, v in node.items():
        if isinstance(v, (dict, list)) and k not in ("fills", "strokes", "effects"):
            _walk(v, f"{path}.{k}", out, want_id, here)


def cmd_coverage(args) -> int:
    path = Path(args.dump)
    if not path.is_file():
        return emit({"ok": False, "code": "dump_not_found",
                     "error": f"덤프 파일이 없습니다: {args.dump}",
                     "hint": "Figma MCP 로 받은 덤프를 JSON 파일로 저장한 뒤 넘기세요"})
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return emit({"ok": False, "code": "dump_unreadable", "error": str(e)})

    items: list[dict] = []
    _walk(data, "$", items, args.node)

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
        "summary": f"분류해야 할 스타일 항목 {len(items)}개 " +
                   " · ".join(f"{k} {v}" for k, v in sorted(counts.items())),
        "next": ("각 항목을 구현 / 근사(사유) / 생략(사유) 중 하나로 분류하세요. "
                 "근사·생략은 사유를 반드시 적습니다 — 적지 않으면 나중에 "
                 "못 옮긴 것인지 안 옮기기로 한 것인지 구분할 수 없습니다"),
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
        "diff_image": out_path,
        "summary": (f"다른 픽셀 {pct:.2f}% · 덩어리 {len(found)}개 "
                    f"(최대 채널차 {int(delta.max())})"),
        "next": ("퍼센트가 아니라 **덩어리 위치**를 보세요. 글자 자리면 래스터라이즈 "
                 "차이라 대개 무해하고, 도형·여백 자리면 실제로 틀린 것입니다. "
                 "그림자·발광·1px 테두리는 전체 화면에서 사라지므로 component 로 다시 봅니다"),
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
