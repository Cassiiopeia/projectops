"""`app back` — 뒤로가기 (Android 뒤로 키). raw `adb shell input keyevent` 대신 쓴다."""
from __future__ import annotations

from pro_launch.commands.app.gestures import backend_for, before_shot, gesture_result
from pro_launch.registry import Action
from pro_launch.runtime.output import out

# iOS 대안: 왼쪽 가장자리에서 오른쪽으로 밀기 (내비게이션 스택 뒤로) — run.py 의 back 거절 안내와 같은 좌표
IOS_EDGE_SWIPE_COMMAND = "app swipe --from 0.02,0.5 --to 0.8,0.5"


def _app_back(args) -> int:
    """뒤로 버튼이 있는 플랫폼(Android)만 누른다. iOS 는 화면마다 뒤로가기 방식이 달라 대안을 안내한다."""
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
