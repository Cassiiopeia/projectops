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
