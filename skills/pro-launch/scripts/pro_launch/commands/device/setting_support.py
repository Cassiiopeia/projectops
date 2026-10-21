"""device 설정 명령(locale · appearance · text-size) 공통 도우미: 명령 실행, 실패 응답, 원래 값 기록·복원."""
from __future__ import annotations

import subprocess

from pro_launch.commands.device.claims import run_restore_commands
from pro_launch.runtime.context import project_root
from pro_launch.runtime.device_claims import pop_device_setting, record_device_setting
from pro_launch.runtime.output import out

COMMAND_TIMEOUT_SECONDS = 60


def run_command(command: list[str]) -> tuple[bool, str]:
    try:
        r = subprocess.run(command, capture_output=True, text=True, timeout=COMMAND_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        return False, f"No response ({COMMAND_TIMEOUT_SECONDS}s)"
    except OSError as error:
        return False, str(error)
    return r.returncode == 0, ((r.stdout or "") + (r.stderr or "")).replace("\r", "").strip()


def fail(code: str, error: str, next_hint: str | None = None, **extra) -> int:
    return out({"ok": False, "code": code, "error": error, "next": next_hint, **extra})


def record_change(key: str, dev_id: str, before, restore_commands: list[list[str]], args) -> None:
    record_device_setting(dev_id, key, before, restore_commands, str(project_root(args)))


def restore_recorded(dev_id: str, platform: str, key: str, action: str) -> int:
    """--restore: 기록한 원래 값으로 되돌린다."""
    setting = pop_device_setting(dev_id, key)
    if setting is None:
        return out({"action": action, "platform": platform, "device": dev_id, "restored": False,
                    "summary": f"Nothing recorded to restore ({key})", "next": None})
    result = run_restore_commands(setting)
    return out({"ok": result["is_ok"], "code": "ok" if result["is_ok"] else "restore_failed", "action": action,
                "platform": platform, "device": dev_id, "restored": result["is_ok"], "key": key,
                "before": setting.get("before"), "error": result["detail"],
                "summary": f"{key} restored to its original value" if result["is_ok"] else f"{key} could not be restored",
                "next": None if result["is_ok"] else f"Run it yourself: {result['failed_command']}"})
