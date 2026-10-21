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


@dataclass
class _Working:
    """단계들이 함께 채우는 중간 결과."""

    matching: list[Candidate] = field(default_factory=list)
    eligible: list[Candidate] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    # 임시 기기를 못 만드는 이유 (자원 한도) — 있으면 마지막에 ask
    create_block: str | None = None


def _owner_phrase(lease: dict) -> str:
    purpose = f", {lease['purpose']}" if lease.get("purpose") else ""
    return f"세션 {str(lease.get('session'))[:8]}{purpose}"


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
            working.reasons.append(f"{', '.join(request.needs)} 가 기록된 {wanted} 기기가 없다 — 새로 만들어도 그 상태는 없다")
        elif request.is_fresh_required:
            working.reasons.append(f"아무도 쓰지 않은 새 {wanted} 기기가 없다")
        else:
            working.reasons.append(f"조건({wanted})에 맞는 기기가 없다")
    return None


def _filter_eligible(request: AcquireRequest, candidates: list[Candidate], working: _Working) -> Decision | None:
    """자격 필터: 사람이 켠 기기 · 이 세션이 이미 쥔 기기 · 켤 수 없는 꺼진 기기를 뺀다 (device 지정 시 앞 둘은 유지)."""
    for candidate in working.matching:
        facts, name = candidate.facts, candidate.facts.name
        is_unrecorded_booted = (facts.is_booted and not candidate.capabilities.is_physical and not candidate.is_pool_booted
                                and not candidate.live_other_leases and not candidate.own_leases)
        if not request.device and is_unrecorded_booted:
            working.reasons.append(f"{name}: 켜져 있지만 원장 기록이 없어 사람이 쓰는 기기일 수 있다 — 제외")
            continue
        if not request.device and candidate.own_leases:
            working.reasons.append(f"{name}: 이 세션이 이미 쥔 기기 — 다른 기기를 찾는다")
            continue
        if not facts.is_booted and not candidate.capabilities.can_boot:
            working.reasons.append(f"{name}: 꺼져 있고 켤 수 없다 — 제외")
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
    reasons = [*working.reasons, f"{chosen.facts.name}: 비어 있다" + (" (꺼져 있어 켠다)" if is_boot_needed else " (켜져 있다)")]
    if is_boot_needed and context.pressure == "critical":
        return Decision("ask", reasons=tuple(reasons + ["호스트 메모리가 위험 수준이라 새로 켜기 전에 사용자 확인이 필요하다"]))
    if is_boot_needed and context.boot_block:
        return Decision("ask", reasons=tuple(reasons + [context.boot_block]))
    if chosen.dead_other_leases:
        dead = max(chosen.dead_other_leases, key=lambda lease: lease.get("last_used") or 0)
        reasons.append(f"{chosen.facts.name}: {_owner_phrase(dead)} 의 소유는 끝났다(호스트 종료 또는 유휴) — 넘겨받는다")
        return Decision("reclaim", chosen.facts.key, tuple(reasons), is_boot_needed, reclaimed_from=dead)
    return Decision("reuse", chosen.facts.key, tuple(reasons), is_boot_needed)


def _create_if_allowed(request: AcquireRequest, candidates: list[Candidate], working: _Working,
                       context: PoolContext) -> Decision | None:
    """빈 기기가 없을 때 임시 기기 만들기 — 특정 기기·공들인 상태 조건이면 만들지 않는다 (만들어도 소용없다).

    자원 한도 3개: 메모리 critical · 디스크 부족 · 메모리 예산(device_capacity). 걸리면 이유를 남기고 다음 단계로.
    """
    if request.device or request.needs or not context.can_create:
        return None
    if context.pressure == "critical":
        working.create_block = "호스트 메모리가 위험 수준이라 새 기기를 만들어 켜지 않는다"
    elif context.is_disk_low:
        working.create_block = "디스크 여유가 부족해 새 기기를 만들지 않는다 (device gc 로 정리할 것이 있는지 본다)"
    elif context.boot_block:
        working.create_block = context.boot_block
    if working.create_block:
        return None
    return Decision("create", reasons=tuple([*working.reasons, "조건에 맞는 빈 기기가 없어 임시 기기를 만들어 켠다"]),
                    is_boot_needed=True)


def _wait_or_ask(request: AcquireRequest, candidates: list[Candidate], working: _Working,
                 context: PoolContext) -> Decision:
    """맞는 기기가 남이 쓰는 중이면 대기 한도 전엔 wait, 넘으면 ask. 아무것도 없으면 no_match · 자원 한도면 ask."""
    owners = tuple({"device": c.facts.name, "key": c.facts.key, **lease}
                   for c in working.eligible for lease in c.live_other_leases)
    if not owners:
        if working.create_block:
            return Decision("ask", reasons=tuple([*working.reasons, working.create_block]))
        return Decision("no_match", reasons=tuple(working.reasons) or ("빌릴 수 있는 기기가 없다",))
    reasons = [*working.reasons, *(f"{o['device']}: {_owner_phrase(o)} 사용 중" for o in owners),
               *([working.create_block] if working.create_block else [])]
    if context.waited_seconds >= context.wait_limit_seconds:
        minutes = round(context.waited_seconds / 60)
        return Decision("ask", reasons=tuple(reasons + [f"{minutes}분 기다렸다 — 사용자에게 물어 정한다"]), busy_owners=owners)
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
    return Decision("no_match", reasons=("판정 단계가 결과를 내지 않았다",))
