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
                     "error": f"Dump file not found: {args.dump}"})
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
                     "summary": "No asset nodes to download",
                     "next": "Icons may be drawn as shapes (RECTANGLE, ELLIPSE). "
                             "Check the element list from coverage directly"})

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
        "summary": (f"{len(assets)} asset nodes → {len(plan['unique'])} to actually download"
                    + (f" ({len(renames)} got an automatic name because the name did not survive as ASCII)"
                       if renames else "")
                    + (f" · {len(baked)} come with the effect baked into the image" if baked else "")),
        "warning": ("The dump has **no shape information** for icons. Nodes with the same "
                    "componentId are certainly the same image (certain=true); the rest were "
                    "grouped only because their node contents match — check them by eye after "
                    "downloading. Assets with baked_effect come with that effect **baked into "
                    "the image as a filter**, so the downloaded image is larger than "
                    "width/height. Squeezing it into the layout size shrinks the shape, and "
                    "adding the effect again in code applies it twice"),
        "next": ("Pass `nodes` as-is to the nodes argument of mcp__figma__download_figma_images "
                 "and give localPath an **absolute path**. Entries with rename_me true lost "
                 "their meaning because the original name was Korean or similar, so look at "
                 "name and pass a meaningful English name instead. After downloading, always "
                 "check the file count and that no file is 0 bytes — downloads have been "
                 "reported as done when nothing was saved"),
    })
