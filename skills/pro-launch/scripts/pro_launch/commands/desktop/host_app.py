"""macOS 권한 대상 호스트 앱 찾기: 손쉬운 사용 · 화면 기록은 python3 가 아니라 agent 를 띄운 앱에 준다 (#1132)
찾는 순서: 조상 프로세스의 가장 바깥 .app > __CFBundleIdentifier > None
"""
from __future__ import annotations

import os
import re
import sys

from pro_launch.runtime import procs

# 경로 안 가장 바깥 앱 번들 (Cursor.app/…/Cursor Helper.app 이면 Cursor.app)
OUTERMOST_APP_BUNDLE_PATTERN = re.compile(r"(/(?:[^/]+/)*?([^/]+)\.app)/Contents/")
# launchd 가 GUI 앱 자식에게 물려주는 번들 ID (tmux 처럼 조상에 앱이 없을 때)
BUNDLE_ID_ENV_VAR = "__CFBundleIdentifier"
# 조상 체인 최대 단계 (ppid 순환 대비)
MAXIMUM_ANCESTOR_DEPTH = 64
# 시스템 설정 화면 바로 열기 (사람이 켤 곳)
ACCESSIBILITY_SETTINGS_URL = "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
SCREEN_RECORDING_SETTINGS_URL = "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"


def app_bundle_in(command: str) -> tuple[str, str] | None:
    """명령줄 > (앱 이름, 번들 경로). 앱 번들 밖이면 None"""
    match = OUTERMOST_APP_BUNDLE_PATTERN.search(command or "")
    return (match.group(2), match.group(1)) if match else None


def find_host_app() -> dict | None:
    """권한 대상 앱 > {name, path, bundle_id, found_by}. macOS 가 아니거나 못 찾으면 None"""
    if sys.platform != "darwin":
        return None
    bundle_id = os.environ.get(BUNDLE_ID_ENV_VAR) or None
    outermost = None
    # 가장 위 조상의 앱이 TCC 책임 앱 (자식 Helper 앱보다 위)
    current = procs.read_process(os.getpid())
    for _ in range(MAXIMUM_ANCESTOR_DEPTH):
        if current is None:
            break
        found = app_bundle_in(current.get("command", ""))
        if found:
            outermost = found
        parent_pid = current.get("ppid")
        if not parent_pid or parent_pid == current["pid"]:
            break
        current = procs.read_process(parent_pid)
    if outermost:
        return {"name": outermost[0], "path": outermost[1], "bundle_id": bundle_id, "found_by": "process"}
    if bundle_id:
        return {"name": bundle_id, "path": None, "bundle_id": bundle_id, "found_by": "environment"}
    return None


def host_app_label(host: dict | None) -> str:
    """사람에게 보일 앱 이름. 모르면 일반 표현"""
    if not host:
        return "the app that runs this agent (Terminal, iTerm, Paseo, Cursor, VS Code…)"
    return f"{host['name']} ({host['path']})" if host.get("path") else host["name"]


# 권한 이름 > (설정 메뉴 경로, 바로 여는 주소)
PERMISSION_SETTINGS = {
    "accessibility": ("System Settings → Privacy & Security → Accessibility", ACCESSIBILITY_SETTINGS_URL),
    "screen_recording": ("System Settings → Privacy & Security → Screen & System Audio Recording", SCREEN_RECORDING_SETTINGS_URL),
}


def permission_guidance(missing: list[str]) -> dict:
    """빠진 권한 > doctor 응답 칸 (host_app · grant · open_settings · note · ask_user)"""
    host = find_host_app()
    label = host_app_label(host)
    grant = {key: f"{PERMISSION_SETTINGS[key][0]} → add (+) and turn on {label}" if key in PERMISSION_SETTINGS else key
             for key in missing}
    return {"host_app": host, "grant": grant,
            "open_settings": [f"open \"{PERMISSION_SETTINGS[key][1]}\"" for key in missing if key in PERMISSION_SETTINGS],
            "note": "Only a person can grant these: the agent cannot switch them on for its own host app "
                    "(pressing System Settings needs the same permissions and macOS asks for the user's password). "
                    "Grant both once: desktop click · type · press · focus need Screen Recording too, even with Accessibility on. "
                    "Quit and reopen the host app afterwards",
            "ask_user": f"Please turn on {' and '.join(missing)} for {label} in System Settings → Privacy & Security, "
                        "then quit and reopen it. I cannot grant these to myself"}
