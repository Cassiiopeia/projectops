"""기기 소유(lease): 어느 세션이 기기를 쥐었나 · 그 세션이 바꾼 기기 전역 설정 (#925 · #953).

한 맥의 에뮬레이터·시뮬레이터를 여러 세션이 함께 쓴다. 기록은 이 컴퓨터 공용 원장(`device_ledger`) 한 곳.
소유 주인 = lease (session, 호스트 pid). 호스트가 죽으면 즉시, 살아 있어도 유휴 한도를 넘으면 풀린다.

**막지 않고 알린다(이 모듈).** 거부 여부는 부르는 쪽(디스패처 게이트 · device 명령)이 정한다.
"""
from __future__ import annotations

import time
import uuid

from common import config as common_config

from pro_launch.runtime import agent_hosts, device_ledger
from pro_launch.runtime.session_identity import ANONYMOUS_SESSION, session_identity

# 마지막 사용 뒤 이만큼 쉬면 소유가 풀린 것으로 본다 (30분, launch.devices.lease_idle_minutes 로 덮어쓴다)
CLAIM_IDLE_EXPIRY_SECONDS = 30 * 60
# 이름만 있는 기기 지정 — 누가 쥐었는지 가를 수 없어 기록하지 않는다
UNNAMED_DEVICE_IDS = ("booted",)

# 프로세스 안 캐시: 실행 중 id > 원장 키 · 이 프로세스의 agent 호스트
_KEY_BY_INSTANCE: dict[str, str] = {}
_CURRENT_HOST: dict = {}


def claims_path():
    return device_ledger.ledger_path()


def lease_idle_seconds() -> float:
    """유휴 한도 (초): 설정 launch.devices.lease_idle_minutes > 기본 30분."""
    devices_config = ((common_config.get_section("launch") or {}).get("devices") or {})
    minutes = devices_config.get("lease_idle_minutes")
    return float(minutes) * 60 if isinstance(minutes, (int, float)) and minutes > 0 else CLAIM_IDLE_EXPIRY_SECONDS


def resolve_instance_key(dev_id: str) -> str:
    """실행 중 id > 원장 키. Android 에뮬레이터 시리얼 > AVD 이름 (못 읽으면 시리얼 그대로), 그 외는 그대로."""
    if not dev_id.startswith("emulator-"):
        return dev_id
    if dev_id not in _KEY_BY_INSTANCE:
        from pro_launch.runtime import device_boot
        _KEY_BY_INSTANCE[dev_id] = device_boot.emulator_avd_name(dev_id) or dev_id
    return _KEY_BY_INSTANCE[dev_id]


def current_host() -> dict | None:
    if "value" not in _CURRENT_HOST:
        _CURRENT_HOST["value"] = agent_hosts.find_agent_host()
    return _CURRENT_HOST["value"]


def owner_identity_strength() -> str:
    """strong: 세션 id 또는 호스트 pid 로 가를 수 있다 · weak: 둘 다 없어 모든 세션이 같아 보인다."""
    return "weak" if session_identity() == ANONYMOUS_SESSION and not current_host() else "strong"


class _HostProbe:
    """여러 lease 의 호스트 생존 — pid 마다 한 번만 묻는다 (ps 전체 목록은 0.2~0.5초라 쓰지 않는다)."""

    def __init__(self):
        self._alive_by_pid: dict[int, bool | None] = {}

    def is_alive(self, host: dict | None) -> bool | None:
        if not host or not host.get("pid"):
            return None
        pid = host["pid"]
        if pid not in self._alive_by_pid:
            self._alive_by_pid[pid] = agent_hosts.is_host_alive(host)
        return self._alive_by_pid[pid]


def is_lease_live(lease: dict, now: float | None = None, probe: _HostProbe | None = None) -> bool:
    """호스트가 죽었으면 False, 아니면 마지막 사용이 유휴 한도 안일 때만 True."""
    if (probe or _HostProbe()).is_alive(lease.get("host")) is False:
        return False
    last_used = lease.get("last_used") or lease.get("acquired_at") or 0
    return ((now or time.time()) - float(last_used)) < lease_idle_seconds()


def is_own_lease(lease: dict) -> bool:
    """이 세션의 lease 인가. 세션 id 가 anonymous 면 호스트 pid 까지 같아야 한다."""
    if lease.get("session") != session_identity():
        return False
    if session_identity() != ANONYMOUS_SESSION:
        return True
    host, mine = lease.get("host") or {}, current_host() or {}
    return host.get("pid") == mine.get("pid")


def _is_recordable(dev_id: str | None) -> bool:
    return bool(dev_id) and dev_id not in UNNAMED_DEVICE_IDS


def lease_view(key: str, lease: dict, entry: dict, now: float, probe: _HostProbe) -> dict:
    """응답에 싣는 소유 요약 (설정 기록은 그 세션 것의 키 목록만)."""
    return {"device": lease.get("instance") or key, "key": key, "lease_id": lease.get("lease_id"),
            "session": lease.get("session"), "project_root": lease.get("project_root"),
            "purpose": lease.get("purpose"), "claimed_at": lease.get("acquired_at"),
            "last_used": lease.get("last_used"),
            "idle_seconds": round(now - float(lease.get("last_used") or now)),
            "is_live": is_lease_live(lease, now, probe), "host_alive": probe.is_alive(lease.get("host")),
            "booted_by_lease": bool(lease.get("booted_by_lease")),
            "is_auto_claimed": bool(lease.get("is_auto_claimed")),
            "changed_settings": [s.get("key") for s in entry.get("settings") or []
                                 if s.get("session") == lease.get("session")]}


def _entry_of(ledger: dict, dev_id: str) -> tuple[str, dict]:
    key = resolve_instance_key(dev_id)
    return key, ledger["devices"].get(key) or {"leases": [], "settings": []}


def device_owner(dev_id: str) -> dict | None:
    """그 기기의 소유 요약 (살아 있는 남의 것 > 살아 있는 내 것 > 가장 최근). 기록이 없으면 None."""
    key, entry = _entry_of(device_ledger.read_ledger(), dev_id)
    if not entry["leases"]:
        return None
    now, probe = time.time(), _HostProbe()
    views = [lease_view(key, lease, entry, now, probe) for lease in entry["leases"]]
    owned = [is_own_lease(lease) for lease in entry["leases"]]
    ranked = sorted(zip(views, owned), key=lambda pair: (pair[0]["is_live"], not pair[1], pair[0]["last_used"] or 0),
                    reverse=True)
    return ranked[0][0]


def owners_by_device() -> dict[str, dict]:
    """살아 있는 소유만 > {실행 중 id 와 원장 키: 소유 요약} (device list · devices 용)."""
    ledger, now, probe = device_ledger.read_ledger(), time.time(), _HostProbe()
    owners: dict[str, dict] = {}
    for key, entry in ledger["devices"].items():
        for lease in entry["leases"]:
            view = lease_view(key, lease, entry, now, probe)
            if view["is_live"]:
                owners.setdefault(view["device"], view)
                owners.setdefault(key, view)
    return owners


def check_device_owner(dev_id: str | None) -> dict | None:
    """다른 살아 있는 lease 가 쥔 기기면 경고 dict, 아니면 None."""
    if not _is_recordable(dev_id):
        return None
    key, entry = _entry_of(device_ledger.read_ledger(), dev_id)
    now, probe = time.time(), _HostProbe()
    for lease in entry["leases"]:
        if is_own_lease(lease) or not is_lease_live(lease, now, probe):
            continue
        view = lease_view(key, lease, entry, now, probe)
        purpose = f", {view['purpose']}" if view["purpose"] else ""
        return {"code": "device_owned_by_other", **view,
                "message": (f"다른 세션({view['session']}, {view['project_root']}{purpose})이 쓰는 기기다 "
                            f"({view['idle_seconds']}초 전 사용)"),
                "next": "그 세션의 작업을 덮을 수 있다 — 사용자에게 묻거나 다른 기기를 쓴다 (device list 로 소유자 확인)"}
    return None


def owner_warning_fields(dev_id: str | None) -> dict:
    """조작 응답에 붙일 경고 필드 — 없으면 빈 dict."""
    warning = check_device_owner(dev_id)
    return {"device_owned_by_other": warning} if warning else {}


def _new_lease(instance: str, project_root: str | None, purpose: str | None, booted_by_lease: bool,
               is_auto_claimed: bool, backend: str | None, now: float) -> dict:
    return {"lease_id": uuid.uuid4().hex[:12], "session": session_identity(), "host": current_host(),
            "project_root": project_root, "purpose": purpose, "instance": instance, "backend": backend,
            "acquired_at": now, "last_used": now, "booted_by_lease": booted_by_lease,
            "is_auto_claimed": is_auto_claimed}


def claim_device(dev_id: str, project_root: str | None, is_auto_claimed: bool = False,
                 purpose: str | None = None, booted_by_lease: bool = False, backend: str | None = None,
                 is_free_required: bool = False) -> dict | None:
    """이 세션이 쥔다 > {owner, previous_owner, lease}. 같은 실행 인스턴스의 남의 lease 는 넘겨받는다.

    넘겨받은 lease 의 설정 기록은 이 세션 것으로 잇는다 — 되돌릴 값을 잃지 않게.
    is_free_required: 잠금 안에서 살아 있는 남의 lease 를 다시 보고, 있으면 쥐지 않고 None (동시 acquire 경합).
    그 외에는 살아 있는 남의 소유를 넘겨받아도 되는지 부르는 쪽이 check_device_owner 로 먼저 가른다.
    """
    now = time.time()
    key = resolve_instance_key(dev_id)

    def mutate(ledger: dict) -> dict | None:
        entry = ledger["devices"].setdefault(key, {"leases": [], "settings": []})
        probe = _HostProbe()
        same_instance = [lease for lease in entry["leases"] if (lease.get("instance") or key) == dev_id]
        own = next((lease for lease in same_instance if is_own_lease(lease)), None)
        others = [lease for lease in same_instance if lease is not own]
        if is_free_required and any(is_lease_live(lease, now, probe) for lease in others):
            return None
        previous = max(others, key=lambda lease: lease.get("last_used") or 0) if others else None
        previous_view = lease_view(key, previous, entry, now, probe) if previous else None
        for lease in others:
            entry["leases"].remove(lease)
            for setting in entry["settings"]:
                if setting.get("session") == lease.get("session"):
                    setting["session"] = session_identity()
        if own is None:
            own = _new_lease(dev_id, project_root, purpose, booted_by_lease, is_auto_claimed, backend, now)
            entry["leases"].append(own)
        else:
            own["last_used"] = now
            own["backend"] = backend or own.get("backend")
            own["project_root"] = project_root or own.get("project_root")
            own["purpose"] = purpose or own.get("purpose")
            own["booted_by_lease"] = bool(own.get("booted_by_lease") or booted_by_lease)
            # 명시 claim 이 한 번이라도 있으면 자동 소유가 아니다
            own["is_auto_claimed"] = bool(own.get("is_auto_claimed")) and is_auto_claimed
        return {"owner": lease_view(key, own, entry, now, probe), "previous_owner": previous_view, "lease": dict(own)}

    return device_ledger.update_ledger(mutate)


def touch_device(dev_id: str | None, project_root: str | None) -> None:
    """조작한 기기의 마지막 사용 갱신. 주인이 없거나 풀렸으면 이 세션이 자동으로 쥔다. 남의 살아 있는 소유는 건드리지 않는다."""
    if not _is_recordable(dev_id) or check_device_owner(dev_id):
        return
    try:
        claim_device(dev_id, project_root, is_auto_claimed=True)
    except (OSError, device_ledger.LedgerBusyError):
        pass   # 기록 실패가 조작 결과를 바꾸지 않는다


def release_device(dev_id: str, lease_id: str | None = None) -> dict | None:
    """lease 를 지우고 되돌릴 설정(그 세션 것, 나중에 바꾼 것부터)을 꺼낸다. 기록이 없으면 None.

    고르는 lease: lease_id > 이 세션 것 > 가장 최근. 응답의 remaining_live_leases 로 끌지 판단한다.
    """
    def mutate(ledger: dict) -> dict | None:
        key, _ = _entry_of(ledger, dev_id)
        entry = ledger["devices"].get(key)
        if not entry or not entry["leases"]:
            return None
        leases = entry["leases"]
        chosen = (next((lease for lease in leases if lease.get("lease_id") == lease_id), None) if lease_id
                  else next((lease for lease in leases if is_own_lease(lease)), None)
                  or max(leases, key=lambda lease: lease.get("last_used") or 0))
        if chosen is None:
            return None
        now, probe = time.time(), _HostProbe()
        view = lease_view(key, chosen, entry, now, probe)
        leases.remove(chosen)
        settings = [s for s in entry["settings"] if s.get("session") == chosen.get("session")]
        entry["settings"] = [s for s in entry["settings"] if s not in settings]
        remaining = sum(1 for lease in leases if is_lease_live(lease, now, probe))
        return {"owner": view, "lease": chosen, "settings": list(reversed(settings)),
                "remaining_live_leases": remaining}

    return device_ledger.update_ledger(mutate)


def leases_of_session(session: str) -> list[tuple[str, dict]]:
    """그 세션의 모든 lease > [(원장 키, lease)] (세션 종료 반납용)."""
    ledger = device_ledger.read_ledger()
    return [(key, lease) for key, entry in ledger["devices"].items() for lease in entry["leases"]
            if lease.get("session") == session]


def record_device_setting(dev_id: str, key: str, before, restore_commands: list[list[str]],
                          project_root: str | None = None) -> None:
    """기기 전역 설정을 바꾸기 전 값 기록 (같은 키는 처음 값만 — 중간 값으로 덮으면 원래로 못 돌아간다).

    key 예: `appearance` · `locale:system` · `locale:app:<패키지>` · `ime`.
    restore_commands: 되돌리는 명령 argv 목록 (순서대로 실행). device release · --restore 가 쓴다.
    """
    if not _is_recordable(dev_id):
        return
    touch_device(dev_id, project_root)
    device_key = resolve_instance_key(dev_id)

    def mutate(ledger: dict) -> None:
        entry = ledger["devices"].setdefault(device_key, {"leases": [], "settings": []})
        if any(s.get("key") == key for s in entry["settings"]):
            return
        entry["settings"].append({"key": key, "before": before, "restore_commands": restore_commands,
                                  "changed_at": time.time(), "session": session_identity()})

    device_ledger.update_ledger(mutate)


def pop_device_setting(dev_id: str, key: str) -> dict | None:
    """기록한 설정 하나를 꺼낸다 (--restore). 어느 세션이 기록했든 기기 기준으로 찾는다."""
    def mutate(ledger: dict) -> dict | None:
        device_key, _ = _entry_of(ledger, dev_id)
        entry = ledger["devices"].get(device_key)
        if not entry:
            return None
        found = next((s for s in entry["settings"] if s.get("key") == key), None)
        if found is not None:
            entry["settings"].remove(found)
        return found

    return device_ledger.update_ledger(mutate)


def set_pool_booted(dev_id: str, is_booted: bool) -> None:
    """acquire 가 켠 기기 표시 (켜져 있어도 사람이 쓰는 기기로 보지 않게) · 끄면 지운다."""
    key = resolve_instance_key(dev_id)

    def mutate(ledger: dict) -> None:
        entry = ledger["devices"].setdefault(key, {"leases": [], "settings": []})
        if is_booted:
            entry["pool_booted_at"] = time.time()
        else:
            entry.pop("pool_booted_at", None)

    device_ledger.update_ledger(mutate)


def record_wait(wait_key: str) -> float:
    """대기 기록 갱신 > 처음 기다리기 시작한 뒤 지난 초 (여러 호출을 합친 대기)."""
    now = time.time()

    def mutate(ledger: dict) -> float:
        record = ledger["waits"].setdefault(wait_key, {"started_at": now})
        record["updated_at"] = now
        return now - float(record["started_at"])

    return device_ledger.update_ledger(mutate)


def waited_seconds(wait_key: str) -> float:
    record = device_ledger.read_ledger()["waits"].get(wait_key)
    return time.time() - float(record["started_at"]) if record else 0.0


def clear_wait(wait_key: str) -> None:
    device_ledger.update_ledger(lambda ledger: ledger["waits"].pop(wait_key, None))


def pop_settings_of_session(dev_id: str, session: str) -> list[dict]:
    """그 세션이 기록한 설정을 꺼낸다 (나중에 바꾼 것부터) — reclaim 때 넘겨받기 전에 되돌린다."""
    key = resolve_instance_key(dev_id)

    def mutate(ledger: dict) -> list[dict]:
        entry = ledger["devices"].get(key)
        if not entry:
            return []
        taken = [s for s in entry["settings"] if s.get("session") == session]
        entry["settings"] = [s for s in entry["settings"] if s not in taken]
        return list(reversed(taken))

    return device_ledger.update_ledger(mutate)


def keep_settings_for_this_session(dev_id: str, settings: list[dict]) -> None:
    """되돌리지 못한 설정을 이 세션 기록으로 다시 넣는다 (다음 release 가 다시 시도)."""
    key = resolve_instance_key(dev_id)

    def mutate(ledger: dict) -> None:
        entry = ledger["devices"].setdefault(key, {"leases": [], "settings": []})
        entry["settings"].extend({**s, "session": session_identity()} for s in settings)

    device_ledger.update_ledger(mutate)
