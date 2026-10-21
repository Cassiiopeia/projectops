"""coverage: 덤프의 스타일 항목을 빠짐없이 나열"""
from __future__ import annotations

from pathlib import Path

from common.emit import emit
from figma_tools.dump_reader import _load_dump, _style_table, _walk


def cmd_coverage(args) -> int:
    path = Path(args.dump)
    if not path.is_file():
        return emit({"ok": False, "code": "dump_not_found",
                     "error": f"Dump file not found: {args.dump}",
                     "hint": "Save the dump from Figma MCP to a file and pass that (JSON and YAML both work)"})
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
    assets: list[dict] = []
    styles = _style_table(data)
    _walk(data, "$", items, args.node, hidden=hidden, elements=elements, styles=styles,
          assets=assets)

    if not items:
        return emit({
            "ok": False, "code": "no_style_found",
            "error": "No style entries found in the dump",
            "hint": ("Check that the node id is right and that the dump includes styles. "
                     "Passing silently with 0 entries is the same as not comparing at all"),
        })

    counts: dict[str, int] = {}
    for it in items:
        counts[it["kind"]] = counts.get(it["kind"], 0) + 1

    # 효과는 layout 수십 줄 사이에 묻히면 아무도 안 본다. **따로 꺼내 놓는다** —
    # 실제로 빠뜨리는 것이 늘 이쪽이었다 (안쪽 그림자·글로우·배경 블러).
    effects = [it for it in items if it["kind"] == "effects"]
    by_effect: dict[str, int] = {}
    for it in effects:
        by_effect[it.get("effect") or "effect"] = by_effect.get(it.get("effect") or "effect", 0) + 1

    return emit({
        "node": args.node,
        "items": items,
        "counts": counts,
        "total": len(items),
        "elements": elements,
        "element_count": len(elements),
        "effects": effects,
        "effect_counts": by_effect,
        "asset_count": len(assets),
        "styles_resolved": len(styles),
        "hidden_skipped": hidden,
        "summary": (f"{len(elements)} elements · {len(items)} style entries " +
                    " · ".join(f"{k} {v}" for k, v in sorted(counts.items())) +
                    (f" · {len(assets)} assets" if assets else "") +
                    (f" ({len(hidden)} hidden layers skipped)" if hidden else "") +
                    (" | effects " + " · ".join(f"{k} {v}" for k, v in sorted(by_effect.items()))
                     if by_effect else "")),
        "next": ("Check in four layers. (1) Is each **element** on screen — elements that "
                 "are in the design but missing from the screen really happen. (2) Go through "
                 "**effects** line by line — inner shadow, glow and background blur are missed "
                 "most often, and are barely visible when missing. (3) The remaining **style "
                 "entries**. (4) If there are assets, get the download list with the `assets` "
                 "subcommand. Classify (1)-(3) as implemented / approximated (reason) / "
                 "omitted (reason), and always write the reason for approximated and omitted — "
                 "without it you cannot later tell whether something could not be ported or "
                 "was deliberately left out"),
    })
