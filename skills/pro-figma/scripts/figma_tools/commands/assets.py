"""assets: 내려받을 에셋 묶기 > 파일명 부여 > 목록"""
from __future__ import annotations

import json
from pathlib import Path

from common.emit import emit
from figma_tools.dump_reader import _load_dump, _slug, _style_table, _walk


def _download_plan(assets: list[dict]) -> dict:
    """같은 그림을 여러 번 받지 않도록 묶고, 거부되지 않을 파일명을 붙인다.

    실측: 에셋 노드 609개 중 실제로 서로 다른 그림은 60여 개였다. 순진하게 훑으면
    609번 내려받고 592개가 같은 파일명으로 **서로 덮어쓴다**.
    """
    groups: dict[tuple, dict] = {}
    for a in assets:
        # 같은 컴포넌트를 꽂은 것이면 같은 그림이 **확실하다**. 그 외에는 이름이
        # 같아도 다른 그림일 수 있어(Figma 기본 이름 'Vector' 가 대표적 —
        # 실측 71개 중 48종이 서로 달랐다) 노드 전체가 똑같을 때만 묶는다.
        key = (("c", a["component_id"]) if a.get("component_id")
               else ("p", json.dumps(a.get("image"), sort_keys=True), a["_print"]))
        hit = groups.get(key)
        if hit:
            hit["used"] += 1
            hit["also"].append(a["node_id"])
            continue
        slug, lost_meaning = _slug(a.get("name"), a["node_id"])
        groups[key] = dict(a, used=1, also=[], slug=slug, rename_me=lost_meaning,
                           certain=bool(a.get("component_id")))

    taken: dict[str, int] = {}
    unique = []
    for item in groups.values():
        # imageRef 가 붙은 것은 사진이라 png, 나머지 벡터는 svg 로 받는다
        ext = "png" if item.get("image") else "svg"
        slug = item["slug"]
        taken[slug] = taken.get(slug, 0) + 1
        if taken[slug] > 1:                      # 이름이 겹치면 번호를 붙여 구분
            slug = f"{slug}-{taken[slug]}"
        item["file_name"] = f"{slug}.{ext}"
        item.pop("slug", None)
        item.pop("_print", None)          # 신원 판정용 내부 값 — 밖으로 내보내지 않는다
        item["also"] = item["also"][:5]   # 같이 묶인 노드 몇 개만 (점검용)
        unique.append(item)

    nodes = []
    for item in unique:
        entry = {"nodeId": item["node_id"], "fileName": item["file_name"]}
        img = item.get("image")
        if img:
            # 사진은 imageRef 가 없으면 엉뚱한 게 온다. 자르기·크기 인자는
            # 덤프가 알려준 대로만 넣는다 (기본값이면 넣지 않는다).
            entry["imageRef"] = img["imageRef"]
            if img.get("needsCropping"):
                entry["needsCropping"] = True
                if img.get("cropTransform"):
                    entry["cropTransform"] = img["cropTransform"]
            if img.get("requiresImageDimensions"):
                entry["requiresImageDimensions"] = True
        nodes.append(entry)
    return {"unique": unique, "nodes": nodes}


def cmd_assets(args) -> int:
    path = Path(args.dump)
    if not path.is_file():
        return emit({"ok": False, "code": "dump_not_found",
                     "error": f"덤프 파일이 없습니다: {args.dump}"})
    data, err = _load_dump(path)
    if err:
        code, msg, hint = err
        out = {"ok": False, "code": code, "error": msg}
        if hint:
            out["hint"] = hint
        return emit(out)

    items, hidden, elements, assets = [], [], [], []
    _walk(data, "$", items, args.node, hidden=hidden, elements=elements,
          styles=_style_table(data), assets=assets)
    if not assets:
        return emit({"ok": True, "total": 0, "unique": 0, "assets": [], "nodes": [],
                     "summary": "내려받을 에셋 노드가 없습니다",
                     "next": "아이콘이 도형(RECTANGLE·ELLIPSE)으로 그려져 있을 수 있습니다. "
                             "coverage 의 요소 목록에서 직접 확인하세요"})

    plan = _download_plan(assets)
    renames = [a for a in plan["unique"] if a.get("rename_me")]
    guessed = [a for a in plan["unique"] if not a.get("certain") and a["used"] > 1]
    baked = [a for a in plan["unique"] if a.get("baked_effect")]
    return emit({
        "total": len(assets), "unique": len(plan["unique"]),
        "assets": plan["unique"], "nodes": plan["nodes"],
        "needs_naming": len(renames),
        "merged_by_guess": len(guessed),
        "with_baked_effect": len(baked),
        "summary": (f"에셋 노드 {len(assets)}개 → 실제로 받을 것 {len(plan['unique'])}개"
                    + (f" (이름이 ASCII 로 안 남아 자동 이름이 붙은 것 {len(renames)}개)"
                       if renames else "")
                    + (f" · 효과가 그림에 박혀 오는 것 {len(baked)}개" if baked else "")),
        "warning": ("덤프에는 아이콘의 **모양 정보가 없습니다**. componentId 가 같은 것은 "
                    "같은 그림이 확실하지만(certain=true), 나머지는 노드 내용이 같다는 "
                    "것만 보고 묶었습니다 — 받은 뒤 눈으로 확인하세요. "
                    "baked_effect 가 있는 것은 그 효과가 **그림 안에 필터로 박혀** 오므로 "
                    "받은 그림이 width/height 보다 큽니다. 레이아웃 크기로 우겨 넣으면 "
                    "도형이 쪼그라들고, 효과를 코드로 또 넣으면 두 번 적용됩니다"),
        "next": ("`nodes` 를 그대로 mcp__figma__download_figma_images 의 nodes 인자로 "
                 "넘기고 localPath 에 **절대경로**를 줍니다. rename_me 가 true 인 것은 "
                 "원래 이름이 한글 등이라 뜻을 잃었으니, name 을 보고 의미 있는 영문 "
                 "이름으로 고쳐서 넘기세요. 받은 뒤 파일 개수와 크기 0 바이트 여부를 "
                 "반드시 확인합니다 — 받았다고 응답해 놓고 안 받아진 적이 있습니다"),
    })
