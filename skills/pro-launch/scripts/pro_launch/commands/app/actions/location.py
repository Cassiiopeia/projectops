"""`app location` — set the device's simulated location (iOS simctl location, Android emulator geo fix)."""
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
                    "error": "Both --lat (-90..90) and --lon (-180..180) are required",
                    "next": "app location --lat 37.5665 --lon 126.9780"})
    platform, dev_id, _, err = resolve_target(args, is_package_required=False)
    if err is not None:
        return err
    if platform == "android":
        # geo fix is an emulator console command — not available on real devices. Longitude comes first
        if not dev_id.startswith("emulator-"):
            return unsupported_response(platform, dev_id, "location",
                                        "adb cannot change the location of a real Android device (emulators only)",
                                        "Use an emulator or set up a mock location app on the device")
        ok, detail = run_tool(adb_command(dev_id, "emu", "geo", "fix", str(longitude), str(latitude)))
        ok = ok and "KO" not in detail
    else:
        ok, detail = run_tool(["xcrun", "simctl", "location", dev_id, "set", f"{latitude},{longitude}"])
    return control_result("location", platform, dev_id, ok, detail, "location_failed",
                          f"location {latitude},{longitude}", "app shot  # check the map / location screen",
                          "Check for Xcode 14+ (simctl location) · that the emulator console is open",
                          latitude=latitude, longitude=longitude)


def configure(p) -> None:
    p.add_argument("--lat", type=float, default=None, help="location: latitude (-90..90)")
    p.add_argument("--lon", type=float, default=None, help="location: longitude (-180..180)")


ACTION = Action(name="location", device_use="mutate", run=_app_location, configure=configure)
