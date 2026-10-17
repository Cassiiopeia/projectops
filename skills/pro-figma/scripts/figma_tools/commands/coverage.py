"""coverage: 덤프의 스타일 항목을 빠짐없이 나열"""
from __future__ import annotations

from pathlib import Path

from common.emit import emit
from figma_tools.dump_reader import _load_dump, _style_table, _walk


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
    assets: list[dict] = []
    styles = _style_table(data)
    _walk(data, "$", items, args.node, hidden=hidden, elements=elements, styles=styles,
          assets=assets)

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

    # 효과는 layout 수십 줄 사이에 묻히면 아무도 안 본다. **따로 꺼내 놓는다** —
    # 실제로 빠뜨리는 것이 늘 이쪽이었다 (안쪽 그림자·글로우·배경 블러).
    effects = [it for it in items if it["kind"] == "effects"]
    by_effect: dict[str, int] = {}
    for it in effects:
        by_effect[it.get("effect") or "효과"] = by_effect.get(it.get("effect") or "효과", 0) + 1

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
        "summary": (f"요소 {len(elements)}개 · 스타일 항목 {len(items)}개 " +
                    " · ".join(f"{k} {v}" for k, v in sorted(counts.items())) +
                    (f" · 에셋 {len(assets)}개" if assets else "") +
                    (f" (꺼 둔 레이어 {len(hidden)}개 제외)" if hidden else "") +
                    (" | 효과 " + " · ".join(f"{k} {v}" for k, v in sorted(by_effect.items()))
                     if by_effect else "")),
        "next": ("네 층으로 확인하세요. ① **요소**가 화면에 있는가 — 시안에 있는데 "
                 "화면에 아예 없는 것이 실제로 나옵니다. ② **effects** 를 한 줄씩 — "
                 "안쪽 그림자·글로우·배경 블러가 가장 자주 빠지고, 빠져도 눈으로는 "
                 "거의 안 보입니다. ③ 나머지 **스타일 항목**. ④ 에셋이 있으면 "
                 "`assets` 서브커맨드로 내려받을 목록을 받으세요. "
                 "①~③ 은 구현 / 근사(사유) / 생략(사유) 로 분류하고, 근사·생략은 "
                 "사유를 반드시 적습니다 — 적지 않으면 못 옮긴 것인지 안 옮기기로 "
                 "한 것인지 나중에 구분할 수 없습니다"),
    })
