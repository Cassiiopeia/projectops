"""`app back` — go back (Android back key). Use instead of raw `adb shell input keyevent`."""
from __future__ import annotations

from pro_launch.commands.app.gestures import backend_for, before_shot, gesture_result
from pro_launch.registry import Action
from pro_launch.runtime.output import out

# iOS alternative: swipe right from the left edge (pop the navigation stack) — same coordinates as run.py's back rejection hint
IOS_EDGE_SWIPE_COMMAND = "app swipe --from 0.02,0.5 --to 0.8,0.5"


def _app_back(args) -> int:
    """Press only on platforms with a back button (Android). iOS goes back differently per screen, so suggest an alternative."""
    be, dev_id, err = backend_for(args)
    if err is not None:
        return err
    if not be.has_back_button:
        return out({"ok": False, "code": "back_unsupported_on_platform", "device": dev_id, "platform": be.name,
                    "error": f"{be.name} has no back button",
                    "next": f"Press the on-screen back button with app tap --desc|--text, or {IOS_EDGE_SWIPE_COMMAND} (edge swipe)",
                    "hint": "Use app tree to find the back button's desc · text (usually the previous screen title or 'Back')"})
    before = before_shot(args, be, dev_id)
    ok, detail = be.press_back(dev_id)
    return gesture_result(args, be, dev_id, before, ok, detail, "back_failed", "back")


ACTION = Action(name="back", device_use="mutate", run=_app_back,
                help="Go back — Android back key (also hides the keyboard). On iOS it suggests alternatives",
                example="app back --device $DEV --shot after_back")
