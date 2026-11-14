"""Find the macOS host app that needs permissions: Accessibility and Screen Recording go to the app that launched the agent, not python3 (#1132)
Search order: outermost .app among ancestor processes > __CFBundleIdentifier > None
"""
from __future__ import annotations

import os
import re
import sys

from pro_launch.runtime import procs

# Outermost app bundle in a path (Cursor.app/…/Cursor Helper.app gives Cursor.app)
OUTERMOST_APP_BUNDLE_PATTERN = re.compile(r"(/(?:[^/]+/)*?([^/]+)\.app)/Contents/")
# Bundle ID launchd passes to children of GUI apps (when no app is among ancestors, e.g. tmux)
BUNDLE_ID_ENV_VAR = "__CFBundleIdentifier"
# Max ancestor-chain depth (guards against ppid cycles)
MAXIMUM_ANCESTOR_DEPTH = 64
# Open the System Settings pane directly (where a person turns it on)
ACCESSIBILITY_SETTINGS_URL = "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
SCREEN_RECORDING_SETTINGS_URL = "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"


def app_bundle_in(command: str) -> tuple[str, str] | None:
    """Command line > (app name, bundle path). None outside an app bundle"""
    match = OUTERMOST_APP_BUNDLE_PATTERN.search(command or "")
    return (match.group(2), match.group(1)) if match else None


def find_host_app() -> dict | None:
    """Permission target app > {name, path, bundle_id, found_by}. None if not macOS or not found"""
    if sys.platform != "darwin":
        return None
    bundle_id = os.environ.get(BUNDLE_ID_ENV_VAR) or None
    outermost = None
    # The topmost ancestor's app is the TCC responsible app (above child Helper apps)
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
    """App name shown to people. Generic wording if unknown"""
    if not host:
        return "the app that runs this agent (Terminal, iTerm, Paseo, Cursor, VS Code…)"
    return f"{host['name']} ({host['path']})" if host.get("path") else host["name"]


# Permission name > (settings menu path, direct-open URL)
PERMISSION_SETTINGS = {
    "accessibility": ("System Settings → Privacy & Security → Accessibility", ACCESSIBILITY_SETTINGS_URL),
    "screen_recording": ("System Settings → Privacy & Security → Screen & System Audio Recording", SCREEN_RECORDING_SETTINGS_URL),
}


def permission_guidance(missing: list[str]) -> dict:
    """Missing permission > doctor response fields (host_app, grant, open_settings, note, ask_user)"""
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
