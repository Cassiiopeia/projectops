"""`app shot` — 앱 화면을 찍는다."""
from __future__ import annotations

import re
import subprocess
import time

from common.proc import run, sdk_tool

from pro_launch.registry import Action
from pro_launch.runtime.context import project_root
from pro_launch.runtime.devices import adb_shell, no_device_response, pick_device
from pro_launch.runtime.output import out
from pro_launch.runtime.shots import finish_shot, shot_target


# 상태바를 고정해 캡처끼리 시각·배터리가 달라 보이지 않게 한다. 찍은 뒤 되돌린다.
DEFAULT_STATUS_TIME = "9:41"
# --time 값: H:MM 또는 HH:MM (24시간)
STATUS_TIME_PATTERN = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")

_ANDROID_DEMO = [
    ["settings", "put", "global", "sysui_demo_allowed", "1"],
    ["am", "broadcast", "-a", "com.android.systemui.demo", "-e", "command", "enter"],
    ["am", "broadcast", "-a", "com.android.systemui.demo", "-e", "command", "clock",
     "-e", "hhmm", "{hhmm}"],
    ["am", "broadcast", "-a", "com.android.systemui.demo", "-e", "command", "battery",
     "-e", "level", "100", "-e", "plugged", "false"],
    ["am", "broadcast", "-a", "com.android.systemui.demo", "-e", "command", "network",
     "-e", "wifi", "show", "-e", "level", "4"],
    ["am", "broadcast", "-a", "com.android.systemui.demo", "-e", "command", "notifications",
     "-e", "visible", "false"],
]


_ANDROID_DEMO_EXIT = ["am", "broadcast", "-a", "com.android.systemui.demo",
                      "-e", "command", "exit"]


_IOS_STATUS = ["--time", "{time}", "--batteryState", "charged", "--batteryLevel", "100",
               "--wifiBars", "3", "--cellularBars", "4"]


def _status_time(args) -> tuple[str | None, str | None]:
    """--time > (H:MM 표시용, 오류). --time 이 없으면 기본 9:41."""
    given = getattr(args, "time", None)
    if not given:
        return DEFAULT_STATUS_TIME, None
    match = STATUS_TIME_PATTERN.match(given.strip())
    if not match:
        return None, f"--time must be H:MM or HH:MM (got {given!r})"
    return f"{int(match.group(1))}:{match.group(2)}", None


def _app_shot(args) -> int:
    root = project_root(args)
    status_time, time_error = _status_time(args)
    if time_error:
        return out({"ok": False, "code": "bad_time", "error": time_error, "next": "e.g. app shot --time 7:42"})
    # --time 은 상태바 고정을 뜻한다
    should_clean_status = bool(args.clean_status or getattr(args, "time", None))
    hhmm = "".join(part.zfill(2) for part in status_time.split(":"))
    platform, dev_id, dev = pick_device(args.device)
    if not platform:
        return no_device_response(dev, args.device)
    # --shot 은 tap·swipe·run 의 이름 옵션이지만 shot 에서도 --out 과 같은 뜻으로 받는다
    raw, explicit = shot_target(root, args.out or getattr(args, "shot", None))

    restore = None
    try:
        if platform == "android":
            adb = sdk_tool("adb")
            if should_clean_status:
                # 데모 모드 허용 설정도 찍기 전 값으로 되돌린다 — 남의 기기 설정을 바꿔 두지 않는다
                prev = adb_shell(dev_id, "settings", "get", "global",
                                  "sysui_demo_allowed").strip()
                for c in _ANDROID_DEMO:
                    adb_shell(dev_id, *(part.replace("{hhmm}", hhmm) for part in c))

                def _undo_demo():
                    adb_shell(dev_id, *_ANDROID_DEMO_EXIT)
                    if prev in ("", "null"):
                        adb_shell(dev_id, "settings", "delete", "global", "sysui_demo_allowed")
                    else:
                        adb_shell(dev_id, "settings", "put", "global",
                                   "sysui_demo_allowed", prev)
                restore = _undo_demo
                time.sleep(0.6)
            # exec-out 은 바이너리를 그대로 준다. shell 로 받으면 줄바꿈이 바뀌어 PNG 가 깨진다
            r = subprocess.run([adb, "-s", dev_id, "exec-out", "screencap", "-p"],
                               capture_output=True, timeout=30)
            data = r.stdout
            if not data.startswith(b"\x89PNG"):
                return out({"ok": False, "code": "capture_failed", "device": dev_id,
                            "error": (r.stderr or b"").decode("utf-8", "replace")[:300]
                                     or "Response is not a PNG",
                            "hint": "The screen may be locked or a secure screen (FLAG_SECURE)"})
            raw.write_bytes(data)
        else:
            if should_clean_status:
                run(["xcrun", "simctl", "status_bar", dev_id, "override",
                     *(part.replace("{time}", status_time) for part in _IOS_STATUS)])
                restore = lambda: run(["xcrun", "simctl", "status_bar", dev_id, "clear"])  # noqa: E731
                time.sleep(0.6)
            r = subprocess.run(["xcrun", "simctl", "io", dev_id, "screenshot", str(raw)],
                               capture_output=True, text=True, timeout=30)
            if r.returncode != 0 or not raw.exists():
                return out({"ok": False, "code": "capture_failed", "device": dev_id,
                            "error": (r.stderr or "").strip()[:300]})
    except (OSError, subprocess.SubprocessError) as e:
        return out({"ok": False, "code": "capture_failed", "device": dev_id, "error": str(e)})
    finally:
        if restore:
            restore()

    final = finish_shot(raw, explicit, args)
    return out({"action": "shot", "platform": platform, "device": dev_id,
                "file": str(final), "clean_status": should_clean_status,
                **({"status_time": status_time} if should_clean_status else {}),
                "summary": f"Captured the {platform} screen: {final.name}",
                "next": "Read the image to decide the next action"})


def configure(p) -> None:
    p.add_argument("--out", default=None,
                   help="shot: a name (→ under $SHOT_DIR) or a path (saved as is). --shot means the same")
    p.add_argument("--clean-status", action="store_true",
                   help="shot: pin the status bar time and battery while capturing, then restore (default time 9:41)")
    p.add_argument("--time", default=None,
                   help="shot: pin the status bar time to this value (H:MM, e.g. 7:42 — also turns on --clean-status)")


ACTION = Action(name="shot", device_use="read", run=_app_shot, configure=configure)
