"""Figma 덤프 읽기: 스타일 항목 나열 · 참조 해소 · 에셋 노드 수집"""
from __future__ import annotations

import json
import re
from pathlib import Path


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
