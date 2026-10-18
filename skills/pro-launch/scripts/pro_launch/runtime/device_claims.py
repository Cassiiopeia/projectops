"""기기 소유 기록: 어느 세션·프로젝트가 기기를 쥐었나 · 그 세션이 바꾼 기기 전역 설정 (#925).

한 맥의 에뮬레이터·시뮬레이터를 여러 세션이 함께 쓴다. 기록은 레포 버킷이 아니라 이 컴퓨터 공용 자리에 둔다
— 다른 레포의 세션도 같은 기기를 보기 때문이다.

파일: {base}/launch/_machine/device-claims.json
    {"schema": 1, "claims": {기기 id: {session, project_root, claimed_at, last_used, is_auto_claimed,
                                       settings: [{key, before, restore_commands, changed_at}]}}}

**막지 않고 알린다.** 다른 세션 소유 기기에 조작하면 `check_device_owner` 가 경고를 돌려줄 뿐이다.
되돌릴 수 없는 동작(device reboot)만 부르는 쪽이 --yes 를 요구한다.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from common.state import MACHINE_BUCKET, base_dir

from pro_launch.runtime.session_identity import session_identity

CLAIMS_FILE_NAME = "device-claims.json"
CLAIMS_SCHEMA = 1
# 마지막 사용 뒤 이만큼 쉬면 소유가 풀린 것으로 본다 (30분)
CLAIM_IDLE_EXPIRY_SECONDS = 30 * 60
# 이름만 있는 기기 지정 — 누가 쥐었는지 가를 수 없어 기록하지 않는다
UNNAMED_DEVICE_IDS = ("booted",)


def claims_path() -> Path:
    return base_dir() / "launch" / MACHINE_BUCKET / CLAIMS_FILE_NAME


def _load() -> dict:
    try:
        data = json.loads(claims_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    claims = data.get("claims") if isinstance(data, dict) else None
    return {k: v for k, v in (claims or {}).items() if isinstance(v, dict)}


def _save(claims: dict) -> None:
    """임시 파일 > 바꿔치기 (읽는 세션이 반쯤 쓴 파일을 보지 않게)."""
    path = claims_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps({"schema": CLAIMS_SCHEMA, "claims": claims}, ensure_ascii=False, indent=2)
                         + "\n", encoding="utf-8")
    os.replace(temporary, path)


def is_claim_live(claim: dict, now: float | None = None) -> bool:
    """마지막 사용이 유휴 한도 안이면 살아 있는 소유."""
    last_used = claim.get("last_used") or claim.get("claimed_at") or 0
    return ((now or time.time()) - float(last_used)) < CLAIM_IDLE_EXPIRY_SECONDS


def _is_recordable(dev_id: str | None) -> bool:
    return bool(dev_id) and dev_id not in UNNAMED_DEVICE_IDS


def _owner_view(dev_id: str, claim: dict, now: float) -> dict:
    """응답에 싣는 소유 요약 (설정 기록은 키 목록만)."""
    return {"device": dev_id, "session": claim.get("session"), "project_root": claim.get("project_root"),
            "claimed_at": claim.get("claimed_at"), "last_used": claim.get("last_used"),
            "idle_seconds": round(now - float(claim.get("last_used") or now)),
            "is_live": is_claim_live(claim, now), "is_auto_claimed": bool(claim.get("is_auto_claimed")),
            "changed_settings": [s.get("key") for s in claim.get("settings") or []]}


def device_owner(dev_id: str) -> dict | None:
    """그 기기의 소유 요약. 기록이 없으면 None (유휴로 풀린 것도 is_live=false 로 돌려준다)."""
    claim = _load().get(dev_id)
    return _owner_view(dev_id, claim, time.time()) if claim else None


def owners_by_device() -> dict[str, dict]:
    """살아 있는 소유만 > {기기 id: 소유 요약} (device list · devices 용)."""
    now = time.time()
    return {dev_id: _owner_view(dev_id, claim, now) for dev_id, claim in _load().items()
            if is_claim_live(claim, now)}


def check_device_owner(dev_id: str | None) -> dict | None:
    """다른 살아 있는 세션이 쥔 기기면 경고 dict, 아니면 None.

    부르는 쪽: `payload.update(owner_warning_fields(dev_id))` 또는 이 값을 직접 `device_owned_by_other` 키에 싣는다.
    """
    if not _is_recordable(dev_id):
        return None
    claim = _load().get(dev_id)
    if not claim or not is_claim_live(claim) or claim.get("session") == session_identity():
        return None
    view = _owner_view(dev_id, claim, time.time())
    return {"code": "device_owned_by_other", **view,
            "message": (f"다른 세션({view['session']}, {view['project_root']})이 쓰는 기기다 "
                        f"({view['idle_seconds']}초 전 사용)"),
            "next": "그 세션의 작업을 덮을 수 있다 — 사용자에게 묻거나 다른 기기를 쓴다 (device list 로 소유자 확인)"}


def owner_warning_fields(dev_id: str | None) -> dict:
    """조작 응답에 붙일 경고 필드 — 없으면 빈 dict."""
    warning = check_device_owner(dev_id)
    return {"device_owned_by_other": warning} if warning else {}


def claim_device(dev_id: str, project_root: str | None, is_auto_claimed: bool = False) -> dict:
    """이 세션이 쥔다. 풀린(유휴) 소유의 설정 기록은 이어받는다 — 되돌릴 값을 잃지 않게.

    다른 살아 있는 세션 소유를 넘겨받는지는 부르는 쪽이 check_device_owner 로 먼저 가른다.
    """
    claims = _load()
    previous = claims.get(dev_id) or {}
    now = time.time()
    is_same_session = previous.get("session") == session_identity()
    claims[dev_id] = {
        "session": session_identity(), "project_root": project_root,
        "claimed_at": previous.get("claimed_at") if is_same_session else now,
        "last_used": now,
        # 명시 claim 이 한 번이라도 있으면 자동 소유가 아니다
        "is_auto_claimed": is_auto_claimed and not (is_same_session and previous.get("is_auto_claimed") is False),
        "settings": list(previous.get("settings") or []),
    }
    _save(claims)
    return {"owner": _owner_view(dev_id, claims[dev_id], now),
            "previous_owner": (_owner_view(dev_id, previous, now) if previous and not is_same_session else None)}


def touch_device(dev_id: str | None, project_root: str | None) -> None:
    """조작한 기기의 마지막 사용 갱신. 주인이 없거나 풀렸으면 이 세션이 자동으로 쥔다. 남의 살아 있는 소유는 건드리지 않는다."""
    if not _is_recordable(dev_id) or check_device_owner(dev_id):
        return
    try:
        claim_device(dev_id, project_root, is_auto_claimed=True)
    except OSError:
        pass   # 기록 실패가 조작 결과를 바꾸지 않는다


def release_device(dev_id: str) -> dict | None:
    """소유 기록을 지우고 되돌릴 설정 목록(나중에 바꾼 것부터)을 돌려준다. 기록이 없으면 None."""
    claims = _load()
    claim = claims.pop(dev_id, None)
    if claim is None:
        return None
    _save(claims)
    return {"owner": _owner_view(dev_id, claim, time.time()),
            "settings": list(reversed(claim.get("settings") or []))}


def record_device_setting(dev_id: str, key: str, before, restore_commands: list[list[str]],
                          project_root: str | None = None) -> None:
    """기기 전역 설정을 바꾸기 전 값 기록 (같은 키는 처음 값만 — 중간 값으로 덮으면 원래로 못 돌아간다).

    key 예: `appearance` · `locale:system` · `locale:app:<패키지>` · `ime`.
    restore_commands: 되돌리는 명령 argv 목록 (순서대로 실행). device release · --restore 가 쓴다.
    """
    if not _is_recordable(dev_id):
        return
    claims = _load()
    if dev_id not in claims or not is_claim_live(claims[dev_id]) or claims[dev_id].get("session") != session_identity():
        claim_device(dev_id, project_root, is_auto_claimed=True)
        claims = _load()
    settings = claims[dev_id].setdefault("settings", [])
    if any(s.get("key") == key for s in settings):
        return
    settings.append({"key": key, "before": before, "restore_commands": restore_commands,
                     "changed_at": time.time()})
    _save(claims)


def pop_device_setting(dev_id: str, key: str) -> dict | None:
    """기록한 설정 하나를 꺼낸다 (--restore). 어느 세션이 기록했든 기기 기준으로 찾는다."""
    claims = _load()
    claim = claims.get(dev_id)
    if not claim:
        return None
    settings = claim.get("settings") or []
    found = next((s for s in settings if s.get("key") == key), None)
    if found is None:
        return None
    claim["settings"] = [s for s in settings if s is not found]
    _save(claims)
    return found
