"""assets: group assets to download > assign file names > list"""
from __future__ import annotations

import json
from pathlib import Path

from common.emit import emit
from figma_tools.dump_reader import _load_dump, _slug, _style_table, _walk


def _download_plan(assets: list[dict]) -> dict:
    """Group so the same image is not downloaded twice, and give file names that will not be rejected.

    Measured: of 609 asset nodes only about 60 were distinct images. A naive walk
    downloads 609 times and 592 **overwrite each other** under the same file name.
    """
    groups: dict[tuple, dict] = {}
    for a in assets:
        # Instances of the same component are **certainly** the same image. Otherwise even the
        # same name can be a different image (Figma's default name 'Vector' is the classic case —
        # measured 48 distinct out of 71), so group only when the whole node is identical.
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
        # Nodes with imageRef are photos, so png; other vectors are fetched as svg
        ext = "png" if item.get("image") else "svg"
        slug = item["slug"]
        taken[slug] = taken.get(slug, 0) + 1
        if taken[slug] > 1:                      # number duplicates to tell them apart
            slug = f"{slug}-{taken[slug]}"
        item["file_name"] = f"{slug}.{ext}"
        item.pop("slug", None)
        item.pop("_print", None)          # internal identity value — not exposed
        item["also"] = item["also"][:5]   # only a few grouped nodes (for review)
        unique.append(item)

    nodes = []
    for item in unique:
        entry = {"nodeId": item["node_id"], "fileName": item["file_name"]}
        img = item.get("image")
        if img:
            # Photos come back wrong without imageRef. Crop and size arguments
            # go in only as the dump says (not added when default).
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
