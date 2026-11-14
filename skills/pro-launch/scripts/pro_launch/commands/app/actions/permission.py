"""`app permission` — grant or deny app permissions without prompts (iOS simctl privacy, Android pm grant/revoke)."""
from __future__ import annotations

from pro_launch.commands.app.app_control import (adb_command, control_result, resolve_target, run_tool,
                                                 unsupported_response)
from pro_launch.registry import Action
from pro_launch.runtime.output import out

# Services accepted by simctl privacy (xcrun simctl help privacy)
IOS_PRIVACY_SERVICES = ("all", "calendar", "contacts-limited", "contacts", "location", "location-always",
                        "photos-add", "photos", "media-library", "microphone", "motion", "reminders", "siri")

# Common service name > Android runtime permission. Names containing a dot are used as raw permission names
ANDROID_PERMISSIONS_BY_SERVICE = {
    "camera": ["android.permission.CAMERA"],
    "microphone": ["android.permission.RECORD_AUDIO"],
    "location": ["android.permission.ACCESS_FINE_LOCATION", "android.permission.ACCESS_COARSE_LOCATION"],
    "location-always": ["android.permission.ACCESS_FINE_LOCATION", "android.permission.ACCESS_COARSE_LOCATION",
                        "android.permission.ACCESS_BACKGROUND_LOCATION"],
    "contacts": ["android.permission.READ_CONTACTS"],
    "calendar": ["android.permission.READ_CALENDAR"],
    "photos": ["android.permission.READ_MEDIA_IMAGES"],
    "notifications": ["android.permission.POST_NOTIFICATIONS"],
}


def _android_permissions(service: str) -> list[str] | None:
    if "." in service:
        return [service]
    return ANDROID_PERMISSIONS_BY_SERVICE.get(service)


def _app_permission(args) -> int:
    service = (getattr(args, "service", None) or "").strip()
    should_grant, should_revoke = bool(getattr(args, "grant", False)), bool(getattr(args, "revoke", False))
    if not service or should_grant == should_revoke:
        return out({"ok": False, "code": "permission_mode_required",
                    "error": "--service and one of --grant · --revoke are required",
                    "next": "app permission --service location --grant"})
    platform, dev_id, package, err = resolve_target(args)
    if err is not None:
        return err
    mode = "grant" if should_grant else "revoke"
    if platform == "ios":
        if service not in IOS_PRIVACY_SERVICES:
            return _unknown_service(platform, dev_id, service, IOS_PRIVACY_SERVICES)
        # simctl kills the app when a permission changes (simctl behavior)
        ok, detail = run_tool(["xcrun", "simctl", "privacy", dev_id, mode, service, package])
    else:
        permissions = _android_permissions(service)
        if permissions is None:
            return _unknown_service(platform, dev_id, service, sorted(ANDROID_PERMISSIONS_BY_SERVICE))
        # Multiple permissions (location etc.) — fail if any one fails
        ok, detail = True, ""
        for permission in permissions:
            ok, detail = run_tool(adb_command(dev_id, "shell", "pm", mode, package, permission))
            if not ok:
                break
    return control_result("permission", platform, dev_id, ok, detail, "permission_failed",
                          f"{package} {service} {mode}", "app relaunch  # restart with the changed permission",
                          "Check that the permission is declared in the app manifest / Info.plist",
                          package=package, service=service, mode=mode)


def _unknown_service(platform: str, dev_id: str, service: str, known) -> int:
    # If another platform has this service, it is 'not on this platform', not 'wrong name'
    other_known = (ANDROID_PERMISSIONS_BY_SERVICE if platform == "ios" else IOS_PRIVACY_SERVICES)
    if service in other_known:
        return unsupported_response(platform, dev_id, "permission",
                                    f"This command cannot change the {service} permission on {platform}",
                                    f"Supported services: {', '.join(known)}")
    return out({"ok": False, "code": "unknown_permission_service", "platform": platform,
                "error": f"Unknown service: {service}", "candidates": list(known),
                "next": "Call again with a name from candidates (Android also accepts a raw android.permission.X)"})


def configure(p) -> None:
    p.add_argument("--service", default=None, help="permission: service (location · camera · photos ...)")
    p.add_argument("--grant", action="store_true", help="permission: grant")
    p.add_argument("--revoke", action="store_true", help="permission: revoke")


ACTION = Action(name="permission", device_use="mutate", run=_app_permission, configure=configure)
