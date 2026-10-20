"""`device claim` — 이 세션이 특정 기기를 쥐었다고 알린다 (#925). 반납은 pool.run_release (#953).

공용 도우미: 기기 해석 · 남의 소유 거부 · 기록된 설정 되돌리기 명령 실행.
"""
from __future__ import annotations

import subprocess

from pro_launch.runtime import device_claims
from pro_launch.runtime.context import project_root
from pro_launch.runtime.devices import no_device_response, pick_device
from pro_launch.runtime.output import out
from pro_launch.runtime.session_identity import session_identity

# 되돌리기 명령 하나의 최대 대기 (초) — iOS 시뮬레이터 재부팅(bootstatus)이 들어 있다
RESTORE_COMMAND_TIMEOUT_SECONDS = 300


def resolve_device(args):
    """(플랫폼, 기기 id, 오류 응답). 이름 없는 booted 는 쥘 수 없다."""
    platform, dev_id, dev = pick_device(args.device)
    if not platform:
        return None, None, no_device_response(dev, args.device)
    if dev_id == "booted":
        return None, None, out({"ok": False, "code": "args_required", "error": "booted 는 어느 기기인지 정할 수 없다",
                                "next": "--device <UDID> 로 지정한다 (device list)"})
    return platform, dev_id, None


def refuse_other_session_owner(dev_id: str, action: str) -> int | None:
    """다른 살아 있는 세션이 쥔 기기에서 --yes 없이는 멈춘다. 통과면 None."""
    owner = device_claims.check_device_owner(dev_id)
    if owner is None:
        return None
    return out({"ok": False, "code": "device_owned_by_other", "action": action, "device": dev_id,
                "owner": owner, "error": owner["message"],
                "next": "사용자에게 먼저 묻는다. 그 세션의 작업을 끊어도 된다고 하면 --yes 를 붙여 다시 부른다"})


def run_restore_commands(setting: dict) -> dict:
    """기록된 되돌리기 명령을 차례로 실행 > {key, is_ok, failed_command, detail}. 하나가 실패하면 멈춘다."""
    for command in setting.get("restore_commands") or []:
        try:
            r = subprocess.run(command, capture_output=True, text=True, timeout=RESTORE_COMMAND_TIMEOUT_SECONDS)
        except (OSError, subprocess.SubprocessError) as error:
            return {"key": setting.get("key"), "is_ok": False, "failed_command": command, "detail": str(error)}
        if r.returncode != 0:
            return {"key": setting.get("key"), "is_ok": False, "failed_command": command,
                    "detail": ((r.stderr or "") + (r.stdout or "")).strip()[-300:]}
    return {"key": setting.get("key"), "is_ok": True, "failed_command": None, "detail": None}


def run_claim(args) -> int:
    platform, dev_id, err = resolve_device(args)
    if err is not None:
        return err
    if not args.yes and (refusal := refuse_other_session_owner(dev_id, "claim")) is not None:
        return refusal
    result = device_claims.claim_device(dev_id, str(project_root(args)))
    previous = result["previous_owner"]
    return out({"action": "claim", "platform": platform, "device": dev_id, **result,
                "summary": f"{dev_id} 를 이 세션({session_identity()})이 쥐었다 — 30분 안 쓰면 풀린다",
                "next": "작업이 끝나면 device release  # 바꾼 전역 설정(언어·외관)도 함께 되돌린다",
                "taken_over_from": previous["session"] if previous and previous["is_live"] else None})
