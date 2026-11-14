"""conform: compare by property whether it was drawn to the design values"""
from __future__ import annotations

from pathlib import Path

from common.emit import emit
from figma_tools.conform_probes import (_ALL_CHECKS, _SEVERITY_ORDER, _check_fills, _check_shadows,
                                        _has_node, _node_width, _probe_corners, _rects,
                                        layers_above, layers_below)
from figma_tools.conform_placement import check_placement, system_node_ids
from figma_tools.dump_reader import _load_dump, _style_table
from figma_tools.imaging import _require_imaging


def cmd_conform(args) -> int:
    missing = _require_imaging()
    if missing is not None:
        return missing
    from PIL import Image
    path = Path(args.dump)
    if not path.is_file():
        return emit({"ok": False, "code": "dump_not_found",
                     "error": f"Dump file not found: {args.dump}"})
    data, derr = _load_dump(path)
    if derr:
        code, msg, hint = derr
        out = {"ok": False, "code": code, "error": msg}
        if hint:
            out["hint"] = hint
        return emit(out)
    render = Path(args.render)
    if not render.is_file():
        return emit({"ok": False, "code": "render_not_found",
                     "error": f"Render image not found: {args.render}"})

    try:
        img = Image.open(render).convert("RGB")
    except Exception as e:   # not an image file (#710)
        return emit({"ok": False, "code": "image_unreadable",
                     "error": f"Cannot open the render image: {render} ({type(e).__name__})",
                     "next": "Check that it is an image file such as png or jpg"})
    # A missing node or unknown check ending in "0 passed" is the same as not comparing (#710)
    checks = [c.strip() for c in args.check.split(",") if c.strip()] if args.check \
        else list(_ALL_CHECKS)
    bad = [c for c in checks if c not in _ALL_CHECKS]
    if bad or (args.check and not checks):
        return emit({"ok": False, "code": "unknown_check",
                     "error": f"Unknown check: {bad or args.check!r}",
                     "hint": f"Available: {', '.join(_ALL_CHECKS)}"})
    if args.node and not _has_node(data, args.node):
        return emit({"ok": False, "code": "node_not_found",
                     "error": f"Node {args.node} is not in the dump",
                     "hint": "The node id must match the id in the dump exactly (e.g. 1:100). Check the id with coverage first"})

    styles = _style_table(data)
    rects, skipped = _rects(data, styles, args.node)
    # Rectangles inside system-drawn bands (status bar · home indicator) are not drawn by the app > excluded (logical coords)
    frame_height = max((r["y"] + r["height"] for r in rects), default=0)
    in_band = [r for r in rects
               if r["y"] + r["height"] <= args.mask_top
               or (args.mask_bottom and r["y"] >= frame_height - args.mask_bottom)]
    rects = [r for r in rects if r not in in_band]
    # Exclude given nodes (data-filled slots such as the designer's photo placeholders)
    masked_nodes = [r for r in rects if r["ref"] in (args.mask_node or [])]
    # Auto-exclude OS-drawn nodes (names: status bar · home indicator · keyboard)
    system_ids = system_node_ids(data)
    system_nodes = [r for r in rects if r["ref"] in system_ids]
    rects = [r for r in rects if r not in masked_nodes and r not in system_nodes]
    if not rects and not skipped:
        return emit({"ok": True, "checked": 0, "findings": [],
                     "summary": "No rectangles with rounded corners",
                     "next": "Check that --node includes nodes with borderRadius"})

    scale, scale_from = args.scale, "given"
    if scale <= 0:
        # Render width ÷ reference node width. Measuring a 3x capture in logical coords misaligns everything.
        base = _node_width(data.get("nodes", data), styles, args.node)
        if base:
            scale, scale_from = img.size[0] / base, f"render {img.size[0]}px / origin {base:g}"
        else:
            scale, scale_from = 1.0, "origin node width not found, assuming 1x"

    W, H = img.size

    def sample(lx, ly):
        px, py = int(round(lx * scale)), int(round(ly * scale))
        if not (0 <= px < W and 0 <= py < H):
            return None
        return img.getpixel((px, py))[:3]

    findings = []
    for index, r in enumerate(rects):
        above = layers_above(rects, index)
        # Placement first: a shifted box makes the corner probe hit inside the face, a false "각짐" > skip corners
        is_placed = None
        if "placement" in checks:
            placement_findings, is_placed = check_placement(sample, r, above, layers_below(rects, index),
                                                            args.tolerance)
            findings.extend(placement_findings)
        if "corners" in checks and is_placed is not False:
            for f in _probe_corners(img, r, scale, args.tolerance, above,
                                    layers_below(rects, index)):
                findings.append({"check": "corners", "severity": "high",
                                 "ref": r["ref"], **f})
        if "fills" in checks:
            findings.extend(_check_fills(sample, r, args.tolerance, above))
        if "shadows" in checks:
            findings.extend(_check_shadows(sample, r, args.tolerance))

    findings.sort(key=lambda f: -_SEVERITY_ORDER.get(f.get("severity"), 0))
    by_sev = {}
    for f in findings:
        by_sev[f["severity"]] = by_sev.get(f["severity"], 0) + 1

    gate = _SEVERITY_ORDER.get(args.fail_on, 0)
    worst = max((_SEVERITY_ORDER.get(f["severity"], 0) for f in findings), default=0)
    failed = bool(gate) and worst >= gate

    return emit({
        "ok": not failed,
        "code": "conformance_failed" if failed else "ok",
        "checks": checks,
        "checked": len(rects), "skipped_unknown_position": len(skipped),
        "skipped_system_bands": len(in_band), "skipped_masked_nodes": [r["ref"] for r in masked_nodes],
        "skipped_system_nodes": len(system_nodes),
        "scale": round(scale, 4), "scale_from": scale_from,
        "render_size": list(img.size),
        "findings": findings, "by_severity": by_sev,
        "summary": (f"{len(rects)} rectangles · {'·'.join(checks)} checks (scale {scale:g}) — "
                    + (" · ".join(f"{k} {v}" for k, v in sorted(by_sev.items()))
                       if findings else "no issues")
                    + (f" · {len(skipped)} skipped (position unknown)" if skipped else "")),
        "next": ("Each `says` names the exact spot to fix. When a corner is square, it is "
                 "usually **not a missing radius but a child covering the radius** — if the "
                 "parent only paints a rounded background and does not clip its children "
                 "(clipping off), the child's background fills the rounded area"
                 if findings else
                 "Geometry, colors and shadows match. Compare the remaining properties with coverage"),
    })
