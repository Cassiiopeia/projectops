"""diff: 시안 export 와 앱 렌더를 픽셀로 맞댐"""
from __future__ import annotations

from pathlib import Path

from common.emit import emit
from figma_tools.imaging import _require_imaging


# =========================================================================
# diff — 그림으로 맞댄다
# =========================================================================


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

    try:
        design_img = Image.open(args.design).convert("RGBA")
        render_img = Image.open(args.render).convert("RGBA")
    except Exception as e:   # 이미지가 아닌 파일은 트레이스백 대신 JSON 으로 (#710)
        return emit({"ok": False, "code": "image_unreadable",
                     "error": f"이미지를 열 수 없습니다: {type(e).__name__}: {e}",
                     "next": "--render · --design 이 png·jpg 같은 이미지 파일인지 확인한다"})
    if args.mask_top < 0 or args.mask_bottom < 0 \
            or args.mask_top + args.mask_bottom >= design_img.size[1]:
        return emit({"ok": False, "code": "bad_mask",
                     "error": (f"--mask-top({args.mask_top}) + --mask-bottom({args.mask_bottom}) 는 "
                               f"이미지 높이({design_img.size[1]}px) 보다 작은 0 이상 값이어야 합니다"),
                     "next": "상태바·홈 인디케이터 높이만큼만 제외한다"})
    try:
        bg, bg_src = _parse_bg(args.bg, design_img)
    except ValueError as e:
        return emit({"ok": False, "code": "bad_bg", "error": str(e)})

    def flatten(img):
        base = Image.new("RGBA", img.size, (*bg, 255))
        return np.asarray(Image.alpha_composite(base, img).convert("RGB"), dtype=np.int16)

    design = flatten(design_img)
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
