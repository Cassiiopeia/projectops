"""figma_verify_cli 테스트 (이슈 #616).

지키려는 것은 하나다 — **빠진 것이 빠진 채로 통과하지 않는다.**

실사고: 어떤 버튼의 효과 네 줄 중 안쪽 세 줄이 통째로 빠진 채 배포됐다. 전체 화면
골든을 만들어 놓고도 지나갔고, 디자이너가 배포 **후에** 발견했다. 그래서 이 스크립트가
지켜야 할 계약은

  - 배열은 **원소마다 한 줄**로 센다 (통째로 한 줄이면 한 줄 빠져도 티가 안 난다)
  - 스타일을 못 찾으면 **실패한다** (0건으로 조용히 통과하면 대조를 안 한 것과 같다)
  - 다른 곳을 **덩어리 좌표**로 짚는다 (퍼센트만으로는 어디가 틀렸는지 모른다)
"""
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
