"""Shared option table for `web` — each action picks what it uses by these names (`Action.options`, #896).

Options used by only one action live in that action's `configure`. Options used by two or more move here.
"""
from __future__ import annotations

from pro_launch.runtime.shots import add_shot_args


def _root(p) -> None:
    p.add_argument("--root", default=".", help="Project root (where the state file lives)")


def _url(p) -> None:
    p.add_argument("--url", default=None, help="URL")


def _selector(p) -> None:
    p.add_argument("--selector", default=None,
                   help="Target selector. text=Login · #id · button:has-text('x')")


def _ref(p) -> None:
    p.add_argument("--ref", type=int, default=None,
                   help="Number given by web find or web inspect. Use it instead of guessing a selector")


def _text(p) -> None:
    p.add_argument("--text", default=None, help="Value to type, or text to find or check")


def _secret_text(p) -> None:
    # A password in --text is stored in plain text in the session log (#604)
    p.add_argument("--cred", default=None, help="Type from a saved login (cred list). The value never appears on the command line")
    p.add_argument("--cred-field", dest="cred_field", default=None,
                   help="Field to type from --cred (default password, e.g. account)")
    p.add_argument("--text-env", dest="text_env", default=None,
                   help="Read the value from an environment variable — always use this for passwords")


def _timeout(p) -> None:
    p.add_argument("--timeout", type=int, default=10, help="Wait limit (seconds)")


def _target_timeout(p) -> None:
    # Cuts the full 10 seconds each guessed selector used to spend (#888). Defaults are computed in element.py *_wait_seconds
    p.add_argument("--timeout", type=int, default=None,
                   help="Wait limit (seconds). Default: 4 s for the target element, 10 s for the result after the press (--expect-*, downloads). If given, both use this value")


def _frame(p) -> None:
    # Login forms inside cross-origin iframes etc. — top-document selectors can't see inside (#877)
    p.add_argument("--frame", default=None,
                   help="Act inside an iframe: frame name, iframe selector or part of its url (lists frames if not found)")


def _clear(p) -> None:
    p.add_argument("--clear", action="store_true", help="Clear the setting")


def _out(p) -> None:
    p.add_argument("--out", default=None, help="Name (saved under $SHOT_DIR) or path")


def _confirm_mutating(p) -> None:
    p.add_argument("--confirm-mutating", dest="confirm_mutating", action="store_true",
                   help="Act even in a read-only session (only after the user approves)")


def _capture_requests(p) -> None:
    # Replaces hand-written page.on("response") hooks to check that a save really reached the server (#930)
    p.add_argument("--capture-requests", dest="capture_requests", action="store_true",
                   help="Add the non-GET requests this action caused (method · status · url) to the result's requests")


# Shared option name → function that adds it to the parser. Names are the values listed in Action.options
SHARED_OPTIONS = {
    "root": _root,
    "url": _url,
    "selector": _selector,
    "ref": _ref,
    "text": _text,
    "secret_text": _secret_text,
    "timeout": _timeout,
    # --timeout for actions on elements (click, type, check, select, hover, press, download).
    # Same flag as timeout, so an action lists only one of the two. Must come after timeout above so undeclared actions keep the default of 10
    "target_timeout": _target_timeout,
    "frame": _frame,
    "clear": _clear,
    "out": _out,
    "confirm_mutating": _confirm_mutating,
    "shot_format": add_shot_args,
    "capture_requests": _capture_requests,
}

# Accepted by every action
ALWAYS_OPTIONS = ("root",)


# --timeout upper bound (seconds). Above it, treat it as mistakenly given in milliseconds — 3000 is 50 minutes (#931, observed: held the shared browser for 50 minutes)
MAXIMUM_TIMEOUT_SECONDS = 300


def timeout_failure(args) -> dict | None:
    """timeout_too_large result if --timeout exceeds the bound, otherwise None. Every web action checks this before attaching."""
    timeout = getattr(args, "timeout", None)
    if timeout is None or timeout <= MAXIMUM_TIMEOUT_SECONDS:
        return None
    return {"ok": False, "code": "timeout_too_large", "action": getattr(args, "action", None),
            "timeout": timeout, "maximum_seconds": MAXIMUM_TIMEOUT_SECONDS,
            "error": f"--timeout {timeout} is too long (the unit is seconds — {timeout} s is about {round(timeout / 60)} min)",
            "hint": (f"Give seconds, not milliseconds (e.g. 5000ms → --timeout 5). Maximum {MAXIMUM_TIMEOUT_SECONDS} s. "
                     "To wait longer, call web wait again"),
            "next": f"web {getattr(args, 'action', '<action>')} --timeout {min(max(timeout // 1000, 1), MAXIMUM_TIMEOUT_SECONDS)}"}
