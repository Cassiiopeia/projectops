#!/usr/bin/env python3
"""figma_verify_cli — 시안과 구현 화면을 대조한다 (projectops 3-layer Layer 2).

**눈으로는 못 잡는다.** 어떤 버튼에서 효과 네 줄 중 안쪽 세 줄이 통째로 빠진 채
배포된 일이 있었다. 전체 화면 골든을 만들어 놓고도 지나갔다 — 361x68 안의 10px
안쪽 그림자는 그 크기에서 몇 픽셀이라 있으나 없으나 비슷해 보인다.

값 단언(`expect(shadow.blur, 10)`)도 절반만 막는다. **단언하기로 생각한 것만**
지킨다. 빠뜨린 줄은 애초에 단언도 안 썼으니 아무도 세지 않는다.

그래서 두 가지를 한다.

  coverage — 덤프의 스타일 항목을 **하나도 빠짐없이 나열**해 분류를 강제한다.
             값을 못 옮긴 것과 안 옮기기로 한 것을 구분하는 것이 요점이다.
  diff     — 그림으로 맞대 어디가 다른지 덩어리로 뽑는다.

판단은 사람이 한다. 이 스크립트는 **세고 나열하고 그릴 뿐**이다.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_PROJECT_ROOT = _HERE.parents[3]
_SCRIPTS_ROOT = _PROJECT_ROOT / "scripts"
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from common.emit import emit  # noqa: E402


# =========================================================================
# coverage — 덤프의 스타일 항목을 전부 나열한다
# =========================================================================

# 시안에서 화면으로 옮겨져야 하는 것들. 덤프마다 키 이름이 조금씩 다르므로
# 별칭을 함께 본다 — 못 찾으면 "항목 0개"로 조용히 통과해 버린다.
_STYLE_KEYS = {
    "fills": ("fills", "fill", "background", "backgroundColor"),
    "strokes": ("strokes", "stroke", "border", "borders"),
    "effects": ("effects", "effect", "boxShadow", "shadow", "shadows"),
    "layout": ("layout", "layoutMode", "padding", "itemSpacing", "cornerRadius",
               "borderRadius", "gap"),
    "text": ("style", "textStyle", "fontSize", "fontWeight", "fontFamily",
             "lineHeight", "letterSpacing"),
}


# 그림자는 **한 문자열 안에 여러 줄**이 쉼표로 이어져 온다. 실측:
#   boxShadow: '0px 4px 20px 0px rgba(...), inset 0px 8px 24px -16px rgba(...),
#               inset 0px -24px 32px 0px rgba(...), inset 0px 0px 10px 2px rgba(...)'
# 이걸 한 줄로 세면 네 줄 중 세 줄이 빠져도 드러나지 않는다 — 실제 사고가 그랬다.
# rgba(...) 안의 쉼표는 건드리면 안 되므로 괄호 깊이를 센다.
def _split_shadows(css: str) -> list[str]:
    out, depth, cur = [], 0, ""
    for ch in css:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            if cur.strip():
                out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


# 종류를 이름 붙여 준다. **자꾸 빠지는 것이 어떤 종류인지** 알아야 눈에 띈다.
_NO_OFFSET = re.compile(r"^(inset\s+)?0(px)?\s+0(px)?\s")


def _effect_kind(prop: str, value: str) -> str:
    v = str(value).strip()
    if prop == "backdropFilter":
        return "배경 블러"
    if prop == "filter":
        return "블러" if "blur" in v else "필터"
    if v.startswith("inset"):
        return "안쪽 그림자"
    if _NO_OFFSET.match(v):
        # 치우침 없이 번지기만 하는 것 — 흔히 "글로우"라 부른다
        return "글로우"
    return "그림자"


def _describe(value) -> str:
    """항목 하나를 사람이 읽을 한 줄로. 값을 줄이되 **버리지 않는다.**"""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)) or value is None:
        return str(value)
    if isinstance(value, list):
        return " / ".join(_describe(v) for v in value) or "[]"
    if isinstance(value, dict):
        parts = []
        for k, v in value.items():
            if isinstance(v, (dict, list)):
                parts.append(f"{k}={_describe(v)}")
            else:
                parts.append(f"{k}={v}")
        return "{" + ", ".join(parts) + "}"
    return str(value)


# 에셋은 덤프 안에 **그림이 아니라 노드로만** 들어 있다. 값을 아무리 잘 옮겨도
# 이 노드들을 따로 내려받지 않으면 화면에 아이콘이 없다.
_ASSET_TYPES = {"IMAGE-SVG", "IMAGE", "VECTOR"}

# download_figma_images 의 fileName 은 ^[a-zA-Z0-9_.-]+\.(png|svg)$ 만 받는다.
# 실측: 어느 실제 파일의 에셋 609개 중 281개(46%)가 한글·공백·'/' 를 담은 이름이라
# 레이어 이름을 그대로 넘기면 거부된다. 게다가 592개가 45종 이름에 몰려 있어
# 이름으로 저장하면 **서로 덮어쓴다**. 그래서 여기서 안전한 이름을 만들어 준다.
def _slug(name, node_id: str) -> tuple[str, bool]:
    raw = re.sub(r"[^A-Za-z0-9]+", "-", str(name or "")).strip("-").lower()
    if raw:
        return raw[:48], False
    # 한글처럼 ASCII 가 하나도 안 남는 이름 — 뜻을 잃었다는 표시를 함께 준다
    return "asset-" + re.sub(r"[^0-9]+", "-", str(node_id)).strip("-"), True


def _image_ref(node: dict, styles: dict):
    """사진 칠을 찾아 내려받기 인자를 돌려준다.

    **칠도 참조로 온다.** 노드에는 `fills: fill_JJ816G` 만 있고 imageRef 는
    globalVars 쪽 값 안에 있다 — 참조를 안 풀면 사진 에셋을 통째로 놓친다.
    덤프가 `imageDownloadArguments` 로 필요한 인자까지 알려주므로 그대로 쓴다.
    """
    for key in ("fills", "fill", "background"):
        blob = node.get(key)
        if isinstance(blob, str):
            blob = styles.get(blob)
        if blob is None:
            continue
        for entry in (blob if isinstance(blob, list) else [blob]):
            if not isinstance(entry, dict) or not entry.get("imageRef"):
                continue
            args = entry.get("imageDownloadArguments") or {}
            return {
                "imageRef": entry["imageRef"],
                "needsCropping": bool(args.get("needsCropping")),
                "requiresImageDimensions": bool(args.get("requiresImageDimensions")),
                "cropTransform": entry.get("imageTransform") or args.get("cropTransform"),
            }
    return None


def _is_hidden(node: dict) -> bool:
    """화면에 안 그려지는 노드인가.

    덤프에는 **꺼 둔 레이어도 섞여 나온다.** 그것까지 세면 "분류할 항목 40개"
    같은 숫자가 나와 사람이 보다 지쳐 포기한다 — 그러면 세는 의미가 없다.
    """
    if node.get("visible") is False:
        return True
    try:
        if float(node.get("opacity", 1)) == 0:
            return True
    except (TypeError, ValueError):
        pass
    # 도구마다 이름이 다르다. 모르는 표기는 보이는 것으로 친다 —
    # 잘못 걸러 빠뜨리는 것보다 한 줄 더 세는 편이 낫다.
    return node.get("isVisible") is False or node.get("hidden") is True


def _walk(node, path, out, want_id=None, inside=False, hidden=None, elements=None,
          styles=None, assets=None):
    """덤프를 훑어 스타일 항목을 모은다.

    덤프 모양이 도구·버전마다 달라서 키 이름을 고정하지 않고 재귀로 찾는다.
    구조를 단정하면 다음 버전에서 **조용히 0건**이 된다.
    """
    if hidden is None:
        hidden = []
    if elements is None:
        elements = []
    if styles is None:
        styles = {}
    if assets is None:
        assets = []
    if isinstance(node, list):
        for i, child in enumerate(node):
            _walk(child, f"{path}[{i}]", out, want_id, inside, hidden, elements, styles,
                  assets)
        return
    if not isinstance(node, dict):
        return

    # 꺼 둔 레이어는 자식까지 통째로 건너뛴다. 부모가 안 보이면 자식도 안 보인다.
    if _is_hidden(node):
        hidden.append(node.get("id") or node.get("name") or "?")
        return

    node_id = node.get("id")
    node_name = node.get("name")
    here = inside or want_id is None or (node_id == want_id)

    if here and (node_id or node_name):
        label = node_id or node_name
        # 스타일만 세면 **요소가 통째로 빠진 것**은 안 보인다. 시안에 있는데
        # 화면에 아예 없는 경우가 실제로 있었다 — 그건 스타일 문제가 아니다.
        #
        # id 가 있는 것만 요소로 친다. 컴포넌트 속성 선언(`Dark Mode` 같은 VARIANT)도
        # name 을 갖고 있어서, name 만 보면 화면 요소가 아닌 것이 목록에 섞인다.
        node_type = node.get("type") or node.get("nodeType")
        if node_id and node_type != "VARIANT":
            elements.append({"ref": node_id, "name": node_name, "type": node_type})
            if node_type in _ASSET_TYPES:
                # 덤프에는 아이콘의 **모양이 없다**. 크기조차 layout 참조 뒤에 있다.
                # 그래서 신원 근거를 모아 두고, 묶을 때 증거가 있는 것만 묶는다.
                layout = node.get("layout")
                box = styles.get(layout) if isinstance(layout, str) else layout
                dims = (box or {}).get("dimensions") if isinstance(box, dict) else None
                # 효과가 붙은 에셋은 **받은 그림이 더 크게 온다** — 번짐이
                # 그림 안에 필터로 박혀 오기 때문이다. 실측: layout 36x34 인
                # 글로우 도형이 96x94 로 왔다. 미리 알려주지 않으면 레이아웃
                # 크기로 넣어 도형을 쪼그라뜨리거나 효과를 코드로 또 넣는다.
                fx = node.get("effects")
                fx = styles.get(fx) if isinstance(fx, str) else fx
                assets.append({
                    "node_id": node_id, "name": node_name, "type": node_type,
                    "width": (dims or {}).get("width"),
                    "height": (dims or {}).get("height"),
                    "baked_effect": _describe(fx) if fx else None,
                    "image": _image_ref(node, styles),
                    "component_id": node.get("componentId"),
                    # 같은 그림이라는 **증거**. 모양 정보가 없으니 이게 최선이다.
                    "_print": json.dumps(
                        {k: v for k, v in node.items() if k not in ("id", "children")},
                        sort_keys=True, ensure_ascii=False),
                })
        for kind, aliases in _STYLE_KEYS.items():
            for key in aliases:
                if key not in node:
                    continue
                value = node[key]
                # 참조면 실제 값으로 바꾼다. 안 바꾸면 "fill_B16QZY" 가 값이 되어
                # 분류할 수 없고, 여러 줄짜리 효과가 한 줄로 뭉개진다.
                if isinstance(value, str) and value in styles:
                    value = styles[value]
                if value in (None, [], {}, ""):
                    continue
                # 배열은 **원소마다 한 줄**로 쪼갠다. 통째로 한 줄이면
                # 네 줄짜리 effects 에서 한 줄이 빠져도 티가 안 난다.
                if isinstance(value, list):
                    for i, item in enumerate(value):
                        out.append({"ref": f"{label}/{key}[{i}]", "kind": kind,
                                    "name": node_name, "value": _describe(item)})
                elif isinstance(value, dict) and kind == "effects":
                    # 효과는 키 하나가 곧 하나의 연출이고(그림자·블러…),
                    # 그 안에서 **또 쉼표로 여러 줄**이 이어진다. 둘 다 쪼갠다.
                    for k2, v2 in value.items():
                        lines = _split_shadows(str(v2)) if isinstance(v2, str) else [v2]
                        many = len(lines) > 1
                        for n2, line in enumerate(lines):
                            ref = f"{label}/{key}.{k2}" + (f"[{n2}]" if many else "")
                            out.append({"ref": ref, "kind": kind, "name": node_name,
                                        "effect": _effect_kind(k2, line),
                                        "value": _describe(line)})
                else:
                    out.append({"ref": f"{label}/{key}", "kind": kind,
                                "name": node_name, "value": _describe(value)})

    for k, v in node.items():
        if isinstance(v, (dict, list)) and k not in ("fills", "strokes", "effects"):
            _walk(v, f"{path}.{k}", out, want_id, here, hidden, elements, styles, assets)


def _load_dump(path: Path):
    """덤프를 읽는다. **실제 MCP 는 YAML 을 돌려준다** — JSON 만 받으면 못 쓴다.

    도구·버전에 따라 JSON 일 수도 있으므로 JSON 을 먼저 시도하고 YAML 로 내려간다.
    """
    text = path.read_text(encoding="utf-8")
    try:
        return json.loads(text), None
    except json.JSONDecodeError:
        pass
    try:
        import yaml
    except ImportError:
        return None, ("yaml_missing",
                      "덤프가 JSON 이 아닙니다. YAML 로 읽으려면 PyYAML 이 필요합니다",
                      "python3 -m pip install pyyaml")
    try:
        return yaml.safe_load(text), None
    except yaml.YAMLError as e:
        return None, ("dump_unreadable", str(e), None)


def _style_table(data) -> dict:
    """`globalVars.styles` — 노드는 스타일을 **참조로만** 갖는다.

        nodes:  {fills: fill_B16QZY}          ← 이것만 보면 "fill_B16QZY" 가 값이 된다
        globalVars.styles: {fill_B16QZY: ['#737373']}   ← 진짜 값은 여기

    해소하지 않으면 효과 네 줄이 **참조 문자열 한 줄**로 세어져, 한 줄이 빠져도
    드러나지 않는다 — 이 도구가 막으려던 바로 그 일이다.
    """
    if not isinstance(data, dict):
        return {}
    gv = data.get("globalVars")
    if isinstance(gv, dict) and isinstance(gv.get("styles"), dict):
        return gv["styles"]
    return gv if isinstance(gv, dict) else {}


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


# =========================================================================
# corners — 속성으로 대조한다 (#626)
#
# 픽셀 퍼센트는 **어디가** 다른지만 말하고 **무엇이 어떻게** 다른지를 말하지 않는다.
# 실제 사고: 바텀시트 상단 모서리가 각져 있었는데, 도구는 그 자리를
# `476~519 / 0~785 / 평균차 77` 로 리포트했다. 전체 5.5% 다름에 덩어리 22개 —
# 진짜 결함이 잡음에 묻혔다. 사람은 22줄짜리 좌표표를 읽지 않는다.
#
# 속성은 단정적이다: `좌상 r=16 인데 렌더가 각졌다`.
# =========================================================================

# 꼭짓점에서 대각선으로 t 만큼 들어간 점 (t,t) 는, 호 중심 (r,r) 까지의 거리가
# (r-t)·√2 다. 이게 r 보다 커야 **도형 바깥**이다:
#     (r-t)·√2 > r  ⟺  t < r(1 - 1/√2) = 0.2929r
# 즉 0.3r 은 임계값을 넘어 **안쪽**이다 — 그 자리를 찍으면 둥근 모서리에서도
# 면 색이 나와 언제나 "각졌다"가 된다. 여유를 두고 0.15r 을 쓴다.
_CORNER_PROBE = 0.15
_CORNER_LIMIT = 1.0 - 1.0 / (2 ** 0.5)      # 0.2929… — 이 값 이상은 의미가 없다

_CORNER_NAMES = ("좌상", "우상", "우하", "좌하")


def _parse_radius(value) -> list[float]:
    """borderRadius 를 네 귀 값으로 편다.

    실측: `20px` 처럼 하나로 오기도, `0px 0px 0px 0px` 처럼 넷으로 오기도 한다.
    """
    if value is None:
        return [0.0] * 4
    if isinstance(value, (int, float)):
        return [float(value)] * 4
    nums = [float(m) for m in re.findall(r"-?\d+(?:\.\d+)?", str(value))]
    if not nums:
        return [0.0] * 4
    if len(nums) == 1:
        return nums * 4
    if len(nums) == 2:
        return [nums[0], nums[1], nums[0], nums[1]]
    return (nums + nums[-1:] * 4)[:4]


def _rects(node, styles: dict, want_id, ox=0.0, oy=0.0, inside=False, out=None,
           skipped=None):
    """절대 좌표를 가진 사각형을 모은다.

    위치는 layout 참조 안의 `locationRelativeToParent` 에 있다. 자동배치
    (auto-layout) 자식은 그 값이 없어 흐름을 계산해야 하는데, 추측으로 좌표를
    지어내면 **엉뚱한 자리를 검사하고 결함이라 우긴다.** 그래서 모르면
    건너뛰고 **몇 개를 건너뛰었는지 밝힌다.**
    """
    if out is None:
        out, skipped = [], []
    if isinstance(node, list):
        for c in node:
            _rects(c, styles, want_id, ox, oy, inside, out, skipped)
        return out, skipped
    if not isinstance(node, dict):
        return out, skipped
    if _is_hidden(node):
        return out, skipped

    node_id = node.get("id")
    here = inside or want_id is None or node_id == want_id

    layout = node.get("layout")
    box = styles.get(layout) if isinstance(layout, str) else layout
    box = box if isinstance(box, dict) else {}
    loc = box.get("locationRelativeToParent")
    dims = box.get("dimensions") or {}
    w, h = dims.get("width"), dims.get("height")

    x, y, known = ox, oy, True
    if here and node_id:
        if isinstance(loc, dict):
            x, y = ox + float(loc.get("x", 0)), oy + float(loc.get("y", 0))
        elif want_id is not None and node_id == want_id:
            x, y = 0.0, 0.0          # 대조 기준 노드는 렌더의 원점이다
        else:
            known = False

        radii = _parse_radius(node.get("borderRadius"))
        fills = node.get("fills")
        fills = styles.get(fills) if isinstance(fills, str) else fills
        fx = node.get("effects")
        fx = styles.get(fx) if isinstance(fx, str) else fx
        interesting = any(r > 0 for r in radii) or fills is not None or fx is not None
        if interesting and w and h:
            (out if known else skipped).append({
                "ref": node_id, "name": node.get("name"), "type": node.get("type"),
                "x": x, "y": y, "width": float(w), "height": float(h),
                "radii": radii, "fills": fills, "effects": fx,
            })

    for k, v in node.items():
        if isinstance(v, (dict, list)) and k not in ("fills", "strokes", "effects"):
            _rects(v, styles, want_id, x if known else ox, y if known else oy,
                   here, out, skipped)
    return out, skipped


_HEX = re.compile(r"^#([0-9a-fA-F]{6})$")
_RGBA = re.compile(r"rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)(?:[,\s/]+([\d.]+))?\s*\)")


def _as_color(entry):
    """칠 한 겹을 (rgb, alpha) 로 읽는다. 색이 아니면 None."""
    if not isinstance(entry, str):
        return None
    m = _HEX.match(entry.strip())
    if m:
        h = m.group(1)
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)), 1.0
    m = _RGBA.search(entry)
    if m:
        a = float(m.group(4)) if m.group(4) is not None else 1.0
        return (int(float(m.group(1))), int(float(m.group(2))),
                int(float(m.group(3)))), a
    return None


def _fill_kind(value):
    """칠을 (종류, 값) 으로 정리한다.

    실측 분포: 단색 hex 72 · rgba 14 · 그라디언트 28 · 이미지 2.
    **맨 위 겹이 화면에 보이는 것**이라 그것을 기준으로 삼는다.
    """
    layers = value if isinstance(value, list) else [value]
    for entry in layers:                      # 목록의 앞이 위 겹이다
        if isinstance(entry, dict):
            if entry.get("imageRef"):
                return "image", entry
            if "gradient" in str(entry):
                return "gradient", entry
            continue
        c = _as_color(entry)
        if c:
            return ("translucent" if c[1] < 1.0 else "solid"), c
    return "unknown", None


def _shadow_offsets(effects):
    """바깥 그림자들의 (dx, dy, blur). inset 은 뺀다 — 밖에서 안 보인다."""
    out = []
    if not isinstance(effects, dict):
        return out
    for line in _split_shadows(str(effects.get("boxShadow") or "")):
        if not line or line.startswith("inset"):
            continue
        nums = re.findall(r"(-?[\d.]+)px", line)
        if len(nums) >= 3:
            out.append((float(nums[0]), float(nums[1]), float(nums[2])))
    return out


def _node_width(node, styles: dict, want_id):
    """기준 노드의 논리 폭. 배율을 여기서 뽑는다.

    ⚠️ 모서리를 가진 사각형들에서 최댓값을 쓰면 안 된다 — 기준 프레임은 대개
    둥근 모서리가 없어 그 목록에 없고, 그러면 배율이 통째로 어긋나 **멀쩡한
    모서리를 각졌다고 우긴다.** (실측으로 1.0 대신 1.25 가 나왔다.)
    """
    if isinstance(node, list):
        for c in node:
            w = _node_width(c, styles, want_id)
            if w:
                return w
        return None
    if not isinstance(node, dict):
        return None
    if want_id is None or node.get("id") == want_id:
        layout = node.get("layout")
        box = styles.get(layout) if isinstance(layout, str) else layout
        w = ((box or {}).get("dimensions") or {}).get("width") if isinstance(box, dict) else None
        if w:
            return float(w)
        if want_id is not None:
            return None
    for k, v in node.items():
        if isinstance(v, (dict, list)) and k not in ("fills", "strokes", "effects"):
            w = _node_width(v, styles, want_id)
            if w:
                return w
    return None


def _probe_corners(img, rect: dict, scale: float, tol: int) -> list[dict]:
    """모서리 네 곳을 찍어 각졌는지 본다.

    바깥이어야 할 자리가 **안쪽과 같은 색**이면 각진 것이다. 칠 값을 따로 알
    필요가 없다 — 같은 사각형 안쪽을 기준으로 삼는다.
    """
    W, H = img.size
    findings = []
    x0, y0 = rect["x"] * scale, rect["y"] * scale
    w, h = rect["width"] * scale, rect["height"] * scale

    def at(px, py):
        px, py = int(round(px)), int(round(py))
        if not (0 <= px < W and 0 <= py < H):
            return None
        return img.getpixel((px, py))[:3]

    for i, r_logical in enumerate(rect["radii"]):
        r = r_logical * scale
        if r <= 1:
            continue
        t = r * _CORNER_PROBE
        # i: 0 좌상 · 1 우상 · 2 우하 · 3 좌하
        vx = x0 if i in (0, 3) else x0 + w
        vy = y0 if i in (0, 1) else y0 + h
        sx = 1 if i in (0, 3) else -1
        sy = 1 if i in (0, 1) else -1
        outside = at(vx + sx * t, vy + sy * t)          # 둥글면 배경이어야 한다
        inside = at(vx + sx * r * 1.6, vy + sy * r * 1.6)   # 확실히 면 안쪽
        if outside is None or inside is None:
            continue
        diff = max(abs(a - b) for a, b in zip(outside, inside))
        if diff <= tol:
            findings.append({
                "corner": _CORNER_NAMES[i], "radius": r_logical,
                "probe": [round(vx + sx * t, 1), round(vy + sy * t, 1)],
                "outside_rgb": list(outside), "inside_rgb": list(inside),
                "verdict": "각짐",
                "says": (f"{rect['name'] or rect['ref']} "
                         f"{rect['width']:.0f}x{rect['height']:.0f} "
                         f"@{rect['x']:.0f},{rect['y']:.0f} "
                         f"{_CORNER_NAMES[i]} r={r_logical:g} → 렌더가 각졌다"),
            })
    return findings


def _label(rect) -> str:
    return (f"{rect['name'] or rect['ref']} {rect['width']:.0f}x{rect['height']:.0f} "
            f"@{rect['x']:.0f},{rect['y']:.0f}")


def _check_fills(sample, rect, tol) -> list[dict]:
    """칠이 시안대로 칠해졌는가.

    잡는 것: 색 자체가 다름 · **투명도가 빠짐**(hex 는 맞는데 그대로 불투명) ·
    **그라디언트를 단색으로 깔음**. 셋 다 화면에서는 "비슷해" 보인다.
    """
    kind, value = _fill_kind(rect.get("fills"))
    if kind in ("unknown", "image"):
        return []                       # 사진은 색으로 판정할 수 없다
    w, h = rect["width"], rect["height"]
    mid = sample(rect["x"] + w / 2, rect["y"] + h / 2)
    if mid is None:
        return []
    out = []

    if kind in ("solid", "translucent"):
        want, alpha = value
        gap = max(abs(a - b) for a, b in zip(mid, want))
        if kind == "solid" and gap > tol:
            out.append({"check": "fills", "severity": "high", "ref": rect["ref"],
                        "says": (f"{_label(rect)} 칠이 다르다 — 시안 "
                                 f"rgb{want}, 렌더 rgb{tuple(mid)}")})
        elif kind == "translucent" and gap <= tol:
            # 반투명인데 원색 그대로 = 투명도를 안 준 것이다
            out.append({"check": "fills", "severity": "high", "ref": rect["ref"],
                        "says": (f"{_label(rect)} 투명도가 빠졌다 — 시안 "
                                 f"alpha={alpha:g} 인데 렌더가 원색 rgb{want} 그대로다")})
    elif kind == "gradient":
        # 축을 몰라도 된다 — 세로·가로 양쪽 끝을 재서 **어느 쪽도 안 변하면** 단색이다
        pad = 0.12
        pts = [sample(rect["x"] + w / 2, rect["y"] + h * pad),
               sample(rect["x"] + w / 2, rect["y"] + h * (1 - pad)),
               sample(rect["x"] + w * pad, rect["y"] + h / 2),
               sample(rect["x"] + w * (1 - pad), rect["y"] + h / 2)]
        pts = [q for q in pts if q is not None]
        if len(pts) >= 2:
            spread = max(max(abs(a - b) for a, b in zip(p1, p2))
                         for p1 in pts for p2 in pts)
            if spread <= tol:
                out.append({"check": "fills", "severity": "high", "ref": rect["ref"],
                            "says": (f"{_label(rect)} 그라디언트가 단색으로 깔렸다 — "
                                     f"면 전체가 rgb{tuple(pts[0])} 한 색이다")})
    return out


def _check_shadows(sample, rect, tol) -> list[dict]:
    """바깥 그림자가 실제로 그려졌는가.

    시안이 치우친 그림자를 말하면, 그 방향 바깥이 **먼 배경과 달라야** 한다.
    같으면 그림자가 통째로 빠진 것이다 — 작고 은은해서 눈으로는 안 보인다.
    """
    offsets = _shadow_offsets(rect.get("effects"))
    out = []
    for dx, dy, blur in offsets:
        reach = max(abs(dx), abs(dy), blur / 2.0)
        if reach < 2:
            continue                     # 너무 얕아 픽셀로 가릴 수 없다
        w, h = rect["width"], rect["height"]
        cx, cy = rect["x"] + w / 2, rect["y"] + h / 2
        # 그림자가 지는 쪽 바로 바깥
        if abs(dy) >= abs(dx):
            near = sample(cx, rect["y"] + h + max(dy, 1) if dy >= 0 else rect["y"] + min(dy, -1))
            far = sample(cx, rect["y"] + h + reach * 6 if dy >= 0 else rect["y"] - reach * 6)
        else:
            near = sample(rect["x"] + w + max(dx, 1) if dx >= 0 else rect["x"] + min(dx, -1), cy)
            far = sample(rect["x"] + w + reach * 6 if dx >= 0 else rect["x"] - reach * 6, cy)
        if near is None or far is None:
            continue
        if max(abs(a - b) for a, b in zip(near, far)) <= tol:
            out.append({"check": "shadows", "severity": "medium", "ref": rect["ref"],
                        "says": (f"{_label(rect)} 그림자가 안 보인다 — 시안은 "
                                 f"{dx:g},{dy:g} blur {blur:g} 인데 가장자리 바깥이 "
                                 f"먼 배경과 같다")})
    return out


_SEVERITY_ORDER = {"none": 0, "low": 1, "medium": 2, "high": 3}
_ALL_CHECKS = ("corners", "fills", "shadows")


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

    styles = _style_table(data)
    rects, skipped = _rects(data, styles, args.node)
    if not rects and not skipped:
        return emit({"ok": True, "checked": 0, "findings": [],
                     "summary": "둥근 모서리를 가진 사각형이 없습니다",
                     "next": "borderRadius 가 있는 노드를 포함하는지 --node 를 확인하세요"})

    img = Image.open(render).convert("RGB")
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

    checks = [c.strip() for c in args.check.split(",") if c.strip()] if args.check \
        else list(_ALL_CHECKS)
    bad = [c for c in checks if c not in _ALL_CHECKS]
    if bad:
        return emit({"ok": False, "code": "unknown_check",
                     "error": f"모르는 검사: {bad}",
                     "hint": f"쓸 수 있는 것: {', '.join(_ALL_CHECKS)}"})

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


# =========================================================================
# get-output-path — 산출물 자리를 도구가 정한다
#
# 어디에 둘지 정해 주지 않으면 매번 다른 곳에 쌓인다. 실제로 다른 스킬에서
# 8MB 스크린샷이 엉뚱한 폴더에 추적되는 채로 쌓인 적이 있다 (#611).
# =========================================================================

# 실제 에셋이 갈 곳 후보. 프로젝트 마커로 프레임워크를 짐작한다.
# **고르는 것은 agent 다** — 레포마다 관례가 달라 여기서 단정하지 않는다.
_ASSET_HINTS = (
    ("pubspec.yaml", ("assets/images", "assets/icons", "assets")),
    ("app.json", ("assets/images", "assets")),
    ("package.json", ("src/assets", "public/assets", "public", "assets")),
)


def _asset_dirs(root: Path) -> list[str]:
    """이 프로젝트에서 에셋이 갈 만한 곳. 실재하는 것을 앞에 둔다."""
    out: list[str] = []
    for marker, candidates in _ASSET_HINTS:
        if not (root / marker).is_file():
            continue
        for c in candidates:
            if c not in out:
                out.append(c)
    exists = [c for c in out if (root / c).is_dir()]
    return exists + [c for c in out if c not in exists]


def cmd_output_path(args) -> int:
    """이번 대조의 산출물 자리를 만들고 알려준다.

    경로 규칙은 common/paths.py 가 단일 소유한다 (#525) — 여기서 재구현하지
    않고 파일명만 빌려 폴더 이름으로 쓴다.
    """
    try:
        from common.paths import resolve_output_path
    except ImportError:
        return emit({"ok": False, "code": "common_not_found",
                     "error": "scripts/common/paths.py 를 찾지 못했습니다",
                     "hint": "projectops 설치가 온전한지 확인하세요"})

    r = resolve_output_path("figma-verify", args.title)
    if r.get("ok") is False:
        return emit(r)

    md = Path(r["path"])          # <우산>/figma-verify/{날짜}_{번호}_{제목}.md
    run_dir = md.parent / md.stem
    subs = {name: run_dir / name for name in ("dump", "design", "render", "diff")}
    try:
        for d in subs.values():
            d.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return emit({"ok": False, "code": "mkdir_failed", "error": str(e)})

    root = Path(args.root).resolve()
    candidates = _asset_dirs(root)
    return emit({
        "run": md.stem,
        "run_dir": str(run_dir),
        "dump": str(subs["dump"]),
        "design": str(subs["design"]),
        "render": str(subs["render"]),
        "diff": str(subs["diff"]),
        "gitignore": r.get("gitignore"),   # 공통(common/paths)이 심는다
        "asset_dir_candidates": candidates,
        "output_root": r.get("output_root"),
        "summary": (f"대조 자리 {run_dir} (추적 안 함)"
                    + (f" · 에셋은 {candidates[0]} 후보" if candidates else "")),
        "next": ("**두 곳을 구분하세요.** 덤프·시안 export·앱 렌더·차이 그림은 위 "
                 "run_dir 안에 둡니다 — 증거라서 추적하지 않습니다. "
                 "**실제 에셋(앱이 쓸 아이콘·이미지)은 여기 두면 안 됩니다.** "
                 "asset_dir_candidates 중 이 프로젝트의 관례에 맞는 곳을 골라 "
                 "download_figma_images 의 localPath 로 주세요 — 앱이 쓰는 파일이라 "
                 "커밋되어야 합니다. 후보가 비었으면 사용자에게 물어보세요"),
    })


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


# =========================================================================
# diff — 그림으로 맞댄다
# =========================================================================

def _require_imaging():
    try:
        import numpy  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError:
        return emit({
            "ok": False, "code": "imaging_missing",
            "error": "Pillow 와 numpy 가 필요합니다",
            "hint": "python3 -m pip install pillow numpy",
        })
    return None


def _parse_bg(text, design_img):
    """합성 배경색을 정한다.

    앱 렌더는 바깥 발광이 반투명으로 남고 시안 export 는 배경이 합성된 채로 온다.
    같은 배경 위에 올려놓지 않으면 **발광 전체가 '다름'으로 잡혀** diff 가 의미를
    잃는다. 색을 고정값으로 박으면 남의 프로젝트에서 틀리므로 시안에서 읽는다.
    """
    if text and text != "auto":
        v = text.lstrip("#")
        if len(v) != 6:
            raise ValueError(f"--bg 는 RRGGBB 형식이어야 합니다: {text}")
        return tuple(int(v[i:i + 2], 16) for i in (0, 2, 4)), f"#{v.upper()}"
    corner = design_img.getpixel((0, 0))
    if len(corner) == 4 and corner[3] == 255:
        return corner[:3], "시안 좌상단 픽셀"
    return (255, 255, 255), "흰색 (시안 모서리가 투명)"


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


def cmd_diff(args) -> int:
    missing = _require_imaging()
    if missing is not None:
        return missing
    import numpy as np
    from PIL import Image

    for label, p in (("render", args.render), ("design", args.design)):
        if not Path(p).is_file():
            return emit({"ok": False, "code": "image_not_found",
                         "error": f"{label} 이미지가 없습니다: {p}"})

    design_img = Image.open(args.design).convert("RGBA")
    try:
        bg, bg_src = _parse_bg(args.bg, design_img)
    except ValueError as e:
        return emit({"ok": False, "code": "bad_bg", "error": str(e)})

    def flatten(img):
        base = Image.new("RGBA", img.size, (*bg, 255))
        return np.asarray(Image.alpha_composite(base, img).convert("RGB"), dtype=np.int16)

    design = flatten(design_img)
    render_img = Image.open(args.render).convert("RGBA")
    if render_img.size != design_img.size:
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
        "summary": (f"다른 픽셀 {pct:.2f}% · 덩어리 {len(found)}개 "
                    f"(최대 채널차 {int(delta.max())})"),
        "next": (
            (f"덩어리가 {len(found)}개지만 렌더를 "
             f"({shift['dx']:+d}, {shift['dy']:+d}) 옮기면 "
             f"{shift['before']}% → {shift['after']}% 로 떨어집니다. "
             "**낱낱이 어긋난 것이 아니라 통째로 밀린 것**입니다 — 안의 요소가 아니라 "
             "그것을 담은 컨테이너(높이·여백·안전영역)를 먼저 보세요."
             if (shift or {}).get("looks_shifted") else
             "퍼센트가 아니라 **덩어리 위치**를 보세요. 글자 자리면 래스터라이즈 "
             "차이라 대개 무해하고, 도형·여백 자리면 실제로 틀린 것입니다. "
             "그림자·발광·1px 테두리는 전체 화면에서 사라지므로 component 로 다시 봅니다")),
    })


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="figma_verify_cli",
                                description="시안과 구현 화면을 대조한다")
    sub = p.add_subparsers(dest="command")

    c = sub.add_parser("coverage", help="덤프의 스타일 항목을 빠짐없이 나열한다")
    c.add_argument("--dump", required=True, help="Figma 덤프를 저장한 JSON 파일")
    c.add_argument("--node", default=None,
                   help="이 노드 아래만 본다 (생략하면 덤프 전체)")
    c.set_defaults(func=cmd_coverage)

    o = sub.add_parser("get-output-path", help="이번 대조의 산출물 자리를 만든다")
    o.add_argument("--title", required=True, help="이번 대조를 부를 이름 (화면 이름 등)")
    o.add_argument("--root", default=".", help="프로젝트 루트 (기본 현재 위치)")
    o.set_defaults(func=cmd_output_path)

    a_ = sub.add_parser("assets", help="내려받아야 할 에셋을 묶어 목록으로 낸다")
    a_.add_argument("--dump", required=True, help="Figma MCP 덤프 파일")
    a_.add_argument("--node", help="이 노드 아래만 (없으면 전체)")
    a_.set_defaults(func=cmd_assets)

    c_ = sub.add_parser("conform", help="시안 값대로 그려졌는지 속성으로 대조한다")
    c_.add_argument("--dump", required=True, help="Figma MCP 덤프 파일")
    c_.add_argument("--render", required=True, help="앱 렌더 png")
    c_.add_argument("--node", help="이 노드를 원점으로 (보통 화면 프레임)")
    c_.add_argument("--check", default="",
                    help=f"쉼표로 고른다 (기본 전부): {','.join(_ALL_CHECKS)}")
    c_.add_argument("--fail-on", dest="fail_on", default="none",
                    choices=["none", "low", "medium", "high"],
                    help="이 심각도 이상이면 종료코드 1 — CI 게이트용")
    c_.add_argument("--scale", type=float, default=0,
                    help="렌더 배율 (0이면 렌더 폭 ÷ 기준 노드 폭으로 추정)")
    c_.add_argument("--tolerance", type=int, default=12,
                    help="같은 색으로 볼 채널 차 (안티에일리어싱 여유)")
    c_.set_defaults(func=cmd_conform)

    d = sub.add_parser("diff", help="시안 export 와 앱 렌더를 픽셀로 맞댄다")
    d.add_argument("--render", required=True, help="앱이 그린 PNG")
    d.add_argument("--design", required=True, help="Figma export PNG")
    d.add_argument("--out", default=None, help="차이를 칠한 PNG 저장 경로")
    d.add_argument("--bg", default="auto",
                   help="합성 배경색 RRGGBB. 기본 auto = 시안 모서리에서 읽는다")
    d.add_argument("--threshold", type=int, default=24,
                   help="채널당 이 값을 넘어야 '다르다'로 본다 (기본 24)")
    d.add_argument("--mask-top", type=int, default=0,
                   help="위에서 이만큼 제외 (상태바 — 앱이 안 그린다)")
    d.add_argument("--mask-bottom", type=int, default=0,
                   help="아래에서 이만큼 제외 (홈 인디케이터)")
    d.add_argument("--min-area", type=int, default=200,
                   help="이 넓이 미만 덩어리는 보고하지 않는다")
    d.add_argument("--probe-shift", type=int, default=40,
                   help="렌더를 ±이 픽셀만큼 옮겨 보며 '통째로 밀림'인지 가린다 (0=끄기)")
    d.set_defaults(func=cmd_diff)
    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help(sys.stderr)
        return 1
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
