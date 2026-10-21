"""빌릴 기기 판정 (순수 함수): 조건 · 기기 사실 · 소유 · 자원 > verdict + 이유 (#953 · #954 · #964).

단계(DECISION_STEPS) 순서대로 처음 결과를 낸 단계가 이긴다. 플랫폼 이름이 아니라 capabilities 만 본다.
verdict 6개: reuse · reclaim · create · wait · ask · no_match
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from pro_launch.runtime.device_backends.base import Capabilities, DeviceFacts, is_os_satisfied

VERDICTS = ("reuse", "reclaim", "create", "wait", "ask", "no_match")


@dataclass(frozen=True)
class AcquireRequest:
    """빌리는 조건. device 를 주면 그 기기 하나만 본다 (사람이 켠 기기 제외 규칙도 풀린다).

    needs: 있어야 하는 공들인 상태 ("login:kakao") · is_fresh_required: 아무도 쓰지 않은 새 폰
    """

    platform: str
    form: str = "phone"
    os_minimum: str | None = None
    device: str | None = None
    purpose: str | None = None
    needs: tuple[str, ...] = ()
    is_fresh_required: bool = False
    # 사용자가 메모리 위험을 보고 켜도 된다고 답했다 (--user-approved) — 메모리 게이트만 넘는다, 디스크·남의 소유는 그대로
    is_memory_risk_user_approved: bool = False


@dataclass(frozen=True)
class Candidate:
    """기기 하나의 판정 재료. lease 목록은 부르는 쪽이 살아 있음·내 것 여부로 나눠 준다."""

    facts: DeviceFacts
    capabilities: Capabilities
    live_other_leases: tuple[dict, ...] = ()
    dead_other_leases: tuple[dict, ...] = ()
    own_leases: tuple[dict, ...] = ()
    # 원장(acquire)이 켰고 아직 끄지 않은 기기 — 켜져 있어도 사람이 쓰는 기기가 아니다
    is_pool_booted: bool = False
    last_used: float | None = None
    # 기록된 공들인 상태 ("kind:name") · create 로 만든 뒤 아무도 쓰지 않은 기기
    marks: tuple[str, ...] = ()
    is_pristine: bool = False


@dataclass(frozen=True)
class PoolContext:
    """호스트 자원 · 대기 · 만들기 한도 (부르는 쪽이 사실을 채운다)."""

    pressure: str = "ok"
    waited_seconds: float = 0.0
    wait_limit_seconds: float = 600.0
    can_create: bool = False
    is_disk_low: bool = False
    # 새 기기를 켜면 안 되는 이유 (메모리 예산 초과 · 지금 여유 부족, device_capacity) — 없으면 None
    boot_block: str | None = None


@dataclass(frozen=True)
class Decision:
    verdict: str
    device_key: str | None = None
    reasons: tuple[str, ...] = ()
    is_boot_needed: bool = False
    reclaimed_from: dict | None = None
    busy_owners: tuple[dict, ...] = field(default_factory=tuple)
    # ask 가 메모리 위험 때문이다 — 사용자 답을 받은 뒤 --user-approved 로 넘을 수 있다
    is_memory_risk: bool = False


@dataclass
class _Working:
    """단계들이 함께 채우는 중간 결과."""

    matching: list[Candidate] = field(default_factory=list)
    eligible: list[Candidate] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    # 임시 기기를 못 만드는 이유 (자원 한도) — 있으면 마지막에 ask
    create_block: str | None = None
    is_create_block_memory: bool = False


def _memory_block(request: AcquireRequest, context: PoolContext) -> str | None:
    """새로 켜면 안 되는 메모리 이유 (critical > 예산 초과). 사용자가 승인했으면 None."""
    if request.is_memory_risk_user_approved:
        return None
    if context.pressure == "critical":
        return "host memory is critical; the user must confirm before booting another device"
    return context.boot_block


def _owner_phrase(lease: dict) -> str:
    purpose = f", {lease['purpose']}" if lease.get("purpose") else ""
    return f"session {str(lease.get('session'))[:8]}{purpose}"


def _filter_matching(request: AcquireRequest, candidates: list[Candidate], working: _Working) -> Decision | None:
    """조건 필터 (platform · device 지정 · form · OS)."""
    for candidate in candidates:
        facts = candidate.facts
        if facts.platform != request.platform:
            continue
        if request.device:
            if request.device in (facts.key, facts.instance):
                working.matching.append(candidate)
            continue
        if facts.form != request.form or not is_os_satisfied(facts.os_version, request.os_minimum):
            continue
        missing = [need for need in request.needs if need not in candidate.marks]
        if missing:
            continue
        if request.is_fresh_required and not candidate.is_pristine:
            continue
        working.matching.append(candidate)
    if not working.matching:
        wanted = request.device or f"{request.platform} {request.form}" + (f" OS {request.os_minimum}" if request.os_minimum else "")
        if request.needs:
            working.reasons.append(f"no {wanted} device has {', '.join(request.needs)} recorded — a new device would not have that state either")
        elif request.is_fresh_required:
            working.reasons.append(f"no unused fresh {wanted} device")
        else:
            working.reasons.append(f"no device matches ({wanted})")
    return None


def _filter_eligible(request: AcquireRequest, candidates: list[Candidate], working: _Working) -> Decision | None:
    """자격 필터: 사람이 켠 기기 · 이 세션이 이미 쥔 기기 · 켤 수 없는 꺼진 기기를 뺀다 (device 지정 시 앞 둘은 유지)."""
    for candidate in working.matching:
        facts, name = candidate.facts, candidate.facts.name
        is_unrecorded_booted = (facts.is_booted and not candidate.capabilities.is_physical and not candidate.is_pool_booted
                                and not candidate.live_other_leases and not candidate.own_leases)
        if not request.device and is_unrecorded_booted:
            working.reasons.append(f"{name}: running but not in the ledger, so a person may be using it — skipped")
            continue
        if not request.device and candidate.own_leases:
            working.reasons.append(f"{name}: already held by this session — looking for another device")
            continue
        if not facts.is_booted and not candidate.capabilities.can_boot:
            working.reasons.append(f"{name}: off and cannot be booted — skipped")
            continue
        working.eligible.append(candidate)
    return None


def _choose_free(request: AcquireRequest, candidates: list[Candidate], working: _Working,
                 context: PoolContext) -> Decision | None:
    """빈 기기: 켜져 있는 것(다시 켜는 비용 없음) > 최근 사용. 죽은 소유가 남아 있으면 reclaim."""
    free = [c for c in working.eligible if not c.live_other_leases]
    if not free:
        return None
    chosen = sorted(free, key=lambda c: (c.facts.is_booted, c.last_used or 0), reverse=True)[0]
    is_boot_needed = not chosen.facts.is_booted
    reasons = [*working.reasons, f"{chosen.facts.name}: free" + (" (off, will boot)" if is_boot_needed else " (running)")]
    memory_block = _memory_block(request, context) if is_boot_needed else None
    if memory_block:
        return Decision("ask", reasons=tuple(reasons + [memory_block]), is_memory_risk=True)
    if chosen.dead_other_leases:
        dead = max(chosen.dead_other_leases, key=lambda lease: lease.get("last_used") or 0)
        reasons.append(f"{chosen.facts.name}: ownership by {_owner_phrase(dead)} ended (host exited or idle) — taking it over")
        return Decision("reclaim", chosen.facts.key, tuple(reasons), is_boot_needed, reclaimed_from=dead)
    return Decision("reuse", chosen.facts.key, tuple(reasons), is_boot_needed)


def _create_if_allowed(request: AcquireRequest, candidates: list[Candidate], working: _Working,
                       context: PoolContext) -> Decision | None:
    """빈 기기가 없을 때 임시 기기 만들기 — 특정 기기·공들인 상태 조건이면 만들지 않는다 (만들어도 소용없다).

    자원 한도 3개: 메모리 critical · 디스크 부족 · 메모리 예산(device_capacity). 걸리면 이유를 남기고 다음 단계로.
    """
    if request.device or request.needs or not context.can_create:
        return None
    memory_block = _memory_block(request, context)
    if memory_block and context.pressure == "critical":
        working.create_block, working.is_create_block_memory = "host memory is critical; not creating and booting a new device", True
    elif context.is_disk_low:
        working.create_block = "not enough free disk; not creating a new device (check device gc for things to clean up)"
    elif memory_block:
        working.create_block, working.is_create_block_memory = memory_block, True
    if working.create_block:
        return None
    return Decision("create", reasons=tuple([*working.reasons, "no free matching device; creating and booting a temporary device"]),
                    is_boot_needed=True)


def _wait_or_ask(request: AcquireRequest, candidates: list[Candidate], working: _Working,
                 context: PoolContext) -> Decision:
    """맞는 기기가 남이 쓰는 중이면 대기 한도 전엔 wait, 넘으면 ask. 아무것도 없으면 no_match · 자원 한도면 ask."""
    owners = tuple({"device": c.facts.name, "key": c.facts.key, **lease}
                   for c in working.eligible for lease in c.live_other_leases)
    if not owners:
        if working.create_block:
            return Decision("ask", reasons=tuple([*working.reasons, working.create_block]),
                            is_memory_risk=working.is_create_block_memory)
        return Decision("no_match", reasons=tuple(working.reasons) or ("no device available to borrow",))
    reasons = [*working.reasons, *(f"{o['device']}: in use by {_owner_phrase(o)}" for o in owners),
               *([working.create_block] if working.create_block else [])]
    if context.waited_seconds >= context.wait_limit_seconds:
        minutes = round(context.waited_seconds / 60)
        return Decision("ask", reasons=tuple(reasons + [f"waited {minutes} min — ask the user to decide"]), busy_owners=owners)
    return Decision("wait", reasons=tuple(reasons), busy_owners=owners)


DECISION_STEPS: tuple[Callable[..., Decision | None], ...] = (
    lambda request, candidates, working, context: _filter_matching(request, candidates, working),
    lambda request, candidates, working, context: _filter_eligible(request, candidates, working),
    _choose_free,
    _create_if_allowed,
    _wait_or_ask,
)


def decide(request: AcquireRequest, candidates: list[Candidate], context: PoolContext | None = None) -> Decision:
    """조건에 맞는 기기 하나를 고른다 > Decision (reasons 는 항상 하나 이상)."""
    working, chosen_context = _Working(), context or PoolContext()
    for step in DECISION_STEPS:
        decision = step(request, candidates, working, chosen_context)
        if decision is not None:
            return decision
    return Decision("no_match", reasons=("no decision step returned a result",))
