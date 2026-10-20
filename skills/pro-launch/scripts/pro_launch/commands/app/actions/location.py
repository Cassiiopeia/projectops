"""`app location` — 기기의 가상 위치를 정한다 (iOS simctl location · Android 에뮬레이터 geo fix)."""
from __future__ import annotations

from pro_launch.commands.app.app_control import (adb_command, control_result, resolve_target, run_tool,
                                                 unsupported_response)
from pro_launch.registry import Action
from pro_launch.runtime.output import out


def _is_valid_coordinate(latitude, longitude) -> bool:
    return (latitude is not None and longitude is not None
            and -90 <= latitude <= 90 and -180 <= longitude <= 180)


def _app_location(args) -> int:
    latitude, longitude = getattr(args, "lat", None), getattr(args, "lon", None)
    if not _is_valid_coordinate(latitude, longitude):
        return out({"ok": False, "code": "bad_coordinates",
                    "error": "--lat(-90~90) 와 --lon(-180~180) 이 둘 다 필요하다",
                    "next": "app location --lat 37.5665 --lon 126.9780"})
    platform, dev_id, _, err = resolve_target(args, is_package_required=False)
    if err is not None:
        return err
    if platform == "android":
        # geo fix 는 에뮬레이터 콘솔 명령 — 실기기에는 없다. 인자 순서는 경도 먼저
        if not dev_id.startswith("emulator-"):
            return unsupported_response(platform, dev_id, "location",
                                        "실기기 Android 는 adb 로 위치를 바꿀 수 없다 (에뮬레이터만)",
                                        "에뮬레이터를 쓰거나 기기에 모의 위치 앱을 설정한다")
        ok, detail = run_tool(adb_command(dev_id, "emu", "geo", "fix", str(longitude), str(latitude)))
        ok = ok and "KO" not in detail
    else:
        ok, detail = run_tool(["xcrun", "simctl", "location", dev_id, "set", f"{latitude},{longitude}"])
    return control_result("location", platform, dev_id, ok, detail, "location_failed",
                          f"위치 {latitude},{longitude}", "app shot  # 지도·위치 화면을 확인한다",
                          "Xcode 14 이상(simctl location) · 에뮬레이터 콘솔이 열려 있는지 확인한다",
                          latitude=latitude, longitude=longitude)


def configure(p) -> None:
    p.add_argument("--lat", type=float, default=None, help="location: 위도 (-90~90)")
    p.add_argument("--lon", type=float, default=None, help="location: 경도 (-180~180)")


ACTION = Action(name="location", device_use="mutate", run=_app_location, configure=configure)
