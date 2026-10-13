"""extras 플러그인은 설치 시 자기 폴더만 복사된다(Claude Code). 그래서 공유 문서를 사본으로 들고 가고,
사본이 정본(skills/references)과 다르면 막는다 (#864)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from sync_extras import COPIES, EXTRAS  # noqa: E402


def test_copies_identical():
    stale = [dst for src, dst in COPIES if (ROOT / src).read_bytes() != (EXTRAS / dst).read_bytes()]
    assert stale == [], "python3 scripts/sync_extras.py 를 실행하라"


def test_extras_references_resolve():
    skill = EXTRAS / "skills" / "pro-synology-expose" / "SKILL.md"
    for ref in ["../references/config-rules.md", "../references/preferences.md"]:
        assert (skill.parent / ref).resolve().exists(), ref


def test_marketplace_lists_both_plugins():
    m = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    names = {p["name"]: p for p in m["plugins"]}
    assert names["projectops-extras"]["source"] == "./plugins/projectops-extras"
    assert names["projectops-extras"]["version"] == names["projectops"]["version"]


def test_core_no_longer_ships_synology():
    assert not (ROOT / "skills" / "pro-synology-expose").exists()
