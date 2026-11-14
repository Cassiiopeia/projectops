"""Options shared by `desktop` actions. Each action lists only the names it uses in `Action.options` (#985)."""
from __future__ import annotations

import desktop_input

from pro_launch.runtime.shots import add_shot_args


def _window(p) -> None:
    p.add_argument("--window", default=None,
                   help="Window to use: part of the title, pid, handle, or 'overlay' for a system dialog / "
                        "notification (default: the window in front)")


def _root(p) -> None:
    p.add_argument("--root", default=".")


def _shot(p) -> None:
    p.add_argument("--shot", default=None, help="Take a shot right after the action (name or path)")
    add_shot_args(p)


def _timeout(p) -> None:
    p.add_argument("--timeout", type=int, default=10, help="Seconds to wait (max 300)")


def _limits(p) -> None:
    p.add_argument("--max-nodes", type=int, default=desktop_input.DEFAULT_MAX_NODES,
                   help=f"Stop reading after this many elements (default {desktop_input.DEFAULT_MAX_NODES})")
    p.add_argument("--depth", type=int, default=desktop_input.DEFAULT_MAX_DEPTH,
                   help=f"How deep to read the tree (default {desktop_input.DEFAULT_MAX_DEPTH})")


def _confirm(p) -> None:
    p.add_argument("--confirm-mutating", action="store_true",
                   help="Press a button that changes something (install, agree, delete, save…) — only after the user approved")


SHARED_OPTIONS = {"window": _window, "root": _root, "shot": _shot, "timeout": _timeout,
                  "limits": _limits, "confirm": _confirm}
# Attached to every action
ALWAYS_OPTIONS = ("root",)
# Seconds cap — same as web and app
MAX_TIMEOUT_SECONDS = 300
