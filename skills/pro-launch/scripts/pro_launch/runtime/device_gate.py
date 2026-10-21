"""기기 소유 게이트: 동작 선언(device_use)을 보고 남의 기기 조작을 거부·경고하고 이 세션의 사용을 기록한다 (#953).

app · device 디스패처가 동작을 실행하기 **전에** 한 번 부른다. 동작 파일은 소유 코드를 갖지 않는다.
"""
from __future__ import annotations

from pro_launch.runtime import device_claims
from pro_launch.runtime.devices import pick_device
from pro_launch.runtime.output import add_response_fields, out


def gate_device_use(device_use: str | None, want_device: str | None, project_root: str,
                    is_forced: bool) -> int | None:
    """mutate: 남의 살아 있는 소유면 거부 응답(종료 코드) · read: 경고 필드만 · 통과면 None.

    기기를 정할 수 없으면 통과시킨다 — 동작이 원래 오류(no_device 등)를 낸다.
    """
    if device_use in (None, "none"):
        return None
    _, dev_id, _ = pick_device(want_device)
    if not dev_id:
        return None
    owner = device_claims.check_device_owner(dev_id)
    if owner is None:
        device_claims.touch_device(dev_id, project_root)
        return None
    if device_use == "mutate" and not is_forced:
        return out({"ok": False, "code": "device_owned_by_other", "device": dev_id, "owner": owner,
                    "error": owner["message"],
                    "next": "Borrow another device with device acquire. If you must use this one, ask the user and add --yes"})
    add_response_fields({"device_owned_by_other": owner})
    return None
