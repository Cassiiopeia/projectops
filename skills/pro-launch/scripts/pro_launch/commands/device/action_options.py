"""Options each device action accepts — options an action does not use are sent back as bad_args, not silently ignored (#972).

device actions share one option set (no subparsers) — argparse alone cannot catch per-action ignoring.
This table is the source of truth for options each action actually reads — when an action reads a new option, add it here too.
"""
from __future__ import annotations

# Options every action accepts (dest names)
COMMON_OPTIONS = frozenset({"root"})
# Display name of the positional argument mode
MODE_LABEL = "<mode>"

_DEVICE_TARGET = ("device",)
# Action > options it reads (dest names, mode is positional)
OPTIONS_BY_ACTION: dict[str, frozenset[str]] = {
    "list": frozenset({"package", "run_dir"}),
    "bind": frozenset({"role", "serial", "note", "package", "run_dir"}),
    "unbind": frozenset({"role", "package", "run_dir"}),
    "show": frozenset({"package", *_DEVICE_TARGET}),
    "claim": frozenset({*_DEVICE_TARGET, "yes"}),
    "acquire": frozenset({*_DEVICE_TARGET, "platform", "form", "os", "purpose", "reason", "wait", "need", "fresh",
                          "count", "name", "window", "scale", "user_approved"}),
    "release": frozenset({*_DEVICE_TARGET, "lease", "all", "keep_booted", "yes"}),
    "shutdown": frozenset({*_DEVICE_TARGET, "yes"}),
    "create": frozenset({"platform", "reason", "purpose", "name", "form", "os", "ttl_days", "yes"}),
    "clone": frozenset({*_DEVICE_TARGET, "platform", "reason", "purpose", "name", "ttl_days", "yes"}),
    "erase": frozenset({*_DEVICE_TARGET, "platform", "yes"}),
    "delete": frozenset({*_DEVICE_TARGET, "platform", "yes"}),
    "mark": frozenset({*_DEVICE_TARGET, "platform", "kind", "name", "note", "verify"}),
    "unmark": frozenset({*_DEVICE_TARGET, "platform", "kind", "name"}),
    "adopt": frozenset({*_DEVICE_TARGET, "platform"}),
    "records": frozenset({"platform"}),
    "gc": frozenset({"apply", "sizes"}),
    "benchmark": frozenset({"platform", "full", "yes"}),
    "boot": frozenset({*_DEVICE_TARGET, "window", "scale", "cold", "user_approved"}),
    "reboot": frozenset({*_DEVICE_TARGET, "window", "scale", "cold", "yes"}),
    "locale": frozenset({*_DEVICE_TARGET, "lang", "region", "app", "restore", "yes"}),
    "appearance": frozenset({*_DEVICE_TARGET, "mode", "restore", "yes"}),
    "text-size": frozenset({*_DEVICE_TARGET, "mode", "restore", "yes"}),
}


def option_label(dest: str) -> str:
    """dest > command-line form (run_dir > --run-dir, mode > <mode>)."""
    return MODE_LABEL if dest == "mode" else "--" + dest.replace("_", "-")


def unused_options(action: str, given: dict, defaults: dict) -> list[str]:
    """Options this action does not read but were given non-default values > list of forms. Actions not in the table are not filtered."""
    allowed = OPTIONS_BY_ACTION.get(action)
    if allowed is None:
        return []
    return [option_label(dest) for dest, default in defaults.items()
            if dest not in allowed and dest not in COMMON_OPTIONS and given.get(dest, default) != default]


def unused_options_failure(action: str, unused: list[str]) -> dict:
    """bad_args response: ignored options, options this action accepts, and guidance when --yes was used for memory risk."""
    valid = sorted(option_label(dest) for dest in OPTIONS_BY_ACTION[action] | COMMON_OPTIONS)
    payload = {"ok": False, "code": "bad_args", "action": action, "unused_options": unused, "valid_options": valid,
               "error": f"device {action} does not read {', '.join(unused)} — left as is, it would be silently ignored",
               "next": f"Call again with only the options device {action} accepts: {' '.join(valid)}"}
    if "--yes" in unused and "--user-approved" in valid:
        payload["next"] = ("Call again without --yes — --yes does not pass the memory risk gate. If it stops on memory risk, "
                           "show the reasons to the user and, once they answer, add --user-approved")
    return payload
