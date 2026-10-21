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
    assert any("a person may be using it" in reason for reason in decision.reasons)


def test_dead_lease_is_reclaimed_with_reason():
    decision = decide(ios(), [cand("A", booted=True, pool_booted=True, dead=[OTHER])])
    assert decision.verdict == "reclaim" and decision.reclaimed_from == OTHER
    assert any("taking it over" in reason for reason in decision.reasons)


def test_wait_then_ask_after_limit():
    busy = [cand("A", booted=True, live=[OTHER])]
    assert decide(ios(), busy, PoolContext(waited_seconds=599)).verdict == "wait"
    decision = decide(ios(), busy, PoolContext(waited_seconds=600))
    assert decision.verdict == "ask" and decision.busy_owners[0]["purpose"] == "#866"


# ── #954 공들인 상태 · 새 폰 · 만들기 ───────────────────────────────────


def test_need_without_any_marked_device_never_creates():
    decision = decide(ios(needs=("login:kakao",)), [cand("A")], PoolContext(can_create=True))
    assert decision.verdict == "no_match"
    assert any("a new device would not have that state either" in reason for reason in decision.reasons)


# 메모리 위험은 사용자 승인(--user-approved)으로만 넘는다 — 디스크 부족은 승인으로 넘지 않는다 (#972)
def test_memory_risk_asks_until_user_approves():
    critical = PoolContext(pressure="critical")
    decision = decide(ios(), [cand("A")], critical)
    assert decision.verdict == "ask" and decision.is_memory_risk
    assert decide(ios(is_memory_risk_user_approved=True), [cand("A")], critical).verdict == "reuse"
    disk_low = PoolContext(can_create=True, is_disk_low=True)
    decision = decide(ios(is_memory_risk_user_approved=True), [], disk_low)
    assert decision.verdict == "ask" and not decision.is_memory_risk
