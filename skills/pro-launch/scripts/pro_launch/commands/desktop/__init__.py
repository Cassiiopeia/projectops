"""`desktop` — read and press programs on the PC screen (installer wizards, OS dialogs, desktop apps) (#985).

Pages inside a browser belong to `web`, emulators and simulators to `app`. This covers every other window.

The safety gate lives only in this file (action declaration `device_use`).
    read    checks dependencies only — window list, tree, capture, wait
    mutate  + not a secure screen (UAC, lock) + this session holds the input session + not paused
            + no user key input since our last input (mouse included on Windows)
    none    the action decides itself (setup, doctor, session)
OS differences are all handled by the backend in `scripts/desktop_input.py`. Adding an action never changes this file.
"""
from __future__ import annotations

import argparse

from pro_launch.commands.desktop import actions as _actions
from pro_launch.commands.desktop.common import load_backend
from pro_launch.commands.desktop.host_app import host_app_label, find_host_app
from pro_launch.commands.desktop.input_ops import TAKEOVER_WORDS, keyboard_takeover_refusal
from pro_launch.commands.desktop.options import ALWAYS_OPTIONS, MAX_TIMEOUT_SECONDS, SHARED_OPTIONS
from pro_launch.registry import Command, action_usage_lines, add_action_parsers, discover_actions
from pro_launch.runtime import desktop_state
from pro_launch.runtime.context import MEMORY_CTX, project_root
from pro_launch.runtime.output import out, set_area

ACTIONS = discover_actions(_actions)


def configure(p) -> None:
    add_action_parsers(p, ACTIONS, SHARED_OPTIONS, always=ALWAYS_OPTIONS)
    p.formatter_class = argparse.RawDescriptionHelpFormatter
    p.description = "Drive programs on this computer's screen, one action per call — options per action: desktop <action> --help"
    p.epilog = "Options per action:\n" + "\n".join(action_usage_lines(p))


def input_gate(be) -> dict | None:
    """Before an action that changes the screen. Failure result if blocked, None if allowed."""
    ready = be.readiness()
    if ready.get("secure_desktop") or ready.get("consent_prompt"):
        return {"ok": False, "code": "needs_user", "reason": "secure_desktop",
                "error": "A security prompt (UAC, sign-in, Ctrl+Alt+Del) is in front. Only a person can answer it",
                "ask_user": "Please answer the security prompt on the screen, then tell me when it is done",
                "next": "desktop windows  # after the user says it is done"}
    if ready.get("locked"):
        return {"ok": False, "code": "screen_locked", "error": "The screen is locked",
                "ask_user": "Please unlock the screen, then tell me when it is done"}
    missing = [k for k, granted in (ready.get("permissions") or {}).items() if not granted]
    if missing:
        # Click and type compare screens before/after, so screen recording is needed too — hosts with only Accessibility on stop here (#1132)
        return {"ok": False, "code": "permission_missing", "missing": missing,
                "error": f"macOS has not granted {', '.join(missing)} to {host_app_label(find_host_app())}. "
                         "click · type · press · focus need both Accessibility and Screen Recording",
                "next": "desktop doctor  # names the host app and where a person turns it on"}
    holder = desktop_state.current_holder()
    mine = desktop_state.my_session()
    if mine is None:
        if holder:
            return {"ok": False, "code": "desktop_busy", "holder": holder.get("session"),
                    "purpose": holder.get("purpose"),
                    "error": "Another session is using this computer's keyboard and mouse",
                    "next": "desktop session status  # wait, or ask the user"}
        return {"ok": False, "code": "desktop_session_required",
                "error": "Start an input session first — it tells the user this session will use the keyboard and mouse",
                "next": "desktop session start --purpose \"<why>\""}
    if mine.get("paused"):
        words = TAKEOVER_WORDS.get(mine.get("paused_by") or "mouse", TAKEOVER_WORDS["keyboard_or_mouse"])
        return {"ok": False, "code": "user_interrupted", "input_detected": mine.get("paused_by") or "mouse",
                "error": f"The input session is paused because the user {words}",
                "ask_user": f"You {words} while I was working. May I continue?",
                "next": "desktop session resume  # only after the user agrees"}
    return keyboard_takeover_refusal(be, mine)


def cmd_desktop(args) -> int:
    MEMORY_CTX["root"] = project_root(args)
    set_area("desktop", MEMORY_CTX["root"])
    if getattr(args, "timeout", None) and args.timeout > MAX_TIMEOUT_SECONDS:
        return out({"ok": False, "code": "timeout_too_large",
                    "error": f"--timeout is in seconds (max {MAX_TIMEOUT_SECONDS})"})
    action = ACTIONS[args.action]
    args.backend = None
    if action.device_use in ("read", "mutate"):
        be, failure = load_backend()
        if failure:
            return out(failure)
        if action.device_use == "mutate":
            refusal = input_gate(be)
            if refusal:
                return out({**refusal, "platform": be.name, "action": args.action})
        args.backend = be
    return action.run(args)


COMMANDS = [Command(name="desktop",
                    help="Drive programs on this computer's screen (installers, OS dialogs, desktop apps): "
                         "windows, tree, find, click, type, press, shot, wait — input only inside a session",
                    run=cmd_desktop, configure=configure)]
