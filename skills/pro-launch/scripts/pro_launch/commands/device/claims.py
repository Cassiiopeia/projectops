"""`device claim` — announce that this session holds a specific device (#925). Release is pool.run_release (#953).

Shared helpers: resolve device, refuse others' ownership, run recorded setting-revert commands.
"""
from __future__ import annotations

import subprocess

from pro_launch.runtime import device_claims
from pro_launch.runtime.context import project_root
from pro_launch.runtime.devices import no_device_response, pick_device
from pro_launch.runtime.output import out
from pro_launch.runtime.session_identity import session_identity

# Max wait (s) for one revert command — includes an iOS simulator reboot (bootstatus)
RESTORE_COMMAND_TIMEOUT_SECONDS = 300


def resolve_device(args):
    """(platform, device id, error response). An unnamed booted cannot be held."""
    platform, dev_id, dev = pick_device(args.device)
    if not platform:
        return None, None, no_device_response(dev, args.device)
    if dev_id == "booted":
        return None, None, out({"ok": False, "code": "args_required", "error": "booted does not identify a specific device",
                                "next": "Specify it with --device <UDID> (device list)"})
    return platform, dev_id, None


def refuse_other_session_owner(dev_id: str, action: str) -> int | None:
    """Stops without --yes on devices held by another live session. None if allowed."""
    owner = device_claims.check_device_owner(dev_id)
    if owner is None:
        return None
    return out({"ok": False, "code": "device_owned_by_other", "action": action, "device": dev_id,
                "owner": owner, "error": owner["message"],
                "next": "Ask the user first. If they agree to interrupt that session's work, call again with --yes"})


def run_restore_commands(setting: dict) -> dict:
    """Run recorded revert commands in order > {key, is_ok, failed_command, detail}. Stops at the first failure."""
    for command in setting.get("restore_commands") or []:
        try:
            r = subprocess.run(command, capture_output=True, text=True, errors="replace", timeout=RESTORE_COMMAND_TIMEOUT_SECONDS)
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
                "summary": f"This session ({session_identity()}) claimed {dev_id} — released after 30 minutes unused",
                "next": "When done, device release  # also restores changed global settings (language · appearance)",
                "taken_over_from": previous["session"] if previous and previous["is_live"] else None})
