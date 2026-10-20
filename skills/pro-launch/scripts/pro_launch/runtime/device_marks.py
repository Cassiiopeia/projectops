"""기기의 공들인 상태(mark) · 출처 · 임시 기기 기록 (#954).

mark: 기기 밖에서 읽을 수 없는 상태 — 로그인 · 테스트 데이터 · 권한 · 설정. kind·name 은 자유 문자열(공급자 목록을 박지 않는다).
mark 가 하나라도 있는 기기는 보호된다: 자동 정리에서 빠지고 초기화·삭제는 --yes 로만.
출처(origin): recorded(create 로 만든 것) · adopted(기존 기기를 원장에 올린 것). 없으면 unrecorded.
"""
from __future__ import annotations

import time

from common import config as common_config

from pro_launch.runtime import device_ledger
from pro_launch.runtime.device_claims import resolve_instance_key
from pro_launch.runtime.session_identity import session_identity

# 권장 kind (강제하지 않는다 — 문서·도움말용)
RECOMMENDED_MARK_KINDS = ("login", "data", "permission", "config", "other")
# mark 확인 주기 기본값 (일) — 넘으면 stale 로 표시 (launch.devices.mark_stale_days)
MARK_STALE_DAYS_DEFAULT = 14
# 임시 기기 기본 보관 (일) — launch.devices.temporary_ttl_days
TEMPORARY_TTL_DAYS_DEFAULT = 3
ORIGIN_RECORDED = "recorded"
ORIGIN_ADOPTED = "adopted"
SECONDS_PER_DAY = 24 * 60 * 60


def _config_days(key: str, default: int) -> float:
    value = ((common_config.get_section("launch") or {}).get("devices") or {}).get(key)
    return float(value) if isinstance(value, (int, float)) and value > 0 else float(default)


def mark_stale_seconds() -> float:
    return _config_days("mark_stale_days", MARK_STALE_DAYS_DEFAULT) * SECONDS_PER_DAY


def temporary_ttl_days() -> float:
    return _config_days("temp_ttl_days", TEMPORARY_TTL_DAYS_DEFAULT)


def mark_label(mark: dict) -> str:
    """kind:name (acquire --need 와 같은 모양)."""
    return f"{mark.get('kind')}:{mark.get('name')}"


def mark_views(entry: dict, now: float | None = None) -> list[dict]:
    """응답용 mark 목록 (is_stale 포함)."""
    current = now or time.time()
    limit = mark_stale_seconds()
    return [{**mark, "label": mark_label(mark),
             "is_stale": current - float(mark.get("verified_at") or mark.get("recorded_at") or 0) > limit}
            for mark in entry.get("marks") or []]


def is_protected(entry: dict) -> bool:
    return bool(entry.get("marks"))


def entry_of(dev_id: str) -> tuple[str, dict]:
    key = resolve_instance_key(dev_id)
    return key, device_ledger.read_ledger()["devices"].get(key) or {}


def _entry(ledger: dict, key: str) -> dict:
    return ledger["devices"].setdefault(key, {"leases": [], "settings": []})


def add_mark(dev_id: str, kind: str, name: str, note: str | None = None) -> dict:
    """mark 기록 (같은 kind·name 은 갱신 — 처음 기록 시각 유지). 출처가 없으면 adopted 로 올린다."""
    key, now = resolve_instance_key(dev_id), time.time()

    def mutate(ledger: dict) -> dict:
        entry = _entry(ledger, key)
        entry.setdefault("origin", ORIGIN_ADOPTED)
        marks = entry.setdefault("marks", [])
        found = next((m for m in marks if m.get("kind") == kind and m.get("name") == name), None)
        if found is None:
            found = {"kind": kind, "name": name, "recorded_at": now}
            marks.append(found)
        found.update({"note": note or found.get("note"), "recorded_by_session": session_identity(), "verified_at": now})
        # 공들인 상태가 생기면 더 이상 새 폰이 아니다
        entry.pop("is_pristine", None)
        return dict(found)

    return device_ledger.update_ledger(mutate)


def remove_mark(dev_id: str, kind: str, name: str) -> bool:
    key = resolve_instance_key(dev_id)

    def mutate(ledger: dict) -> bool:
        entry = ledger["devices"].get(key) or {}
        before = len(entry.get("marks") or [])
        entry["marks"] = [m for m in entry.get("marks") or [] if not (m.get("kind") == kind and m.get("name") == name)]
        return len(entry["marks"]) < before

    return device_ledger.update_ledger(mutate)


def verify_mark(dev_id: str, kind: str, name: str) -> dict | None:
    """mark 가 아직 살아 있음을 확인했다 — verified_at 갱신. 없으면 None."""
    key, now = resolve_instance_key(dev_id), time.time()

    def mutate(ledger: dict) -> dict | None:
        entry = ledger["devices"].get(key) or {}
        found = next((m for m in entry.get("marks") or [] if m.get("kind") == kind and m.get("name") == name), None)
        if found is not None:
            found["verified_at"] = now
        return dict(found) if found else None

    return device_ledger.update_ledger(mutate)


def adopt_device(dev_id: str) -> str:
    """원장에 없는 기기를 올린다 > 출처 (이미 있으면 그대로)."""
    key = resolve_instance_key(dev_id)
    return device_ledger.update_ledger(lambda ledger: _entry(ledger, key).setdefault("origin", ORIGIN_ADOPTED))


def record_created(key: str, reason: str, ttl_days: float, backend: str) -> dict:
    """create 로 만든 임시 기기 기록 > temporary 기록. 새로 만든 기기는 pristine(아무도 쓰지 않은 새 폰)."""
    now = time.time()
    temporary = {"reason": reason, "created_by_session": session_identity(), "created_at": now,
                 "expires_at": now + ttl_days * SECONDS_PER_DAY, "backend": backend}

    def mutate(ledger: dict) -> dict:
        entry = _entry(ledger, key)
        entry.update({"origin": ORIGIN_RECORDED, "temporary": temporary, "is_pristine": True})
        return temporary

    return device_ledger.update_ledger(mutate)


def clear_pristine(key: str) -> None:
    device_ledger.update_ledger(lambda ledger: (ledger["devices"].get(key) or {}).pop("is_pristine", None))


def reset_after_erase(key: str) -> None:
    """초기화한 기기: 공들인 상태 · 설정 기록이 사라졌다 > mark · 설정 기록을 지우고 새 폰으로 표시."""
    def mutate(ledger: dict) -> None:
        entry = _entry(ledger, key)
        entry["marks"], entry["settings"], entry["is_pristine"] = [], [], True

    device_ledger.update_ledger(mutate)


def forget_device(key: str) -> None:
    """삭제한 기기 항목을 원장에서 지운다."""
    device_ledger.update_ledger(lambda ledger: ledger["devices"].pop(key, None))


def record_views() -> dict[str, dict]:
    """원장 전체 요약 > {키: {origin, marks, temporary, is_pristine, lease_count}} (device records 용)."""
    now = time.time()
    return {key: {"origin": entry.get("origin"), "marks": mark_views(entry, now), "temporary": entry.get("temporary"),
                  "is_temporary_expired": bool(entry.get("temporary")) and now > float(entry["temporary"].get("expires_at") or 0),
                  "is_pristine": bool(entry.get("is_pristine")), "lease_count": len(entry.get("leases") or [])}
            for key, entry in device_ledger.read_ledger()["devices"].items()}
