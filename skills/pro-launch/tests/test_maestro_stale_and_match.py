"""iOS Maestro 잔여 드라이버 자동 정리 (#922) · 라벨 매칭 (#927). 기기 없이 돈다."""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import maestro_drivers  # noqa: E402
import node_match  # noqa: E402

UDID = "3F328F1A-16D1-453B-A0D3-94CDC21C4189"


def _node(text="", desc="", id_=""):
    return {"text": text, "desc": desc, "id": id_, "clickable": True, "bounds": [0, 0, 10, 10], "center": [5, 5]}


# ── #927 매칭 ───────────────────────────────────────────────────────────

def test_doubled_flutter_label_matches_single_text():
    nodes = [_node(text="GitHub로 계속하기\nGitHub로 계속하기")]
    found, by, kind = node_match.find_nodes(nodes, "text", "GitHub로 계속하기")
    assert found == nodes and by == "text" and kind == "normalized"


# ── #922 드라이버 가르기 ────────────────────────────────────────────────


def test_auto_clean_is_conservative():
    old = {"owner": "orphan", "kind": maestro_drivers.KIND_XCODEBUILD_DRIVER, "udid": UDID, "age_seconds": 600}
    assert maestro_drivers.is_auto_cleanable(old, UDID)
    assert not maestro_drivers.is_auto_cleanable({**old, "udid": "OTHER"}, UDID)
    assert not maestro_drivers.is_auto_cleanable({**old, "udid": None}, UDID)
    assert not maestro_drivers.is_auto_cleanable({**old, "age_seconds": 5}, UDID)
    assert not maestro_drivers.is_auto_cleanable({**old, "owner": "active"}, UDID)
