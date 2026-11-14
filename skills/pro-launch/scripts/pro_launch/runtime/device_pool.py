"""Deciding which device to borrow (pure functions): conditions · device facts · ownership · resources > verdict + reasons (#953 · #954 · #964).

The first step in DECISION_STEPS order that produces a result wins. Looks only at capabilities, never platform names.
6 verdicts: reuse · reclaim · create · wait · ask · no_match
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from pro_launch.runtime.device_backends.base import Capabilities, DeviceFacts, is_os_satisfied

VERDICTS = ("reuse", "reclaim", "create", "wait", "ask", "no_match")


@dataclass(frozen=True)
class AcquireRequest:
    """Borrowing conditions. Given device, only that one device is considered (the human-started-device exclusion is lifted too).

    needs: prepared states that must exist ("login:kakao") · is_fresh_required: a new phone nobody has used
    """

    platform: str
    form: str = "phone"
    os_minimum: str | None = None
    device: str | None = None
    purpose: str | None = None
    needs: tuple[str, ...] = ()
    is_fresh_required: bool = False
    # The user saw the memory risk and said it may boot (--user-approved) — passes only the memory gate; disk and others' ownership still apply
    is_memory_risk_user_approved: bool = False


@dataclass(frozen=True)
class Candidate:
    """Decision inputs for one device. The caller splits the lease list into live and mine."""

    facts: DeviceFacts
    capabilities: Capabilities
    live_other_leases: tuple[dict, ...] = ()
    dead_other_leases: tuple[dict, ...] = ()
    own_leases: tuple[dict, ...] = ()
    # Device the ledger (acquire) powered on and has not powered off — not a human-used device even when on
    is_pool_booted: bool = False
    last_used: float | None = None
    # Recorded prepared states ("kind:name") · device nobody has used since create
    marks: tuple[str, ...] = ()
    is_pristine: bool = False


@dataclass(frozen=True)
class PoolContext:
    """Host resources · waiting · create limits (the caller fills in the facts)."""

    pressure: str = "ok"
    waited_seconds: float = 0.0
    wait_limit_seconds: float = 600.0
    can_create: bool = False
    is_disk_low: bool = False
    # Why a new device must not boot (memory budget exceeded · not enough headroom now, device_capacity) — None if none
    boot_block: str | None = None


@dataclass(frozen=True)
class Decision:
    verdict: str
    device_key: str | None = None
    reasons: tuple[str, ...] = ()
    is_boot_needed: bool = False
    reclaimed_from: dict | None = None
    busy_owners: tuple[dict, ...] = field(default_factory=tuple)
    # ask is due to memory risk — can be passed with --user-approved after the user answers
    is_memory_risk: bool = False


@dataclass
class _Working:
    """Intermediate result the steps fill in together."""

    matching: list[Candidate] = field(default_factory=list)
    eligible: list[Candidate] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    # Why a temporary device cannot be created (resource limits) — if set, ask at the end
    create_block: str | None = None
    is_create_block_memory: bool = False


def _memory_block(request: AcquireRequest, context: PoolContext) -> str | None:
    """Memory reason not to boot a new one (critical > budget exceeded). None if the user approved."""
    if request.is_memory_risk_user_approved:
        return None
    if context.pressure == "critical":
        return "host memory is critical; the user must confirm before booting another device"
    return context.boot_block


def _owner_phrase(lease: dict) -> str:
    purpose = f", {lease['purpose']}" if lease.get("purpose") else ""
    return f"session {str(lease.get('session'))[:8]}{purpose}"


def _filter_matching(request: AcquireRequest, candidates: list[Candidate], working: _Working) -> Decision | None:
    """Condition filter (platform · device selector · form · OS)."""
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
    """Eligibility filter: drops human-started devices · devices this session already holds · powered-off devices that cannot boot (the first two stay when a device is specified)."""
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
    """Free device: powered on (no boot cost) > most recently used. reclaim if a dead ownership remains."""
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
    """Create a temporary device when none is free — not when a specific device or prepared state is required (creating would not help).

    3 resource limits: memory critical · low disk · memory budget (device_capacity). If one trips, record the reason and move on.
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
    """If a matching device is in use by someone else, wait until the wait limit, then ask. no_match if nothing at all · ask on resource limits."""
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
    """Pick one device matching the conditions > Decision (reasons always has at least one)."""
    working, chosen_context = _Working(), context or PoolContext()
    for step in DECISION_STEPS:
        decision = step(request, candidates, working, chosen_context)
        if decision is not None:
            return decision
    return Decision("no_match", reasons=("no decision step returned a result",))
