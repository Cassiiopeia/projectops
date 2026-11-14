"""Device ownership gate: reads the action declaration (device_use) to refuse·warn on acting on someone else's device and records this session's use (#953).

The app · device dispatchers call it once **before** running an action. Action files hold no ownership code.
"""
from __future__ import annotations

from pro_launch.runtime import device_claims
from pro_launch.runtime.devices import pick_device
from pro_launch.runtime.output import add_response_fields, out


def gate_device_use(device_use: str | None, want_device: str | None, project_root: str,
                    is_forced: bool) -> int | None:
    """mutate: refusal response (exit code) if someone else's live ownership · read: warning field only · None if it passes.

    Passes if the device cannot be determined — the action raises its own error (no_device, etc.).
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
