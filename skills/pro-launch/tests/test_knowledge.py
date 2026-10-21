"""컴퓨터별 학습 메모(recall · learn · forget) 테스트.

⚠️ 진짜 홈을 건드리지 않는다 — 전부 임시 HOME 으로 돌린다.
지키려는 것: 강화(카운터)·상한·비밀값 거절·금지 방법이 기억으로 되살아나지 않는 것.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import knowledge  # noqa: E402


def test_long_how_is_refused_not_silently_truncated(tmp_path):
    """조용히 자르면 결론이 문장 중간에서 사라진다 (#863) — 길이·상한과 함께 거절한다."""
    p = tmp_path / "k.json"
    r = knowledge.learn(p, "web", "long", "가" * 350, "ok", today="2026-09-29")
    assert r["error"] == "too_long" and r["length"] == 350 and r["limit"] == knowledge.MAX_HOW
    assert knowledge.load(p) == []


@pytest.mark.parametrize("how", ["password: hunter2secret 로 로그인", "me@example.com 계정으로 로그인",
                                 "토큰 eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkw 사용"])
def test_secrets_are_refused(tmp_path, how):
    p = tmp_path / "k.json"
    r = knowledge.learn(p, "web", "login", how, "ok")
    assert r["error"] == "secret_detected" and not p.exists()


def test_forbidden_method_in_an_old_file_is_filtered_on_recall(tmp_path):
    """손으로 고친 파일·옛 파일에 금지 방법이 있어도 꺼내지 않는다 — 기억이 안전 규칙을 우회하면 안 된다."""
    p = tmp_path / "k.json"
    p.write_text(json.dumps({"schema": 1, "entries": [
        {"key": "ios.tap", "area": "ios", "how": "cliclick 으로 누른다", "ok": 9, "fail": 0,
         "last_seen": "2026-09-29"},
        {"key": "ios.e2e", "area": "ios", "how": "Maestro 플로우", "ok": 1, "fail": 0,
         "last_seen": "2026-09-29"}]}), encoding="utf-8")
    rows = knowledge.recall({"repo": p}, "ios", today="2026-09-29")
    assert [r["key"] for r in rows] == ["ios.e2e"]
