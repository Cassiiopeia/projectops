"""전역 출력 모양 옵션 --brief · --fields 와 키 순서 (#898).

잘라 읽다가 next·memory·known_fix 를 잃던 문제 — 줄여도 그 키들은 남고, 플래그가 없으면 키 집합이 그대로인지 본다.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from pro_launch.runtime import output as rt_output  # noqa: E402
from pro_launch.runtime.context import OUTPUT_CTX  # noqa: E402


@pytest.fixture(autouse=True)
def reset_output_shape():
    OUTPUT_CTX.clear()
    yield
    OUTPUT_CTX.clear()


def _sample_failure() -> dict:
    return {"ok": False, "code": "boom", "error": "실패", "path": "/x", "url": "u",
            "learn_hint": "h", "summary": "요약", "known_fix": [{"id": "k"}], "next": "다음",
            "memory": [{"key": "m"}], "plugin_version": "9.9.9"}


# 순서: 머리 4필드 > 안내 > 나머지 (값은 그대로)
def test_order_puts_head_then_guidance_then_rest():
    payload = _sample_failure()
    shaped = rt_output.shape_payload(dict(payload))
    assert list(shaped)[:8] == ["ok", "code", "summary", "next", "known_fix", "memory", "learn_hint", "plugin_version"]
    assert list(shaped)[8:] == ["error", "path", "url"]
    assert shaped == payload


def test_brief_keeps_core_and_error_only():
    OUTPUT_CTX.update(is_brief=True)
    shaped = rt_output.shape_payload(_sample_failure())
    assert set(shaped) == {"ok", "code", "summary", "next", "error", "known_fix", "memory", "learn_hint",
                           "plugin_version"}


# ── #972 실패 응답 · --brief · --fields 별칭 · learn_hint ──────────────

def test_failure_summary_never_says_done():
    assert rt_output.default_summary({"ok": False, "action": "acquire", "code": "needs_user",
                                      "reasons": ["메모리 위험"]}) == "메모리 위험"
    summary = rt_output.default_summary({"ok": False, "action": "boot", "code": "boot_failed"})
    assert "done" not in summary and summary.startswith("boot failed") and "boot_failed" in summary


def test_brief_keeps_failure_evidence_that_next_points_to():
    OUTPUT_CTX.update(is_brief=True)
    shaped = rt_output.shape_payload({"ok": False, "code": "needs_user", "reasons": ["r"], "output_tail": "t",
                                      "limits": {}})
    assert "reasons" in shaped and "output_tail" in shaped and "limits" not in shaped
    assert "reasons" not in rt_output.shape_payload({"ok": True, "reasons": ["r"]})


def test_fields_path_is_an_alias_of_file():
    OUTPUT_CTX.update(field_names=["path"])
    shaped = rt_output.shape_payload({"ok": True, "file": "/shot.webp", "url": "u"})
    assert shaped["file"] == "/shot.webp" and "unknown_fields" not in shaped and "url" not in shaped


def test_intended_failure_then_success_gives_no_learn_hint(tmp_path):
    attempts = tmp_path / "attempts.json"
    assert rt_output._track_attempt(attempts, "android", {"ok": False, "code": "wait_timeout"}) is None
    assert rt_output._track_attempt(attempts, "android", {"ok": True}) is None
    rt_output._track_attempt(attempts, "android", {"ok": False, "code": "boot_failed"})
    assert rt_output._track_attempt(attempts, "android", {"ok": True}) is not None
