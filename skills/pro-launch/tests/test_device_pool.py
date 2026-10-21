"""빌릴 기기 판정 (#953) — 순수 함수라 기기·원장 없이 사실만 넣어 검사한다."""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from pro_launch.runtime.device_backends.base import Capabilities, DeviceFacts  # noqa: E402
from pro_launch.runtime.device_pool import AcquireRequest, Candidate, PoolContext, decide  # noqa: E402

VIRTUAL = Capabilities(can_boot=True, can_shutdown=True)
OTHER = {"session": "other-session", "purpose": "#866", "last_used": 100.0}


def cand(key="A", *, booted=False, pool_booted=False, live=(), dead=(), own=(), form="phone", os_version="18.3",
         last_used=None, capabilities=VIRTUAL, platform="ios"):
    facts = DeviceFacts(key=key, platform=platform, backend="test", name=f"dev-{key}", form=form,
                        os_version=os_version, is_booted=booted, instance=key if booted else None)
    return Candidate(facts, capabilities, tuple(live), tuple(dead), tuple(own), pool_booted, last_used)


def ios(**kwargs):
    return AcquireRequest(platform="ios", **kwargs)


def test_booted_unleased_unrecorded_device_is_not_a_candidate():
    decision = decide(ios(), [cand("A", booted=True)])
    assert decision.verdict == "no_match"
    assert any("사람이 쓰는 기기일 수 있다" in reason for reason in decision.reasons)


def test_dead_lease_is_reclaimed_with_reason():
    decision = decide(ios(), [cand("A", booted=True, pool_booted=True, dead=[OTHER])])
    assert decision.verdict == "reclaim" and decision.reclaimed_from == OTHER
    assert any("넘겨받는다" in reason for reason in decision.reasons)


def test_wait_then_ask_after_limit():
    busy = [cand("A", booted=True, live=[OTHER])]
    assert decide(ios(), busy, PoolContext(waited_seconds=599)).verdict == "wait"
    decision = decide(ios(), busy, PoolContext(waited_seconds=600))
    assert decision.verdict == "ask" and decision.busy_owners[0]["purpose"] == "#866"


# ── #954 공들인 상태 · 새 폰 · 만들기 ───────────────────────────────────


def test_need_without_any_marked_device_never_creates():
    decision = decide(ios(needs=("login:kakao",)), [cand("A")], PoolContext(can_create=True))
    assert decision.verdict == "no_match"
    assert any("새로 만들어도 그 상태는 없다" in reason for reason in decision.reasons)


