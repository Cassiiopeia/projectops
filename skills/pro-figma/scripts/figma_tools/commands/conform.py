"""conform: 시안 값대로 그려졌는지 속성으로 대조"""
from __future__ import annotations

from pathlib import Path

from common.emit import emit
from figma_tools.conform_probes import (_ALL_CHECKS, _SEVERITY_ORDER, _check_fills, _check_shadows,
                                        _has_node, _node_width, _probe_corners, _rects)
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
    except Exception as e:   # 이미지가 아닌 파일 (#710)
        return emit({"ok": False, "code": "image_unreadable",
                     "error": f"Cannot open the render image: {render} ({type(e).__name__})",
                     "next": "Check that it is an image file such as png or jpg"})
    # 없는 노드·모르는 검사가 "0건 통과"로 끝나면 대조를 안 한 것과 같다 (#710)
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
    if not rects and not skipped:
        return emit({"ok": True, "checked": 0, "findings": [],
                     "summary": "No rectangles with rounded corners",
                     "next": "Check that --node includes nodes with borderRadius"})

    scale, scale_from = args.scale, "given"
    if scale <= 0:
        # 렌더 폭 ÷ 기준 노드 폭. 3배로 찍은 화면을 논리 좌표로 재면 다 어긋난다.
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
    for r in rects:
        if "corners" in checks:
            for f in _probe_corners(img, r, scale, args.tolerance):
                findings.append({"check": "corners", "severity": "high",
                                 "ref": r["ref"], **f})
        if "fills" in checks:
            findings.extend(_check_fills(sample, r, args.tolerance))
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
