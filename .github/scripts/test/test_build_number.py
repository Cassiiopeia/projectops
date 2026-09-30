"""빌드 번호 규칙 테스트 (이슈 #643)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import build_number as bn


def test_time_based_number_is_seconds_since_2024():
    assert bn.time_based_number(now=1704067200 + 86677440) == 86677440


def test_next_uses_time_when_no_floor():
    r = bn.next_build_number(now=1704067200 + 100)
    assert r == {"build_number": 100, "source": "time", "built_at_utc": "2024-01-01T00:01:40Z"}


def test_next_uses_floor_when_larger():
    r = bn.next_build_number(floors=[2026093001], now=1704067200 + 100)
    assert r["build_number"] == 2026093001 and r["source"] == "floor"


def test_next_ignores_none_and_nonpositive_floors():
    assert bn.next_build_number(floors=[None, 0, -5], now=1704067200 + 7)["build_number"] == 7


def test_monotonic_over_time():
    assert bn.time_based_number(now=1704067200 + 10) < bn.time_based_number(now=1704067200 + 11)


def test_describe_roundtrip():
    assert bn.describe(86677440) == "2026-09-30T05:04:00Z"


def test_cli_next_prints_json_and_writes_output(tmp_path, monkeypatch, capsys):
    out = tmp_path / "out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setattr(bn.time, "time", lambda: 1704067200 + 42)
    assert bn.main(["next", "--floor", "5"]) == 0
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["ok"] is True and payload["build_number"] == 42
    assert "build_number=42" in out.read_text()
