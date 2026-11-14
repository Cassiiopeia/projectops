"""diff: pixel-compare the design export against the app render"""
from __future__ import annotations

from pathlib import Path

from common.emit import emit
from figma_tools.data_regions import DATA_KINDS, find_data_regions, find_node_regions, parse_data_kinds
from figma_tools.dump_reader import _load_dump
from figma_tools.imaging import _require_imaging
from figma_tools.solid_blobs import find_solid_blobs
from figma_tools.text_rows import compare_rows


# =========================================================================
# diff — overlay the images
# =========================================================================


def _parse_bg(text, design_img):
    """Decide the compositing background color.

    The app render keeps outer glow semi-transparent, while the design export arrives composited on its background.
    Unless both sit on the same background, **the whole glow registers as 'different'** and diff
    loses its meaning. A hard-coded color is wrong in other projects, so it is read from the design.
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
    """Box up clusters of differing pixels.

    Reporting pixel by pixel drowns in anti-aliasing noise. Scanning by row and
    merging overlapping boxes is enough for a person to decide where to look.
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
    """Shift the render a little at a time to tell whether **everything moved as one**.

    Real incident: the sheet's top edge sat 35px lower and its steps·rewards·button **all showed
    doubled**. Ten blobs came out but only one thing was wrong — the container height. Counting blobs
    alone reads as "ten places are off" and leads to fixing the wrong things.

    Vertical first. Screens stack vertically, so shifts are usually vertical too.
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
    """Warning for size mismatch: if the aspect ratio also differs, the comparison is practically meaningless"""
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


def _data_regions(args, image_width: int):
    """Validate --mask-data · --mask-node input > (data boxes, None) or (None, error payload)"""
    kinds = parse_data_kinds(args.mask_data) if args.mask_data else ()
    if kinds is None:
        return None, {"ok": False, "code": "bad_mask_data",
                      "error": f"--mask-data accepts {', '.join(DATA_KINDS)} (comma-separated): {args.mask_data!r}"}
    if not args.dump:
        return None, {"ok": False, "code": "dump_required",
                      "error": "--mask-data and --mask-node need --dump (and --node) to know where the data sits"}
    dump_path = Path(args.dump)
    if not dump_path.is_file():
        return None, {"ok": False, "code": "dump_not_found", "error": f"Dump file not found: {args.dump}"}
    data, error = _load_dump(dump_path)
    if error:
        return None, {"ok": False, "code": error[0], "error": error[1]}
    regions = find_data_regions(data, args.node, kinds, image_width) if kinds else {"boxes": [], "skipped": []}
    if args.mask_node:
        picked = find_node_regions(data, args.node, args.mask_node, image_width)
        regions["boxes"] += picked["boxes"]
        regions["missing_nodes"] = picked["missing"]
    return regions, None


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
    except Exception as e:   # non-image files return JSON instead of a traceback (#710)
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
    excluded = np.zeros(delta.shape, dtype=bool)
    if args.mask_top:
        excluded[:args.mask_top] = True
    if args.mask_bottom:
        excluded[-args.mask_bottom:] = True

    # Exclude data regions (text length·photo differences in mock data are not defects)
    data_regions = None
    if args.mask_data or args.mask_node:
        data_regions, error = _data_regions(args, design.shape[1])
        if error:
            return emit(error)
        for box in data_regions["boxes"]:
            excluded[max(box["y0"], 0):box["y1"], max(box["x0"], 0):box["x1"]] = True
    delta[excluded] = 0

    mask = delta > args.threshold
    compared = delta.size - int(excluded.sum())
    pct = 100.0 * int(mask.sum()) / max(compared, 1)

    found = []
    for x0, y0, x1, y1 in _clusters(mask, args.min_area):
        region = delta[y0:y1 + 1, x0:x1 + 1]
        hot = region[region > args.threshold]
        found.append({"x": x0, "y": y0, "w": x1 - x0 + 1, "h": y1 - y0 + 1,
                      "mean_delta": round(float(hot.mean()), 1)})

    # Optional checks: color fills present on one side only · text line height (surface defects even when the score is low)
    solids = find_solid_blobs(design, render, mask, args.min_area, args.threshold) if args.solids else None
    rows = None
    if args.rows:
        scale = (args.scale or 1.0)
        rows = compare_rows(design, render, args.mask_top, args.mask_bottom, scale)

    # With several blobs, tell "each one wrong" from "one thing shifted".
    shift = None
    if found and args.probe_shift > 0:
        shift = _shift_probe(design, render, args.threshold, args.probe_shift)
        # If shifting drops it below half, treat it as a shift. Small improvements
        # also come from anti-aliasing, so they do not count as a signal.
        shift["looks_shifted"] = bool(
            (shift["dy"] or shift["dx"])
            and shift["after"] <= shift["before"] * 0.5)

    out_path = None
    if args.out:
        # Lay the original faintly and paint only differing spots red — shows at once what is wrong.
        canvas = (design * 0.35 + 255 * 0.65).astype(np.uint8)
        canvas[mask] = [255, 0, 0]
        if data_regions:
            canvas[excluded & ~mask] = [200, 200, 255]   # excluded data regions in light blue
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(canvas).save(args.out)
        out_path = str(args.out)

    return emit({
        # Sizes differ, so the render was scaled to design size before comparing — text size·spacing differences may be spurious (#949)
        **({"size_mismatch": size_mismatch} if size_mismatch else {}),
        **({"data_excluded": {"kinds": list(parse_data_kinds(args.mask_data or "") or ()) + (["node"] if args.mask_node else []),
                              "missing_nodes": data_regions.get("missing_nodes", []),
                              "box_count": len(data_regions["boxes"]),
                              "boxes": data_regions["boxes"],
                              "position_unknown": data_regions["skipped"],
                              "note": ("Text content and photos were not compared by pixels. Check text "
                                       "styles (font, size, weight, color) by value with coverage, and that "
                                       "long data still fits (wrapping, ellipsis) on its own")}}
           if data_regions else {}),
        "size": f"{design.shape[1]}x{design.shape[0]}",
        "background": bg_src,
        "threshold": args.threshold,
        "different_pixels": int(mask.sum()),
        "compared_pixels": int(compared),
        "different_percent": round(pct, 2),
        "max_delta": int(delta.max()),
        "clusters": found,
        **({"solid_blobs": solids} if solids is not None else {}),
        **({"text_rows": rows} if rows is not None else {}),
        "shift_probe": shift,
        "diff_image": out_path,
        "summary": (f"different pixels {pct:.2f}% · {len(found)} clusters "
                    f"(max channel delta {int(delta.max())})"
                    + (f" · {len(solids)} solid blob(s) only on one side" if solids else "")
                    + (f" · text rows: {rows['shifted_rows']} shifted, {rows['unpaired_rows']} unpaired"
                       if rows else "")),
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
