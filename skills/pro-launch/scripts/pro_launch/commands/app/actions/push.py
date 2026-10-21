"""`app push` — 푸시 알림을 흉내 낸다 (iOS 시뮬레이터 simctl push 전용)."""
from __future__ import annotations

import json
from pathlib import Path

from pro_launch.commands.app.app_control import (control_result, resolve_target, run_tool,
                                                 unsupported_response)
from pro_launch.registry import Action
from pro_launch.runtime.output import out

# payload 안에 대상 앱을 적는 simctl 표준 키 — 있으면 --pkg 없이도 된다
PAYLOAD_BUNDLE_KEY = "Simulator Target Bundle"


def _read_payload(raw_path: str | None) -> tuple[dict | None, str]:
    """(payload, 거부 사유). 파일이 없거나 JSON 객체가 아니면 사유를 돌려준다."""
    if not raw_path:
        return None, "--payload <json file> is required"
    path = Path(raw_path)
    if not path.is_file():
        return None, f"File not found: {raw_path}"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return None, f"Not JSON: {e}"
    if not isinstance(payload, dict) or "aps" not in payload:
        return None, "The top level must be an object with an aps key (APNs format)"
    return payload, ""


def _app_push(args) -> int:
    payload, reason = _read_payload(getattr(args, "payload", None))
    if payload is None:
        return out({"ok": False, "code": "payload_invalid", "error": reason,
                    "next": "{\"aps\": {\"alert\": {\"title\": \"t\", \"body\": \"b\"}}} — pass a file in this shape with --payload"})
    is_package_required = PAYLOAD_BUNDLE_KEY not in payload
    platform, dev_id, package, err = resolve_target(args, is_package_required=is_package_required)
    if err is not None:
        return err
    if platform != "ios":
        return unsupported_response(platform, dev_id, "push",
                                    "Android has no official way to fake a push via adb (it goes through the FCM server)",
                                    "Send an FCM test message (Firebase console · server API)")
    command = ["xcrun", "simctl", "push", dev_id] + ([package] if package else []) + [str(args.payload)]
    ok, detail = run_tool(command)
    return control_result("push", platform, dev_id, ok, detail, "push_failed",
                          "send push", "app shot  # check the notification banner",
                          "Check that the bundle ID matches the installed app", package=package)


def configure(p) -> None:
    p.add_argument("--payload", default=None, help="push: APNs payload JSON file (iOS simulator only)")


ACTION = Action(name="push", device_use="mutate", run=_app_push, configure=configure)
