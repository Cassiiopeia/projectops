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
            raise ValueError(f"--bg must be in RRGGBB format: {text}")
        return tuple(int(v[i:i + 2], 16) for i in (0, 2, 4)), f"#{v.upper()}"
    corner = design_img.getpixel((0, 0))
    if len(corner) == 4 and corner[3] == 255:
        return corner[:3], "design top-left pixel"
    return (255, 255, 255), "white (design corner is transparent)"


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


def _size_mismatch_report(render_size, design_size) -> dict:
    """크기가 다를 때의 경고: 가로세로 비율까지 다르면 비교가 사실상 무의미하다"""
    render_ratio = render_size[0] / render_size[1]
    design_ratio = design_size[0] / design_size[1]
    return {
        "render": f"{render_size[0]}x{render_size[1]}",
        "design": f"{design_size[0]}x{design_size[1]}",
        "scale_x": round(design_size[0] / render_size[0], 3),
        "aspect_changed": abs(render_ratio - design_ratio) / design_ratio > 0.01,
        "warning": ("The render was resized to the design size before comparing. When device widths differ "
                    "(e.g. 440 vs 393) text and spacing differences show up falsely, so re-rendering "
                    "at the same width is accurate"),
    }


def cmd_diff(args) -> int:
    missing = _require_imaging()
    if missing is not None:
        return missing
    import numpy as np
    from PIL import Image

    for label, p in (("render", args.render), ("design", args.design)):
        if not Path(p).is_file():
            return emit({"ok": False, "code": "image_not_found",
                         "error": f"{label} image not found: {p}"})

    try:
        design_img = Image.open(args.design).convert("RGBA")
        render_img = Image.open(args.render).convert("RGBA")
    except Exception as e:   # 이미지가 아닌 파일은 트레이스백 대신 JSON 으로 (#710)
        return emit({"ok": False, "code": "image_unreadable",
                     "error": f"Cannot open the image: {type(e).__name__}: {e}",
                     "next": "Check that --render and --design are image files such as png or jpg"})
    if args.mask_top < 0 or args.mask_bottom < 0 \
            or args.mask_top + args.mask_bottom >= design_img.size[1]:
        return emit({"ok": False, "code": "bad_mask",
                     "error": (f"--mask-top({args.mask_top}) + --mask-bottom({args.mask_bottom}) must be "
                               f"non-negative and smaller than the image height ({design_img.size[1]}px)"),
                     "next": "Exclude only the status bar and home indicator heights"})
    try:
        bg, bg_src = _parse_bg(args.bg, design_img)
    except ValueError as e:
        return emit({"ok": False, "code": "bad_bg", "error": str(e)})

    def flatten(img):
        base = Image.new("RGBA", img.size, (*bg, 255))
        return np.asarray(Image.alpha_composite(base, img).convert("RGB"), dtype=np.int16)

    design = flatten(design_img)
    size_mismatch = None
    if render_img.size != design_img.size:
        size_mismatch = _size_mismatch_report(render_img.size, design_img.size)
        if args.strict_size:
            return emit({"ok": False, "code": "size_mismatch", **size_mismatch,
                         "error": "Render and design sizes differ (--strict-size)",
                         "next": "Re-render at the same device width and scale, or match the design frame size"})
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
        # 크기가 달라 렌더를 디자인 크기로 늘이거나 줄인 채 비교했다 — 글자 크기·간격 차이가 가짜로 생길 수 있다 (#949)
        **({"size_mismatch": size_mismatch} if size_mismatch else {}),
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
        "summary": (f"different pixels {pct:.2f}% · {len(found)} clusters "
                    f"(max channel delta {int(delta.max())})"),
        "next": (
            (f"There are {len(found)} clusters, but shifting the render by "
             f"({shift['dx']:+d}, {shift['dy']:+d}) drops the difference from "
             f"{shift['before']}% → {shift['after']}%. "
             "**It is not many separate mismatches but one block shifted as a whole** — look "
             "first at the container holding it (height, padding, safe area), not the elements inside."
             if (shift or {}).get("looks_shifted") else
             "Look at **cluster positions**, not the percentage. Clusters on text are rasterization "
             "differences and usually harmless; clusters on shapes or spacing are real mistakes. "
             "Shadows, glows and 1px borders vanish on a full-screen diff, so check them again per component")),
    })
