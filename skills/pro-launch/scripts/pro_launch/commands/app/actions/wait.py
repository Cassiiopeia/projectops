"""`app wait` — wait until an element appears (or disappears with --gone), or with --settle until the screen stops changing (#928)."""
from __future__ import annotations

import json
import time

import app_input

from pro_launch.commands.app.gestures import backend_for, device_failure_response, elapsed_seconds, with_session_advice
from pro_launch.registry import Action
from pro_launch.runtime.output import out

# Default and maximum wait (seconds) / default and minimum screen re-read interval (seconds)
DEFAULT_WAIT_TIMEOUT_SECONDS = 30
MAXIMUM_WAIT_TIMEOUT_SECONDS = 300
DEFAULT_POLL_INTERVAL_SECONDS = 1.0
MINIMUM_POLL_INTERVAL_SECONDS = 0.2


def _app_wait(args) -> int:
    """Pick the target > device and backend > re-read the screen tree until the condition holds > result."""
    selector = next(((f, getattr(args, f"sel_{f}")) for f in app_input.SELECTOR_FIELDS
                     if getattr(args, f"sel_{f}", None)), None)
    is_settle = bool(getattr(args, "settle", False))
    if is_settle and selector:
        return out({"ok": False, "code": "settle_with_target",
                    "error": "--settle waits until the screen stops changing, without an element — do not combine it with --text · --id · --desc",
                    "next": "app wait --settle  or  app wait --text <text>"})
    if not selector and not is_settle:
        return out({"ok": False, "code": "target_required",
                    "error": "Needs one of --text · --id · --desc, or --settle to wait until the screen stops",
                    "next": "app wait --settle  # until transitions and loading finish (when you do not know the element)"})
    timeout = getattr(args, "timeout", None) or DEFAULT_WAIT_TIMEOUT_SECONDS
    if not 0 < timeout <= MAXIMUM_WAIT_TIMEOUT_SECONDS:
        return out({"ok": False, "code": "timeout_too_large",
                    "error": f"--timeout is 1–{MAXIMUM_WAIT_TIMEOUT_SECONDS} seconds (got {timeout})"})
    interval = max(getattr(args, "interval", None) or DEFAULT_POLL_INTERVAL_SECONDS, MINIMUM_POLL_INTERVAL_SECONDS)
    be, dev_id, err = backend_for(args)
    if err is not None:
        return err
    if is_settle:
        return _wait_until_settled(args, be, dev_id, timeout, interval)
    field, value = selector
    should_be_gone = bool(getattr(args, "gone", False))
    condition = f"{field}={value!r} " + ("gone" if should_be_gone else "visible")
    started = time.monotonic()
    deadline = started + timeout
    polls = 0
    while True:
        nodes = be.nodes(dev_id) or []
        polls += 1
        matches = app_input.match_nodes(nodes, field, value)
        # Failing to read the screen tree does not mean 'gone'
        if (matches and not should_be_gone) or (should_be_gone and nodes and not matches):
            return out({"ok": True, "code": "ok", "device": dev_id, "via": be.name, "condition": condition,
                        "polls": polls, "waited_seconds": round(time.monotonic() - started, 1),
                        "elapsed_seconds": elapsed_seconds(args),
                        "summary": f"{field}={value!r} " + ("gone" if should_be_gone else "appeared"),
                        "next": "app shot  # check the screen"})
        if time.monotonic() >= deadline:
            break
        time.sleep(interval)
    if not nodes and getattr(be, "device_failure", None):
        return device_failure_response(be, dev_id, args)
    return out({"ok": False, "code": "wait_timeout", "device": dev_id, "via": be.name,
                "condition": condition, "polls": polls, "timeout_seconds": timeout,
                "elapsed_seconds": elapsed_seconds(args),
                "error": f"{field}={value!r} " + ("did not disappear" if should_be_gone else "did not appear") + f" within {timeout}s",
                "next": "Look at the screen with app shot and check the text (app tree)"})


def _screen_signature(nodes: list[dict]) -> str:
    """Screen tree > comparison text (element order must match too for the same screen)."""
    return json.dumps(nodes, ensure_ascii=False, sort_keys=True)


def _wait_until_settled(args, be, dev_id: str, timeout: float, interval: float) -> int:
    """Done when the screen tree reads the same twice in a row — instead of a fixed sleep or waiting on any text (--text '.') (an empty screen does not count as settled)."""
    started = time.monotonic()
    deadline = started + timeout
    polls, previous_signature, nodes = 0, None, []
    while True:
        nodes = be.nodes(dev_id) or []
        polls += 1
        signature = _screen_signature(nodes) if nodes else None
        if signature is not None and signature == previous_signature:
            return out(with_session_advice({"ok": True, "code": "ok", "device": dev_id, "via": be.name,
                                            "condition": "settle", "polls": polls, "elements": len(nodes),
                                            "waited_seconds": round(time.monotonic() - started, 1),
                                            "elapsed_seconds": elapsed_seconds(args),
                                            "summary": "Screen settled (same structure twice in a row)",
                                            "next": "app tree  # or app shot"}, be, dev_id, args))
        previous_signature = signature
        if time.monotonic() >= deadline:
            break
        time.sleep(interval)
    if not nodes and getattr(be, "device_failure", None):
        return device_failure_response(be, dev_id, args)
    return out({"ok": False, "code": "wait_timeout", "device": dev_id, "via": be.name, "condition": "settle",
                "polls": polls, "timeout_seconds": timeout, "elapsed_seconds": elapsed_seconds(args),
                "error": f"Screen structure kept changing for {timeout}s (may be an animation · clock · auto-advancing screen)",
                "next": "Look with app shot, pick the element to wait for, then app wait --text <text>"})


def configure(p) -> None:
    # --text, --id, --desc are already defined by tap and --timeout by flow (app shares one parser)
    p.add_argument("--gone", action="store_true", help="wait: until it disappears instead of appears")
    p.add_argument("--settle", action="store_true",
                   help="wait: instead of an element, until the screen structure is the same twice in a row (waits for transitions and loading)")
    p.add_argument("--interval", type=float, default=None,
                   help=f"wait: seconds between screen reads (default {DEFAULT_POLL_INTERVAL_SECONDS:g})")


ACTION = Action(name="wait", device_use="read", run=_app_wait, configure=configure,
                help="Wait until an element (--text·--id·--desc) appears, with --gone until it disappears, with --settle until the screen stops (--timeout seconds)",
                example='app wait --device $DEV --text "Loading" --gone --timeout 40')
