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
                     "error": f"덤프 파일이 없습니다: {args.dump}"})
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
                     "error": f"렌더 이미지가 없습니다: {args.render}"})

    try:
        img = Image.open(render).convert("RGB")
    except Exception as e:   # 이미지가 아닌 파일 (#710)
        return emit({"ok": False, "code": "image_unreadable",
                     "error": f"렌더 이미지를 열 수 없습니다: {render} ({type(e).__name__})",
                     "next": "png·jpg 같은 이미지 파일인지 확인한다"})
    # 없는 노드·모르는 검사가 "0건 통과"로 끝나면 대조를 안 한 것과 같다 (#710)
    checks = [c.strip() for c in args.check.split(",") if c.strip()] if args.check \
        else list(_ALL_CHECKS)
    bad = [c for c in checks if c not in _ALL_CHECKS]
    if bad or (args.check and not checks):
        return emit({"ok": False, "code": "unknown_check",
                     "error": f"모르는 검사: {bad or args.check!r}",
                     "hint": f"쓸 수 있는 것: {', '.join(_ALL_CHECKS)}"})
    if args.node and not _has_node(data, args.node):
        return emit({"ok": False, "code": "node_not_found",
                     "error": f"덤프에 노드 {args.node} 가 없습니다",
                     "hint": "노드 id 는 덤프의 id 와 정확히 같아야 합니다 (예: 1:100). coverage 로 id 를 먼저 확인하세요"})

    styles = _style_table(data)
    rects, skipped = _rects(data, styles, args.node)
    if not rects and not skipped:
        return emit({"ok": True, "checked": 0, "findings": [],
                     "summary": "둥근 모서리를 가진 사각형이 없습니다",
                     "next": "borderRadius 가 있는 노드를 포함하는지 --node 를 확인하세요"})

    scale, scale_from = args.scale, "지정"
    if scale <= 0:
        # 렌더 폭 ÷ 기준 노드 폭. 3배로 찍은 화면을 논리 좌표로 재면 다 어긋난다.
        base = _node_width(data.get("nodes", data), styles, args.node)
        if base:
            scale, scale_from = img.size[0] / base, f"렌더 {img.size[0]}px ÷ 기준 {base:g}"
        else:
            scale, scale_from = 1.0, "기준 노드 폭을 못 찾아 1배로 가정"

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
        "summary": (f"사각형 {len(rects)}개 · {'·'.join(checks)} 검사 (배율 {scale:g}) — "
                    + (" · ".join(f"{k} {v}" for k, v in sorted(by_sev.items()))
                       if findings else "이상 없음")
                    + (f" · 위치를 몰라 건너뜀 {len(skipped)}개" if skipped else "")),
        "next": ("각 `says` 가 고칠 자리를 그대로 말해 줍니다. 모서리가 각졌다면 "
                 "**라운드를 안 준 것이 아니라 준 라운드를 자식이 덮은 경우**가 흔합니다 — "
                 "부모가 배경만 둥글게 칠하고 자식을 자르지 않으면(클리핑 꺼짐) "
                 "자식이 깐 배경색이 둥근 자리를 메웁니다"
                 if findings else
                 "기하·색·그림자는 맞습니다. 나머지 속성은 coverage 로 대조하세요"),
    })
