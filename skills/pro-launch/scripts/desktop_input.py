"""OS backends that read and press the PC (desktop) screen (#985).

launch_cli.py `desktop …` actions call only this module. Every OS difference lives in `desktop_backends/`.

Design
- **Find through the screen tree (accessibility API) and press without moving the mouse** is the default.
  Windows uses UI Automation Invoke·Value·Toggle patterns, macOS uses AXPress·AXValue.
  So the user's cursor is never touched (`transport: "invoke"`).
- Only elements without a pattern are pressed with the mouse (`transport: "mouse"`). Before that, check whether the user moved the mouse.
- Every backend returns **nodes of the same shape**, with text·id·desc so `node_match.find_nodes` can use them as is.
- Each CLI call is a new process, so accessibility objects cannot be passed along. Elements are remembered by **locator**
  and found again right before pressing — window + path in the tree + kind and name. On mismatch: `ref_stale`.

Adding an OS
1. Make a class inheriting `DesktopBackend` in `desktop_backends/`.
2. Register it in `BACKENDS` below (key = the name `platform_key()` returns).
3. The contract test in tests/test_desktop_input.py catches missing methods.
"""
from __future__ import annotations

import importlib
import sys

# Fields kept per node — shape of an elements entry in the result JSON
NODE_FIELDS = ("ref", "text", "id", "desc", "role", "clickable", "enabled", "secret",
               "actions", "named_actions", "bounds", "center", "window", "mutating")
# Kinds treated as pressable (UIA ControlType · AX role normalized to short lowercase names)
CLICKABLE_ROLES = {"button", "checkbox", "radiobutton", "menuitem", "hyperlink", "link", "tabitem",
                   "listitem", "treeitem", "combobox", "splitbutton", "edit", "textfield", "cell"}
# Action names that run without the mouse (values backends put in actions)
ACTION_NAMES = ("invoke", "toggle", "select", "expand", "set_value")
# Do not input if the user moved the mouse more than this (pixels) — trackpad jitter is ignored
CURSOR_DRIFT_PIXELS = 4
# Only input arriving this many seconds after our last input counts as the user's — absorbs synthetic-input lag and clock skew (#985)
USER_INPUT_GRACE_SECONDS = 0.5
# Windows GetTickCount is 32-bit ms — wraps to 0 about every 49.7 days
TICK_WRAP_MILLISECONDS = 1 << 32
# Default node cap for tree — reading all of a big app (IDE, browser) takes seconds
DEFAULT_MAX_NODES = 300
DEFAULT_MAX_DEPTH = 25


# ── Shared pure functions (tested without an OS) ─────────────────────────────────

def make_desktop_node(*, text: str, id_: str, desc: str, role: str, enabled: bool, secret: bool,
                      actions: list[str], bounds: tuple[int, int, int, int] | None, window: str,
                      named_actions: list[str] | None = None) -> dict | None:
    """Raw values → node. None if zero size or off screen (invisible elements cannot be pressed).

    named_actions: hidden buttons called only by name (close·show on macOS notification banners, etc.). Used by `click --action`.
    """
    if not bounds:
        return None
    x1, y1, x2, y2 = (int(v) for v in bounds)
    if x2 <= x1 or y2 <= y1:
        return None
    role = (role or "").lower()
    clickable = bool(actions) or bool(named_actions) or role in CLICKABLE_ROLES
    return {"text": (text or "").strip(), "id": id_ or "", "desc": (desc or "").strip(), "role": role,
            "clickable": clickable, "enabled": bool(enabled), "secret": bool(secret),
            "actions": [a for a in actions if a in ACTION_NAMES], "named_actions": list(named_actions or []),
            "bounds": [x1, y1, x2, y2],
            "center": [(x1 + x2) // 2, (y1 + y2) // 2], "window": window or ""}


def is_worth_listing(node: dict) -> bool:
    """Is this node worth showing the agent — has text, is pressable, or is an input field."""
    return bool(node["text"] or node["desc"] or node["clickable"] or node["role"] in ("edit", "textfield"))


def assign_refs(nodes: list[dict]) -> list[dict]:
    """Number from 1. `find`·`tree` results and `click --ref` share the same numbers."""
    return [{**n, "ref": i} for i, n in enumerate(nodes, start=1)]


def public_node(node: dict) -> dict:
    """Shape included in results — locator (path·handle) stays only in the state file. Empty values are dropped."""
    return {k: node[k] for k in NODE_FIELDS if k in node and node[k] not in ("", None, [])}


def locator_matches(saved: dict, current: dict) -> bool:
    """Did the screen change since the ref was saved — kind and name must match to count as the same element.

    Position is not compared since moving the window changes it. Elements with an empty name are compared by id.
    """
    if (saved.get("role") or "") != (current.get("role") or ""):
        return False
    if saved.get("text") or current.get("text"):
        return (saved.get("text") or "") == (current.get("text") or "")
    return (saved.get("id") or "") == (current.get("id") or "")


def ratio_point(bounds: list[int], rx: float, ry: float) -> tuple[int, int]:
    """0-1 ratio within the window (or screen) area → physical pixel coordinates."""
    x1, y1, x2, y2 = bounds
    return int(round(x1 + (x2 - x1) * rx)), int(round(y1 + (y2 - y1) * ry))


def scale_point(x: float, y: float, scale: float) -> tuple[int, int]:
    """Logical coordinates (macOS points, etc.) × scale → physical pixels. Scale <= 0 is treated as 1."""
    s = scale if scale and scale > 0 else 1.0
    return int(round(x * s)), int(round(y * s))


def cursor_moved_by_user(last: list[int] | None, now: tuple[int, int] | None,
                         threshold: int = CURSOR_DRIFT_PIXELS) -> bool:
    """Did the user move away from where we last left the cursor. No record means no judgment (False)."""
    if not last or now is None:
        return False
    return abs(now[0] - last[0]) > threshold or abs(now[1] - last[1]) > threshold


def tick_elapsed_seconds(now_milliseconds: int, last_milliseconds: int) -> float:
    """Two 32-bit ticks → elapsed seconds. Subtracts modulo so it stays right across wraparound (GetLastInputInfo)."""
    return ((now_milliseconds - last_milliseconds) % TICK_WRAP_MILLISECONDS) / 1000.0


def user_input_after(baseline_at: float | None, idle_seconds: float | None, now: float,
                     grace: float = USER_INPUT_GRACE_SECONDS) -> bool:
    """Was there user input after our last input (baseline_at, epoch seconds).

    Last system input time = now - idle_seconds. Without a value (cannot detect) no judgment is made (False — fail open).
    """
    if baseline_at is None or idle_seconds is None or idle_seconds < 0:
        return False
    return now - idle_seconds > float(baseline_at) + grace


def ancestor_pids(own_pid: int, parent_by_pid: dict[int, int], limit: int = 64) -> set[int]:
    """Ancestor pids of this process (terminal, IDE, Claude app). Stops on cycles or broken chains too."""
    found, pid = set(), parent_by_pid.get(own_pid)
    while pid and pid not in found and len(found) < limit:
        found.add(pid)
        pid = parent_by_pid.get(pid)
    return found


def platform_key(platform: str | None = None) -> str | None:
    """sys.platform → backend name. None for unsupported OSes."""
    p = platform or sys.platform
    if p == "win32":
        return "windows"
    if p == "darwin":
        return "macos"
    return None


# ── Backend contract ──────────────────────────────────────────────────────────

class DesktopBackend:
    """One OS. Methods that change the screen return (success, human-readable reason)."""

    name = ""
    # Packages to install in the venv · install hint (used by desktop setup)
    packages: tuple[str, ...] = ()
    install_hint = ""

    def missing_modules(self) -> list[str]:
        """Module names that cannot be imported — usable when empty."""
        raise NotImplementedError

    def readiness(self) -> dict:
        """Permission, lock-screen and secure-desktop state. {"locked": bool, "secure_desktop": bool, "permissions": {...}}"""
        raise NotImplementedError

    def windows(self) -> list[dict]:
        """Open windows: {handle, pid, app, title, bounds, foreground, elevated}."""
        raise NotImplementedError

    def nodes(self, window: dict, max_nodes: int, max_depth: int) -> list[dict] | None:
        """Node list of that window, each with its locator (`path`). None when it cannot be read."""
        raise NotImplementedError

    def focus(self, window: dict) -> tuple[bool, str]:
        raise NotImplementedError

    def perform(self, window: dict, node: dict, action: str, value: str | None = None) -> tuple[bool, str]:
        """Run without the mouse (invoke·toggle·select·expand·set_value)."""
        raise NotImplementedError

    def cursor(self) -> tuple[int, int] | None:
        raise NotImplementedError

    # Input kinds the value below counts: "keyboard" · "keyboard_or_mouse". Empty means cannot detect
    user_input_kind = ""

    def seconds_since_user_input(self) -> float | None:
        """Seconds since the last user keyboard (·mouse) input. None when unreadable — let it pass rather than block (#985)."""
        return None

    def parent_by_pid(self) -> dict[int, int]:
        """pid → parent pid. Used so keys the user typed into the agent terminal are not treated as interference. Empty dict when unreadable."""
        return {}

    def mouse_click(self, x: int, y: int, button: str = "left", is_double: bool = False) -> tuple[bool, str]:
        raise NotImplementedError

    def type_text(self, text: str) -> tuple[bool, str]:
        raise NotImplementedError

    def press(self, key: str, mods: list[str]) -> tuple[bool, str]:
        raise NotImplementedError

    def grab(self, region: list[int] | None = None) -> bytes | None:
        """PNG bytes. region = [x1, y1, x2, y2] physical pixels, None for the main screen."""
        raise NotImplementedError


# name → "module:Class". Backend modules import OS-only libraries, so they load only when used.
BACKENDS = {
    "windows": "desktop_backends.windows_uia:WindowsBackend",
    "macos": "desktop_backends.macos_ax:MacBackend",
}


def get_backend(name: str | None = None) -> DesktopBackend | None:
    key = name or platform_key()
    target = BACKENDS.get(key or "")
    if not target:
        return None
    module_name, class_name = target.split(":")
    return getattr(importlib.import_module(module_name), class_name)()
