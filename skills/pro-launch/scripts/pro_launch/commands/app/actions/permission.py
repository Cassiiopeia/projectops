"""`app permission` — 앱 권한을 묻지 않고 허용·거부한다 (iOS simctl privacy · Android pm grant/revoke)."""
from __future__ import annotations

from pro_launch.commands.app.app_control import (adb_command, control_result, resolve_target, run_tool,
                                                 unsupported_response)
from pro_launch.registry import Action
from pro_launch.runtime.output import out

# simctl privacy 가 받는 서비스 (xcrun simctl help privacy)
IOS_PRIVACY_SERVICES = ("all", "calendar", "contacts-limited", "contacts", "location", "location-always",
                        "photos-add", "photos", "media-library", "microphone", "motion", "reminders", "siri")

# 공통 서비스 이름 > Android 런타임 권한. 점이 든 이름은 권한 원문으로 그대로 쓴다
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
                    "error": "--service 와 --grant · --revoke 중 하나가 필요하다",
                    "next": "app permission --service location --grant"})
    platform, dev_id, package, err = resolve_target(args)
    if err is not None:
        return err
    mode = "grant" if should_grant else "revoke"
    if platform == "ios":
        if service not in IOS_PRIVACY_SERVICES:
            return _unknown_service(platform, dev_id, service, IOS_PRIVACY_SERVICES)
        # 권한이 바뀌면 simctl 이 앱을 끈다 (simctl 사양)
        ok, detail = run_tool(["xcrun", "simctl", "privacy", dev_id, mode, service, package])
    else:
        permissions = _android_permissions(service)
        if permissions is None:
            return _unknown_service(platform, dev_id, service, sorted(ANDROID_PERMISSIONS_BY_SERVICE))
        # 권한 여러 개 (location 등) — 하나라도 실패하면 실패
        ok, detail = True, ""
        for permission in permissions:
            ok, detail = run_tool(adb_command(dev_id, "shell", "pm", mode, package, permission))
            if not ok:
                break
    return control_result("permission", platform, dev_id, ok, detail, "permission_failed",
                          f"{package} {service} {mode}", "app relaunch  # 바뀐 권한으로 다시 띄운다",
                          "앱 매니페스트·Info.plist 에 그 권한이 선언돼 있는지 확인한다",
                          package=package, service=service, mode=mode)


def _unknown_service(platform: str, dev_id: str, service: str, known) -> int:
    # 다른 플랫폼에는 있는 서비스면 '이름 틀림'이 아니라 '이 플랫폼에 없음'
    other_known = (ANDROID_PERMISSIONS_BY_SERVICE if platform == "ios" else IOS_PRIVACY_SERVICES)
    if service in other_known:
        return unsupported_response(platform, dev_id, "permission",
                                    f"{platform} 에서는 {service} 권한을 이 명령으로 바꿀 수 없다",
                                    f"지원 서비스: {', '.join(known)}")
    return out({"ok": False, "code": "unknown_permission_service", "platform": platform,
                "error": f"알 수 없는 서비스: {service}", "candidates": list(known),
                "next": "candidates 의 이름으로 다시 부른다 (Android 는 android.permission.X 원문도 된다)"})


def configure(p) -> None:
    p.add_argument("--service", default=None, help="permission: 서비스 (location · camera · photos ...)")
    p.add_argument("--grant", action="store_true", help="permission: 허용")
    p.add_argument("--revoke", action="store_true", help="permission: 거부")


ACTION = Action(name="permission", device_use="mutate", run=_app_permission, configure=configure)
