"""figma_verify_cli 테스트 (이슈 #616).

지키려는 것은 하나다 — **빠진 것이 빠진 채로 통과하지 않는다.**

실사고: 어떤 버튼의 효과 네 줄 중 안쪽 세 줄이 통째로 빠진 채 배포됐다. 전체 화면
골든을 만들어 놓고도 지나갔고, 디자이너가 배포 **후에** 발견했다. 그래서 이 스크립트가
지켜야 할 계약은

  - 배열은 **원소마다 한 줄**로 센다 (통째로 한 줄이면 한 줄 빠져도 티가 안 난다)
  - 스타일을 못 찾으면 **실패한다** (0건으로 조용히 통과하면 대조를 안 한 것과 같다)
  - 다른 곳을 **덩어리 좌표**로 짚는다 (퍼센트만으로는 어디가 틀렸는지 모른다)
"""
import re
import json
import subprocess
import sys
from pathlib import Path

import pytest

CLI = Path(__file__).resolve().parents[1] / "scripts" / "figma_verify_cli.py"


def run(*args, cwd=None):
    r = subprocess.run([sys.executable, str(CLI), *args],
                       capture_output=True, text=True, encoding="utf-8",
                       cwd=str(cwd) if cwd else None)
    return r.returncode, r.stdout, r.stderr


def out(stdout):
    return json.loads(stdout.strip())


# 실사고 그대로 — 효과가 네 줄인 버튼
_DUMP = {
    "nodes": [{
        "id": "1:100", "name": "화면", "layout": {"mode": "VERTICAL", "gap": 16},
        "children": [{
            "id": "1:200", "name": "버튼",
            "fills": [{"type": "SOLID", "color": "#8B5CF6"}],
            "cornerRadius": 34,
            "effects": [
                {"type": "DROP_SHADOW", "blur": 20},
                {"type": "INNER_SHADOW", "blur": 24},
                {"type": "INNER_SHADOW", "blur": 32},
                {"type": "INNER_SHADOW", "blur": 10},
            ],
            "style": {"fontFamily": "Pretendard", "fontWeight": 600},
        }],
    }]
}


def _dump(tmp_path, data=None):
    f = tmp_path / "dump.json"
    f.write_text(json.dumps(data if data is not None else _DUMP,
                            ensure_ascii=False), encoding="utf-8")
    return f


# ── coverage ─────────────────────────────────────────────────────────────

def test_each_array_element_is_counted_separately(tmp_path):
    """효과 네 줄이 네 줄로 세어져야 한 줄 빠진 것이 드러난다."""
    rc, o, _ = run("coverage", "--dump", str(_dump(tmp_path)))
    assert rc == 0, o
    d = out(o)
    effects = [i for i in d["items"] if i["kind"] == "effects"]
    assert len(effects) == 4, f"효과가 {len(effects)}줄로 세어졌다 — 네 줄이어야 한다"
    assert {e["ref"] for e in effects} == {
        f"1:200/effects[{i}]" for i in range(4)}
    # 값이 버려지지 않아야 분류할 수 있다
    assert any("blur=10" in e["value"] for e in effects)


def test_counts_cover_every_style_family(tmp_path):
    rc, o, _ = run("coverage", "--dump", str(_dump(tmp_path)))
    d = out(o)
    assert d["counts"]["effects"] == 4
    assert d["counts"]["fills"] == 1
    assert d["counts"]["text"] == 1
    assert d["counts"]["layout"] >= 2       # 화면의 layout + 버튼의 cornerRadius
    assert d["total"] == sum(d["counts"].values())


def test_node_filter_narrows_to_that_subtree(tmp_path):
    rc_all, o_all, _ = run("coverage", "--dump", str(_dump(tmp_path)))
    rc_one, o_one, _ = run("coverage", "--dump", str(_dump(tmp_path)), "--node", "1:200")
    assert rc_all == 0 and rc_one == 0
    assert out(o_one)["total"] < out(o_all)["total"]
    assert all(i["ref"].startswith("1:200/") for i in out(o_one)["items"])


def test_empty_dump_fails_instead_of_passing_with_zero(tmp_path):
    """0건으로 통과하면 대조를 안 한 것과 구분되지 않는다 — 실패해야 한다."""
    rc, o, _ = run("coverage", "--dump", str(_dump(tmp_path, {"nodes": [{"id": "1:1"}]})))
    assert rc == 1
    d = out(o)
    assert d["ok"] is False and d["code"] == "no_style_found"


def test_missing_dump_says_so(tmp_path):
    rc, o, _ = run("coverage", "--dump", str(tmp_path / "없음.json"))
    assert rc == 1 and out(o)["code"] == "dump_not_found"


def test_classification_is_demanded_in_next(tmp_path):
    """분류를 시키지 않으면 나열은 장식이다."""
    _, o, _ = run("coverage", "--dump", str(_dump(tmp_path)))
    nxt = out(o)["next"]
    assert "구현" in nxt and "근사" in nxt and "생략" in nxt
    assert "사유" in nxt


# ── diff ─────────────────────────────────────────────────────────────────
#
# Pillow·numpy 는 CI 에도 설치한다. 없다고 건너뛰면 "안 돌아간 것"과 구분되지 않는다
# (#591). 아래 imaging_missing 테스트만 모듈을 숨겨 그 경로를 따로 확인한다.

pillow = pytest.importorskip("PIL", reason="Pillow 는 CI 설치 목록에 있어야 한다")
pytest.importorskip("numpy")


def _pill(path, inner_ring):
    """시안/구현 한 쌍. 차이는 안쪽 테두리 유무 하나뿐이다."""
    from PIL import Image, ImageDraw, ImageFilter
    W, H, BG = 240, 100, (247, 242, 239)
    im = Image.new("RGBA", (W, H), (*BG, 255))
    d = ImageDraw.Draw(im)
    box = (10, 20, W - 10, H - 20)
    d.rounded_rectangle(box, radius=30, fill=(139, 92, 246, 255))
    if inner_ring:
        ring = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(ring).rounded_rectangle(
            (box[0] + 2, box[1] + 2, box[2] - 2, box[3] - 2),
            radius=28, outline=(255, 255, 255, 255), width=4)
        im.alpha_composite(ring.filter(ImageFilter.GaussianBlur(3)))
    im.save(path)
    return path


def test_identical_images_report_no_difference(tmp_path):
    p = _pill(tmp_path / "a.png", True)
    _, o, _ = run("diff", "--render", str(p), "--design", str(p))
    d = out(o)
    assert d["different_percent"] == 0.0
    assert d["clusters"] == []


def test_missing_inner_effect_is_found_and_located(tmp_path):
    """이번 사고와 같은 모양 — 안쪽 효과가 빠진 구현을 잡아 좌표로 짚는다."""
    design = _pill(tmp_path / "design.png", True)
    render = _pill(tmp_path / "render.png", False)
    _, o, _ = run("diff", "--render", str(render), "--design", str(design),
                  "--out", str(tmp_path / "diff.png"))
    d = out(o)
    assert d["different_percent"] > 1.0, d
    assert d["clusters"], "어디가 다른지 덩어리로 짚지 못했다"
    c = d["clusters"][0]
    assert {"x", "y", "w", "h", "mean_delta"} <= set(c)
    assert (tmp_path / "diff.png").is_file(), "차이 그림을 남기지 않았다"


def test_background_is_read_from_the_design_not_hardcoded(tmp_path):
    """배경색을 코드에 박으면 남의 프로젝트에서 틀린다 (#614 와 같은 실수)."""
    design = _pill(tmp_path / "d.png", True)
    _, o, _ = run("diff", "--render", str(design), "--design", str(design))
    assert "시안" in out(o)["background"]
    _, o2, _ = run("diff", "--render", str(design), "--design", str(design),
                   "--bg", "F7F2EF")
    assert out(o2)["background"] == "#F7F2EF"


def test_bad_background_is_rejected(tmp_path):
    design = _pill(tmp_path / "d.png", True)
    rc, o, _ = run("diff", "--render", str(design), "--design", str(design), "--bg", "xyz")
    assert rc == 1 and out(o)["code"] == "bad_bg"


def test_missing_image_says_which_one(tmp_path):
    design = _pill(tmp_path / "d.png", True)
    rc, o, _ = run("diff", "--render", str(tmp_path / "없음.png"), "--design", str(design))
    assert rc == 1
    d = out(o)
    assert d["code"] == "image_not_found" and "render" in d["error"]


def test_masking_excludes_the_bands_the_app_does_not_draw(tmp_path):
    """상태바·홈 인디케이터는 앱이 안 그려 늘 다르게 나온다 — 가려야 한다."""
    design = _pill(tmp_path / "design.png", True)
    render = _pill(tmp_path / "render.png", False)
    _, plain, _ = run("diff", "--render", str(render), "--design", str(design))
    _, masked, _ = run("diff", "--render", str(render), "--design", str(design),
                       "--mask-top", "40", "--mask-bottom", "40")
    assert out(masked)["compared_pixels"] < out(plain)["compared_pixels"]


# ── 통째로 밀린 것과 낱낱이 틀린 것을 가린다 (실사고 기반) ────────────────
#
# 시트 윗변이 35px 아래에 뜨자 안의 단계·보상·버튼이 **전부 두 겹**으로 보였다.
# 덩어리가 열 개 나왔지만 틀린 것은 하나 — 컨테이너 높이였다. 덩어리 수를 결함 수로
# 읽으면 엉뚱한 데를 고친다.

def _sheet(path, top, wrong_row=False):
    """시트 안에 줄이 여럿. top 만 다르면 '통째로 밀림'이다."""
    from PIL import Image, ImageDraw
    W, H, BG = 300, 480, (247, 242, 239)
    im = Image.new("RGBA", (W, H), (*BG, 255))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((12, top, W - 12, H - 16), radius=20, fill=(255, 255, 255, 255))
    y = top + 24
    for i in range(6):
        color = (220, 90, 90, 255) if (wrong_row and i == 0) else (156, 173, 241, 255)
        d.rounded_rectangle((32, y, W - 32, y + 28), radius=8, fill=color)
        y += 44
    im.save(path)
    return path


def test_whole_block_shift_is_named_as_such(tmp_path):
    """옮겨서 맞아떨어지면 '컨테이너가 밀렸다'고 말해야 한다."""
    design = _sheet(tmp_path / "d.png", 90)
    render = _sheet(tmp_path / "r.png", 125)          # 35px 아래
    _, o, _ = run("diff", "--render", str(render), "--design", str(design))
    d = out(o)

    assert len(d["clusters"]) > 1, "줄이 여럿 잡혀야 이 상황이다"
    sp = d["shift_probe"]
    assert sp["looks_shifted"] is True, sp
    assert sp["dy"] == -35, sp
    assert sp["after"] < sp["before"] / 2
    assert "통째로 밀린" in d["next"]
    assert "컨테이너" in d["next"]


def test_one_real_difference_is_not_called_a_shift(tmp_path):
    """한 줄만 틀린 것을 밀림으로 오판하면 엉뚱한 곳을 고치게 된다."""
    design = _sheet(tmp_path / "d.png", 90)
    render = _sheet(tmp_path / "r.png", 90, wrong_row=True)
    _, o, _ = run("diff", "--render", str(render), "--design", str(design))
    d = out(o)
    assert d["shift_probe"]["looks_shifted"] is False, d["shift_probe"]
    assert "통째로 밀린" not in d["next"]


def test_shift_probe_can_be_turned_off(tmp_path):
    design = _sheet(tmp_path / "d.png", 90)
    render = _sheet(tmp_path / "r.png", 125)
    _, o, _ = run("diff", "--render", str(render), "--design", str(design),
                  "--probe-shift", "0")
    assert out(o)["shift_probe"] is None


# ── 꺼 둔 레이어는 세지 않는다 ───────────────────────────────────────────
#
# 덤프에는 화면에 안 그려지는 레이어도 섞여 나온다. 그것까지 세면 "분류할 항목 40개"
# 가 되어 사람이 보다 지쳐 포기한다 — 그러면 세는 의미가 없다.

def test_hidden_layers_are_skipped_with_their_children(tmp_path):
    dump = {"nodes": [{"id": "1:1", "name": "화면", "layout": {"gap": 16}, "children": [
        {"id": "1:2", "name": "보임", "fills": [{"color": "#8B5CF6"}],
         "effects": [{"blur": 20}, {"blur": 10}]},
        {"id": "1:3", "name": "꺼둠", "visible": False,
         "effects": [{"blur": 1}, {"blur": 2}, {"blur": 3}]},
        {"id": "1:4", "name": "투명", "opacity": 0, "strokes": [{"color": "#0F0"}]},
    ]}]}
    _, o, _ = run("coverage", "--dump", str(_dump(tmp_path, dump)))
    d = out(o)

    assert d["total"] == 4, d["items"]          # layout 1 + fills 1 + effects 2
    assert set(d["hidden_skipped"]) == {"1:3", "1:4"}
    assert "꺼 둔 레이어 2개 제외" in d["summary"]
    # 꺼 둔 노드의 항목이 하나도 섞이지 않아야 한다
    assert not any(i["ref"].startswith(("1:3", "1:4")) for i in d["items"])


def test_visible_nodes_are_never_dropped_by_accident(tmp_path):
    """모르는 표기를 만나면 보이는 것으로 친다 — 잘못 걸러 빠뜨리는 쪽이 더 나쁘다."""
    dump = {"nodes": [{"id": "1:1", "name": "이상한 표기", "displayMode": "weird",
                       "effects": [{"blur": 5}]}]}
    _, o, _ = run("coverage", "--dump", str(_dump(tmp_path, dump)))
    d = out(o)
    assert d["total"] == 1 and d["hidden_skipped"] == []


# ── 요소가 통째로 빠진 것은 스타일만 세면 안 보인다 ──────────────────────
#
# 실사고: "시안에 있는데 화면이 없다" 가 여러 건 있었다. 그건 스타일 문제가 아니라
# 요소가 아예 없는 것이라, 스타일 항목만 나열해서는 드러나지 않는다.

def test_elements_are_listed_alongside_styles(tmp_path):
    dump = {"nodes": [{"id": "1:1", "name": "화면", "type": "FRAME",
                       "layout": {"gap": 8}, "children": [
        {"id": "1:2", "name": "버튼", "type": "COMPONENT",
         "fills": [{"color": "#111"}]},
        {"id": "1:3", "name": "보상 줄", "type": "TEXT", "style": {"fontSize": 14}},
    ]}]}
    _, o, _ = run("coverage", "--dump", str(_dump(tmp_path, dump)))
    d = out(o)

    refs = {e["ref"] for e in d["elements"]}
    assert refs == {"1:1", "1:2", "1:3"}, refs
    assert d["element_count"] == 3
    assert {e["type"] for e in d["elements"]} == {"FRAME", "COMPONENT", "TEXT"}
    assert "요소 3개" in d["summary"]
    # 두 층을 다 보라고 말해야 한다
    assert "요소" in d["next"] and "스타일" in d["next"]


def test_hidden_elements_are_not_listed_either(tmp_path):
    dump = {"nodes": [{"id": "1:1", "name": "화면", "type": "FRAME", "children": [
        {"id": "1:2", "name": "보임", "type": "TEXT", "style": {"fontSize": 14}},
        {"id": "1:3", "name": "꺼둠", "type": "TEXT", "visible": False,
         "style": {"fontSize": 99}},
    ]}]}
    _, o, _ = run("coverage", "--dump", str(_dump(tmp_path, dump)))
    d = out(o)
    assert {e["ref"] for e in d["elements"]} == {"1:1", "1:2"}
    assert d["hidden_skipped"] == ["1:3"]


# ── 실제 MCP 응답 모양 (이걸 안 보고 만들어서 크게 틀렸다) ────────────────
#
# 스킬을 만들 때 **직접 쓴 합성 JSON** 으로만 테스트해서 모든 검사를 통과했다.
# 진짜 Figma MCP 응답을 받아 보니 두 가지가 달랐다.
#
#   1. JSON 이 아니라 **YAML** 이다
#   2. 노드가 스타일을 **참조로만** 갖는다 — 실제 값은 globalVars.styles 에 따로 있다
#
#        nodes: {fills: fill_B16QZY}
#        globalVars: {styles: {fill_B16QZY: ['#737373']}}
#
# 해소하지 않으면 값이 "fill_B16QZY" 로 세어진다. 분류할 수 없고, 무엇보다
# **여러 줄짜리 효과가 참조 한 줄로 뭉개져** 한 줄이 빠져도 드러나지 않는다 —
# 이 도구가 막으려던 바로 그 일이다.

_REAL_SHAPE = """
metadata:
  name: 어떤 파일
nodes:
  - id: '1:100'
    name: 화면
    type: FRAME
    layout: layout_AAA
    fills: fill_BBB
    children:
      - id: '1:200'
        name: 버튼
        type: INSTANCE
        fills: fill_MULTI
        effects: effect_TWO
        componentProperties:
          - name: Dark Mode
            value: 'False'
            type: VARIANT
      - id: '1:300'
        name: 꺼둔 것
        type: RECTANGLE
        visible: false
        fills: fill_BBB
globalVars:
  styles:
    layout_AAA:
      mode: none
      dimensions: {width: 393, height: 852}
    fill_BBB:
      - '#F7F2EF'
    fill_MULTI:
      - '#939393'
      - 'rgba(86, 88, 92, 0.87)'
      - 'rgba(85, 85, 85, 0.9)'
    effect_TWO:
      boxShadow: 0px 2px 5px 0px rgba(0, 0, 0, 0.05)
      backdropFilter: blur(10px)
"""


def _real(tmp_path):
    p = tmp_path / "dump.yaml"
    p.write_text(_REAL_SHAPE, encoding="utf-8")
    return p


def test_yaml_dump_is_accepted(tmp_path):
    """실제 MCP 는 YAML 을 준다. JSON 만 받으면 이 도구는 못 쓴다."""
    rc, o, _ = run("coverage", "--dump", str(_real(tmp_path)))
    assert rc == 0, o
    assert out(o)["styles_resolved"] == 4


def test_style_references_are_resolved_to_real_values(tmp_path):
    """참조가 값으로 바뀌지 않으면 분류 자체를 할 수 없다."""
    _, o, _ = run("coverage", "--dump", str(_real(tmp_path)))
    d = out(o)
    leftover = [i for i in d["items"]
                if isinstance(i["value"], str)
                and i["value"].startswith(("fill_", "effect_", "layout_", "stroke_"))]
    assert leftover == [], f"참조 문자열이 값으로 남았다: {leftover}"
    assert any("#F7F2EF" in i["value"] for i in d["items"])


def test_multi_value_reference_is_split_per_entry(tmp_path):
    """채움 셋·효과 둘이 각각 한 줄로 세어져야 한 줄 빠진 것이 드러난다."""
    _, o, _ = run("coverage", "--dump", str(_real(tmp_path)))
    d = out(o)

    fills = [i for i in d["items"] if i["ref"].startswith("1:200/fills")]
    assert len(fills) == 3, fills          # 참조 해소 전이라면 1개였다
    assert {i["ref"] for i in fills} == {f"1:200/fills[{n}]" for n in range(3)}

    fx = [i for i in d["items"] if i["kind"] == "effects"]
    assert len(fx) == 2, fx                # boxShadow · backdropFilter 각각
    assert {i["ref"] for i in fx} == {"1:200/effects.boxShadow",
                                      "1:200/effects.backdropFilter"}


def test_component_property_declarations_are_not_elements(tmp_path):
    """`Dark Mode` 같은 VARIANT 는 컴포넌트 속성이지 화면 요소가 아니다."""
    _, o, _ = run("coverage", "--dump", str(_real(tmp_path)))
    d = out(o)
    assert all(e["type"] != "VARIANT" for e in d["elements"]), d["elements"]
    # 꺼 둔 것도 빠지고, 남는 것은 화면·버튼 둘
    assert {e["ref"] for e in d["elements"]} == {"1:100", "1:200"}
    assert d["hidden_skipped"] == ["1:300"]


# =========================================================================
# 실제 파일에서 관찰한 모양 2 — 효과 여러 줄 · 에셋
#
# 아래 값은 지어낸 것이 아니라 실제 Figma MCP 응답에서 그대로 가져왔다.
# 지어낸 모양으로만 테스트해서 실제 응답에 통째로 못 쓴 적이 있다.
# =========================================================================

_REAL_ASSETS = """
nodes:
  - id: '2:1'
    name: 화면
    type: FRAME
    children:
      - id: '2:10'
        name: 카드
        type: FRAME
        effects: effect_FOUR
      - id: '2:11'
        name: 빛나는 것
        type: FRAME
        effects: effect_GLOW
      - id: '2:20'
        name: Vector
        type: IMAGE-SVG
        layout: layout_A
        fills: point_color
      - id: '2:21'
        name: Vector
        type: IMAGE-SVG
        layout: layout_B
        fills: point_color
      - id: '2:30'
        name: 뒤로가기
        type: IMAGE-SVG
        layout: layout_A
        fills: point_color
      - id: 'I2:40;9:9'
        name: Icon / Mobile Signal
        type: IMAGE-SVG
        componentId: '178:473'
        layout: layout_A
      - id: 'I2:41;9:9'
        name: Icon / Mobile Signal
        type: IMAGE-SVG
        componentId: '178:473'
        layout: layout_B
      - id: '2:50'
        name: 사진
        type: IMAGE
        layout: layout_A
        fills: fill_PHOTO
globalVars:
  styles:
    layout_A:
      dimensions: {width: 24, height: 24}
    layout_B:
      dimensions: {width: 48, height: 16}
    point_color:
      - '#00FFD0'
    fill_PHOTO:
      - type: IMAGE
        imageRef: abc123def
        scaleMode: FILL
        imageDownloadArguments:
          needsCropping: false
          requiresImageDimensions: true
    effect_FOUR:
      boxShadow: '0px 4px 20px 0px rgba(204, 188, 246, 1), inset 0px 8px 24px -16px rgba(255, 255, 255, 0.24), inset 0px -24px 32px 0px rgba(255, 255, 255, 0.24), inset 0px 0px 10px 2px rgba(255, 255, 255, 1)'
    effect_GLOW:
      boxShadow: 0px 0px 30px 0px rgba(0, 255, 208, 1)
      filter: blur(200px)
      backdropFilter: blur(10px)
"""


def _assets_dump(tmp_path):
    p = tmp_path / "assets.yaml"
    p.write_text(_REAL_ASSETS, encoding="utf-8")
    return p


def test_four_shadows_in_one_string_are_counted_as_four(tmp_path):
    """한 문자열에 쉼표로 이어 붙은 그림자를 한 줄로 세면 세 줄이 소리 없이 빠진다.

    실제 사고가 이것이었다 — 안쪽 그림자 셋이 빠진 채 배포됐다.
    """
    _, o, _ = run("coverage", "--dump", str(_assets_dump(tmp_path)))
    d = out(o)
    card = [i for i in d["items"] if i["ref"].startswith("2:10/effects")]
    assert len(card) == 4, card
    assert [i["ref"] for i in card] == [f"2:10/effects.boxShadow[{n}]" for n in range(4)]
    # rgba(...) 안의 쉼표에서 쪼개지면 값이 망가진다
    assert card[0]["value"] == "0px 4px 20px 0px rgba(204, 188, 246, 1)"
    assert card[3]["value"] == "inset 0px 0px 10px 2px rgba(255, 255, 255, 1)"


def test_effect_kinds_are_named(tmp_path):
    """무엇이 빠졌는지 알려면 종류에 이름이 있어야 한다."""
    _, o, _ = run("coverage", "--dump", str(_assets_dump(tmp_path)))
    d = out(o)
    kind = {i["ref"]: i["effect"] for i in d["items"] if i["kind"] == "effects"}
    assert kind["2:10/effects.boxShadow[0]"] == "그림자"
    assert kind["2:10/effects.boxShadow[1]"] == "안쪽 그림자"
    # 치우침 0 에 번짐만 있는 것 — 그림자로 뭉뚱그리면 눈에 안 띈다
    assert kind["2:11/effects.boxShadow"] == "글로우"
    assert kind["2:11/effects.filter"] == "블러"
    assert kind["2:11/effects.backdropFilter"] == "배경 블러"
    assert d["effect_counts"]["안쪽 그림자"] == 3


def test_same_name_different_shape_is_not_merged(tmp_path):
    """Figma 기본 이름 'Vector' 는 서로 다른 아이콘에 똑같이 붙는다.

    실측: 어느 실제 파일에서 'Vector' 71개가 48종의 서로 다른 그림이었다.
    이름으로 묶으면 아이콘 하나를 48곳에 잘못 쓴다.
    """
    _, o, _ = run("assets", "--dump", str(_assets_dump(tmp_path)))
    d = out(o)
    vectors = [a for a in d["assets"] if a["name"] == "Vector"]
    assert len(vectors) == 2, vectors
    assert {a["file_name"] for a in vectors} == {"vector.svg", "vector-2.svg"}


def test_same_component_is_merged_and_marked_certain(tmp_path):
    """componentId 가 같으면 같은 그림이 **확실하다** — 그때만 확실 표시를 준다."""
    _, o, _ = run("assets", "--dump", str(_assets_dump(tmp_path)))
    d = out(o)
    icon = [a for a in d["assets"] if a["name"] == "Icon / Mobile Signal"]
    assert len(icon) == 1, icon
    assert icon[0]["used"] == 2 and icon[0]["certain"] is True
    assert icon[0]["also"] == ["I2:41;9:9"]
    # 추정으로 묶은 것과 구분돼야 한다
    assert all(a["certain"] is False for a in d["assets"] if a["name"] == "Vector")


def test_every_file_name_passes_the_mcp_pattern(tmp_path):
    """download_figma_images 의 fileName 은 ^[a-zA-Z0-9_.-]+\\.(png|svg)$ 만 받는다.

    실측: 실제 파일의 에셋 609개 중 281개(46%)가 한글·공백·'/' 를 담은 이름이라
    레이어 이름을 그대로 넘기면 거부된다.
    """
    _, o, _ = run("assets", "--dump", str(_assets_dump(tmp_path)))
    d = out(o)
    pattern = re.compile(r"^[a-zA-Z0-9_.-]+\.(png|svg)$")
    bad = [n["fileName"] for n in d["nodes"] if not pattern.match(n["fileName"])]
    assert bad == [], bad
    assert len(d["nodes"]) == len(d["assets"])


def test_korean_name_keeps_its_meaning_for_the_agent(tmp_path):
    """자동 이름은 뜻을 잃는다. 원래 이름을 남겨 두고 고치라고 표시한다."""
    _, o, _ = run("assets", "--dump", str(_assets_dump(tmp_path)))
    d = out(o)
    back = [a for a in d["assets"] if a["name"] == "뒤로가기"]
    assert len(back) == 1
    assert back[0]["rename_me"] is True
    assert back[0]["file_name"] == "asset-2-30.svg"
    assert d["needs_naming"] == 2      # '뒤로가기' 와 '사진' 둘 다 한글이다
    # ASCII 가 남는 이름은 뜻을 지키므로 표시하지 않는다
    assert all(a["rename_me"] is False for a in d["assets"] if a["name"] == "Vector")


def test_photo_asks_for_image_ref_and_png(tmp_path):
    """imageRef 가 있는 것은 사진이다. 인자를 빠뜨리면 엉뚱한 그림이 온다."""
    _, o, _ = run("assets", "--dump", str(_assets_dump(tmp_path)))
    d = out(o)
    photo = [n for n in d["nodes"] if n["nodeId"] == "2:50"]
    assert photo == [{"nodeId": "2:50", "fileName": "asset-2-50.png",
                      "imageRef": "abc123def",
                      "requiresImageDimensions": True}], photo


def test_asset_size_comes_from_the_layout_reference(tmp_path):
    """크기조차 참조 뒤에 있다. 안 풀면 None 이 되고 묶는 근거가 사라진다."""
    _, o, _ = run("assets", "--dump", str(_assets_dump(tmp_path)))
    d = out(o)
    sizes = {a["file_name"]: (a["width"], a["height"]) for a in d["assets"]}
    assert sizes["vector.svg"] == (24, 24)
    assert sizes["vector-2.svg"] == (48, 16)


def test_coverage_surfaces_assets_and_effects_separately(tmp_path):
    """효과는 layout 수십 줄 사이에 묻히면 아무도 안 본다."""
    _, o, _ = run("coverage", "--dump", str(_assets_dump(tmp_path)))
    d = out(o)
    assert d["asset_count"] == 6
    assert len(d["effects"]) == 7        # 그림자 4 + 글로우·블러·배경블러
    assert "안쪽 그림자 3" in d["summary"]


def test_asset_with_effect_is_flagged_because_the_file_comes_bigger(tmp_path):
    """효과가 붙은 에셋은 번짐이 그림 안에 필터로 박혀 **더 크게** 온다.

    실측: layout 36x34 인 글로우 도형을 받으니 96x94 였다. 모르고 레이아웃
    크기로 넣으면 도형이 쪼그라들고, 효과를 코드로 또 넣으면 두 번 적용된다.
    """
    _, o, _ = run("assets", "--dump", str(_assets_dump(tmp_path)))
    d = out(o)
    assert d["with_baked_effect"] == 0      # 효과 붙은 에셋이 없는 덤프

    # 글로우 붙은 아이콘 하나를 넣으면 표시돼야 한다
    src = _REAL_ASSETS.replace("""      - id: '2:30'
        name: 뒤로가기
        type: IMAGE-SVG
        layout: layout_A
        fills: point_color""", """      - id: '2:30'
        name: 뒤로가기
        type: IMAGE-SVG
        layout: layout_A
        fills: point_color
        effects: effect_GLOW""")
    p = tmp_path / "baked.yaml"
    p.write_text(src, encoding="utf-8")
    _, o, _ = run("assets", "--dump", str(p))
    d = out(o)
    assert d["with_baked_effect"] == 1
    back = [a for a in d["assets"] if a["name"] == "뒤로가기"][0]
    assert "blur(200px)" in back["baked_effect"]
    assert "효과가 그림에 박혀 오는 것 1개" in d["summary"]


def test_human_named_style_keys_are_resolved(tmp_path):
    """스타일 키가 `fill_XXX` 만 오는 게 아니다.

    실측으로 `Label Color/Light/Primary`·`Callout / Bold` 처럼 사람이 붙인
    이름이 섞여 온다. 접두사로 참조를 판별하면 이것들을 못 풀고 지나간다.
    """
    p = tmp_path / "named.yaml"
    p.write_text("""
nodes:
  - id: '3:1'
    name: 글자
    type: TEXT
    fills: Label Color/Light/Primary
    textStyle: Callout / Bold
globalVars:
  styles:
    Label Color/Light/Primary:
      - '#000000'
    Callout / Bold:
      fontFamily: SF Pro Text
      fontSize: 16
""", encoding="utf-8")
    _, o, _ = run("coverage", "--dump", str(p))
    d = out(o)
    values = " ".join(str(i["value"]) for i in d["items"])
    assert "#000000" in values, d["items"]
    assert "SF Pro Text" in values, d["items"]
    assert "Label Color/Light/Primary" not in values, "참조가 값으로 남았다"
