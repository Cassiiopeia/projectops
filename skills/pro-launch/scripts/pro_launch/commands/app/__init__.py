"""`app` — capture, launch, stop, type into, tap and swipe app screens; set location, permissions, push and deep links.

Each action is one module in `actions/`. Everything that differs per platform (Android, iOS) lives in the
backends of `scripts/app_input.py` — a new platform adds a backend there and leaves this folder alone.
"""
from __future__ import annotations

import os
import time

from harness_store import APP_AREA

from pro_launch.commands.app import actions as _actions
from pro_launch.registry import Command, discover_actions
from pro_launch.runtime.context import MEMORY_CTX, project_root
from pro_launch.runtime.device_gate import gate_device_use
from pro_launch.runtime.output import out, set_target
from pro_launch.runtime.shots import add_shot_args

ACTIONS = discover_actions(_actions)
# Actions that read the shared positional word (session_verb); any other action rejects a stray word (#1224)
POSITIONAL_WORD_ACTIONS = ("session", "record", "swipe")


def configure(p) -> None:
    # Options shared by several actions. Options used by one action live in that action's configure
    p.add_argument("action", choices=sorted(ACTIONS))
    p.add_argument("--shot", default=None, help="tap·swipe·back·run: take a shot right after (name or path) — saves a separate shot call")
    p.add_argument("--root", default=".")
    p.add_argument("--device", default=None,
                   help="Android serial or iOS UDID. Default: $DEV → the only attached device")
    p.add_argument("--yes", action="store_true",
                   help="proceed even on a device held by another session (only after asking the user)")
    p.add_argument("--pkg", default=None, help="launch·terminate·relaunch·permission·push: package name / bundle ID (default: $PKG → device bind package)")
    add_shot_args(p)
    for action in ACTIONS.values():
        if action.configure:
            action.configure(p)


def cmd_app(args) -> int:
    MEMORY_CTX["root"] = project_root(args)
    # Attach the harness (guide) for this app to the response — here only an explicit --pkg or $PKG.
    # A device bind package is passed only by actions that actually use it (resolve_target) (projectops#1024)
    set_target(app=getattr(args, "pkg", None) or os.environ.get("PKG"), root=MEMORY_CTX["root"], area=APP_AREA)
    # Reference point for the elapsed_seconds an action adds to its result (includes device pick and tool runs)
    args.started_monotonic = time.monotonic()
    action = ACTIONS.get(args.action, ACTIONS["launch"])
    stray_word = getattr(args, "session_verb", None)
    if stray_word and args.action not in POSITIONAL_WORD_ACTIONS:
        return out({"ok": False, "code": "bad_args", "error": f"app {args.action} takes no positional word: {stray_word}",
                    "summary": f"Argument error: unexpected '{stray_word}'",
                    "next": f"launch_cli.py app {args.action} --help  # pass values with their option name"})
    # Ownership check and recording happen here only (declared per action via device_use)
    refusal = gate_device_use(action.device_use, args.device, str(MEMORY_CTX["root"]), bool(getattr(args, "yes", False)))
    if refusal is not None:
        return refusal
    return action.run(args)


COMMANDS = [Command(name="app",
                    help="Capture (shot), start/stop (launch·terminate·relaunch), type, tap, swipe and go back in an app. Several steps at once (run). "
                         "Location, permissions, push, deep links (location·permission·push·openurl)",
                    run=cmd_app, configure=configure)]
