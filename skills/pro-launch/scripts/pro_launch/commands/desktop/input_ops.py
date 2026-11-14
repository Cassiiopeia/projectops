"""Shared sequence for `desktop` input actions — re-find ref, dangerous buttons, no mouse, user intervention, result check (#985).

Press order
    1) Bring the window to front if it is not
    2) If the element supports a pattern, run it without the mouse     transport: invoke
    3) Otherwise check for user intervention, then use the mouse     transport: mouse
    4) Compare screens → screen_changed, wait until settled, then --shot
"""
from __future__ import annotations

import os
import time

import desktop_input

from pro_launch.commands.desktop.common import save_shot, screen_digest, settle, target_window
from pro_launch.runtime import desktop_state
from pro_launch.runtime.mutating import is_mutating_label

# Pattern priority for pressing (set_value, which enters values, is used by type)
PRESS_ACTIONS = ("invoke", "toggle", "select", "expand")
# Reason text the backend perform uses to say "the found element is not that element"
STALE_REASONS = ("element is gone", "element changed")


def stale_failure(detail: str) -> dict:
    return {"ok": False, "code": "ref_stale", "error": f"The {detail} since find",
            "next": "desktop find --text \"<text>\"  # number the elements again"}


def resolve_ref(be, ref: int) -> tuple[dict | None, dict | None, dict | None]:
    """(window, node, failure result). Matches the last tree/find ref against the current window list."""
    snap = desktop_state.load_snapshot()
    nodes = snap.get("nodes") or []
    node = next((n for n in nodes if n.get("ref") == ref), None)
    if node is None:
        return None, None, {"ok": False, "code": "ref_stale" if nodes else "ref_missing",
                            "error": f"ref {ref} is not in the last tree/find result",
                            "next": "desktop find --text \"<text>\"  # number the elements again"}
    saved = snap.get("window") or {}
    window = next((w for w in be.windows() if w["handle"] == saved.get("handle")), None)
    if window is None:
        return None, None, {"ok": False, "code": "ref_stale", "error": "The window of that ref is gone",
                            "next": "desktop windows"}
    return target_window(window), node, None


def mutating_refusal(node: dict, is_confirmed: bool) -> dict | None:
    if node.get("mutating") and not is_confirmed:
        return {"ok": False, "code": "mutating_blocked", "element": desktop_input.public_node(node),
                "error": f"'{node.get('text')}' changes something that is hard to undo",
                "ask_user": f"Pressing '{node.get('text')}' will make a change. Shall I press it?",
                "next": f"desktop click --ref {node.get('ref')} --confirm-mutating  # only after the user agrees"}
    if not node.get("enabled", True):
        return {"ok": False, "code": "element_disabled", "element": desktop_input.public_node(node),
                "error": f"'{node.get('text')}' is disabled", "next": "desktop wait --settle, then find again"}
    return None


def named_action_refusal(node: dict, name: str, is_confirmed: bool) -> dict | None:
    """`click --action` — judged by action name, not node text (a banner body is not a button)."""
    names = node.get("named_actions") or []
    if name not in names:
        return {"ok": False, "code": "action_not_found", "candidates": names, "element": desktop_input.public_node(node),
                "error": f"'{node.get('text')}' has no action named {name!r}",
                "next": f"desktop click --ref {node.get('ref')} --action \"<one of candidates>\""}
    if is_mutating_label(name, is_desktop=True) and not is_confirmed:
        return {"ok": False, "code": "mutating_blocked", "element": desktop_input.public_node(node), "action": name,
                "error": f"'{name}' on '{node.get('text')}' changes something that is hard to undo",
                "ask_user": f"Pressing '{name}' on '{node.get('text')}' will make a change. Shall I press it?",
                "next": f"desktop click --ref {node.get('ref')} --action \"{name}\" --confirm-mutating  # only after the user agrees"}
    return None


# input_detected value from user-intervention detection → message to the person
TAKEOVER_WORDS = {"mouse": "moved the mouse", "keyboard": "typed on the keyboard",
                  "keyboard_or_mouse": "used the keyboard or mouse"}


def interrupted(input_detected: str, did_not: str, **extra) -> dict:
    """Pause the session and build a user_interrupted result (mouse and keyboard alike)."""
    words = TAKEOVER_WORDS.get(input_detected, TAKEOVER_WORDS["keyboard_or_mouse"])
    desktop_state.touch_session(paused=True, paused_by=input_detected)
    return {"ok": False, "code": "user_interrupted", "input_detected": input_detected, **extra,
            "error": f"The user {words}, so I did not {did_not}",
            "ask_user": f"You {words} while I was working. May I continue?",
            "next": "desktop session resume  # only after the user agrees"}


def user_input_check(be) -> tuple[float | None, bool]:
    """(seconds since last user input, is detectable). (None, False) if the OS cannot tell — does not block."""
    try:
        idle = be.seconds_since_user_input()
    except Exception:   # noqa: BLE001 — detection is a secondary safeguard, so failure never blocks input (#985)
        idle = None
    return idle, idle is not None


def is_reply_to_agent(be) -> bool:
    """Is the front window the terminal/IDE/Claude app that launched this CLI — keys typed there answer the agent, not intervention."""
    front = next((w for w in be.windows() if w.get("foreground")), None)
    if not front or not front.get("pid"):
        return False
    return int(front["pid"]) in desktop_input.ancestor_pids(os.getpid(), be.parent_by_pid())


def keyboard_takeover_refusal(be, session: dict) -> dict | None:
    """If the user pressed a key after our last input (last_used), pause the session (#985).

    None if undetectable (fail open). Answers typed into the agent terminal (approval "yes" etc.) are let through.
    """
    idle, is_available = user_input_check(be)
    if not is_available:
        return None
    baseline = session.get("last_used") or session.get("started_at")
    if not desktop_input.user_input_after(baseline, idle, time.time()) or is_reply_to_agent(be):
        return None
    return interrupted(be.user_input_kind or "keyboard_or_mouse", "continue",
                       idle_seconds=round(idle, 2))


def guarded_mouse_click(be, x: int, y: int, is_double: bool = False) -> tuple[bool, str, dict | None]:
    """If the user is using the mouse, do not press; pause the session. (success, reason, failure result)"""
    session = desktop_state.my_session() or {}
    if desktop_input.cursor_moved_by_user(session.get("last_cursor"), be.cursor()):
        return False, "user moved the mouse", interrupted("mouse", "click")
    ok, detail = be.mouse_click(x, y, is_double=is_double)
    desktop_state.touch_session(last_cursor=[x, y])
    return ok, detail, None


def press_node(be, window: dict, node: dict) -> tuple[bool, str, str, dict | None]:
    """(success, reason, transport, failure result). Avoids the mouse when a pattern exists."""
    for action in (a for a in PRESS_ACTIONS if a in (node.get("actions") or [])):
        ok, detail = be.perform(window, node, action)
        if detail in STALE_REASONS:
            return False, detail, "invoke", stale_failure(detail)
        if ok:
            desktop_state.touch_session()
            return True, detail, "invoke", None
        # This pattern failed — next pattern, then the mouse
    ok, detail, failure = guarded_mouse_click(be, *node["center"])
    return ok, detail, "mouse", failure


def keys_target_refusal(be, window: dict) -> dict | None:
    """Before sending keys — is the system window (banner, popup) really in front? Otherwise keys go to the app the user was using."""
    if not window.get("overlay"):
        return None
    now = next((w for w in be.windows() if w["handle"] == window["handle"]), None)
    if now and now.get("foreground"):
        return None
    return {"ok": False, "code": "focus_failed", "window": window.get("title"),
            "error": "This system window cannot take keyboard focus, so keys would go to another app",
            "next": "desktop find --window overlay --text \"<button>\"  # press its buttons instead"}


def ensure_front(be, window: dict) -> dict | None:
    if window.get("elevated"):
        return {"ok": False, "code": "elevated_window", "window": window.get("title"),
                "error": "This window runs as administrator; Windows blocks input from this session",
                "ask_user": f"'{window.get('title')}' runs as administrator. Please press it yourself"}
    if window.get("foreground"):
        return None
    ok, detail = be.focus(window)
    return None if ok else {"ok": False, "code": "focus_failed", "error": detail,
                            "next": "Ask the user to click the window once, then retry"}


def finish(be, args, region: list[int] | None, before: str | None, payload: dict) -> dict:
    """Attach screen change, wait and --shot."""
    changed, waited = settle(be, region, before)
    payload.update(screen_changed=changed, settle_seconds=waited)
    if changed is False:
        payload["hint"] = "Nothing changed on screen — pick another candidate"
    if getattr(args, "shot", None):
        payload["shot"] = save_shot(be, args, region, args.shot)
    return payload


def before_digest(be, region: list[int] | None) -> str | None:
    return screen_digest(be, region)
