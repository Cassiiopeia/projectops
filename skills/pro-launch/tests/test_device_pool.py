"""빌릴 기기 판정 (#953) — 순수 함수라 기기·원장 없이 사실만 넣어 검사한다."""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from pro_launch.runtime.device_backends.base import Capabilities, DeviceFacts  # noqa: E402
from pro_launch.runtime.device_pool import AcquireRequest, Candidate, PoolContext, decide, is_os_satisfied  # noqa: E402

VIRTUAL = Capabilities(can_boot=True, can_shutdown=True)
PHYSICAL = Capabilities(is_physical=True)
OTHER = {"session": "other-session", "purpose": "#866", "last_used": 100.0}


def cand(key="A", *, booted=False, pool_booted=False, live=(), dead=(), own=(), form="phone", os_version="18.3",
         last_used=None, capabilities=VIRTUAL, platform="ios"):
    facts = DeviceFacts(key=key, platform=platform, backend="test", name=f"dev-{key}", form=form,
                        os_version=os_version, is_booted=booted, instance=key if booted else None)
    return Candidate(facts, capabilities, tuple(live), tuple(dead), tuple(own), pool_booted, last_used)


def ios(**kwargs):
    return AcquireRequest(platform="ios", **kwargs)


def test_reuse_prefers_booted_then_recent():
    decision = decide(ios(), [cand("A", last_used=50), cand("B", booted=True, pool_booted=True, last_used=10),
                              cand("C", last_used=90)])
    assert (decision.verdict, decision.device_key, decision.is_boot_needed) == ("reuse", "B", False)
    shut_only = decide(ios(), [cand("A", last_used=50), cand("C", last_used=90)])
    assert (shut_only.device_key, shut_only.is_boot_needed) == ("C", True)


def test_booted_unleased_unrecorded_device_is_not_a_candidate():
    decision = decide(ios(), [cand("A", booted=True)])
    assert decision.verdict == "no_match"
    assert any("사람이 쓰는 기기일 수 있다" in reason for reason in decision.reasons)


def test_explicit_device_overrides_human_booted_exclusion():
    decision = decide(ios(device="A"), [cand("A", booted=True), cand("B")])
    assert (decision.verdict, decision.device_key) == ("reuse", "A")


def test_physical_device_is_not_excluded_as_human_booted():
    decision = decide(AcquireRequest(platform="android"),
                      [cand("R5", booted=True, capabilities=PHYSICAL, platform="android")])
    assert decision.verdict == "reuse"


def test_same_session_gets_a_different_device():
    decision = decide(ios(), [cand("A", booted=True, pool_booted=True, own=[{"session": "me"}]), cand("B")])
    assert decision.device_key == "B"


def test_dead_lease_is_reclaimed_with_reason():
    decision = decide(ios(), [cand("A", booted=True, pool_booted=True, dead=[OTHER])])
    assert decision.verdict == "reclaim" and decision.reclaimed_from == OTHER
    assert any("넘겨받는다" in reason for reason in decision.reasons)


def test_boot_under_critical_pressure_asks():
    decision = decide(ios(), [cand("A")], PoolContext(pressure="critical"))
    assert decision.verdict == "ask"
    booted_free = decide(ios(), [cand("A", booted=True, pool_booted=True)], PoolContext(pressure="critical"))
    assert booted_free.verdict == "reuse"


def test_wait_then_ask_after_limit():
    busy = [cand("A", booted=True, live=[OTHER])]
    assert decide(ios(), busy, PoolContext(waited_seconds=599)).verdict == "wait"
    decision = decide(ios(), busy, PoolContext(waited_seconds=600))
    assert decision.verdict == "ask" and decision.busy_owners[0]["purpose"] == "#866"


def test_form_and_os_filters():
    candidates = [cand("P", form="phone", os_version="16.4"), cand("T", form="tablet", os_version="18.3")]
    assert decide(ios(form="tablet"), candidates).device_key == "T"
    assert decide(ios(os_minimum=">=17"), candidates).verdict == "no_match"
    assert is_os_satisfied("17.2", "17") and not is_os_satisfied(None, "17") and is_os_satisfied(None, None)


def test_every_decision_has_reasons():
    cases = [decide(ios(), []), decide(ios(), [cand("A")]), decide(ios(), [cand("A", booted=True, live=[OTHER])]),
             decide(ios(), [cand("A", booted=True)])]
    assert all(decision.reasons for decision in cases)
