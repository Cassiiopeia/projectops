"""Platform backends that tap, swipe and read app screens (#826).

launch_cli.py `app tap|swipe|tree` calls only this module. Every platform difference lives here.

Design
- **Finding by screen element is the default** (text, id, accessibility description). The agent reads coordinates
  off a downscaled capture, so pixel coordinates drift from device resolution. Coordinates are taken only as 0-1 ratios.
- Every backend returns **nodes of the same shape** — {text, id, desc, clickable, bounds, center}.
  So launch_cli and the agent need not know the platform.

Adding a platform (e.g. physical iOS via idb)
1. Make a class that inherits `Backend` and fill in the needed methods.
2. Register it in `BACKENDS` below under the platform name (must match the name `_pick_device` returns).
3. Add device-free unit tests to tests/test_launch_cli.py. If a real device is needed, mark it local_only.
Full contract: references/extending.md.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from common.proc import sdk_tool

import maestro_session
# Node matching lives in one platform-shared matcher (exact > normalized · per line > contains, text <-> desc)
from node_match import match_nodes  # noqa: F401

BOUNDS = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")
# (start, end) ratios — move 15% inside the edges to avoid edge gestures (back, pull-down notifications)
SWIPE_DIRS = {
    "up": ((0.5, 0.75), (0.5, 0.25)), "down": ((0.5, 0.25), (0.5, 0.75)),
    "left": ((0.85, 0.5), (0.15, 0.5)), "right": ((0.15, 0.5), (0.85, 0.5)),
}
SELECTOR_FIELDS = ("text", "id", "desc")
# Env vars Maestro reads as ${...} in a flow (only the MAESTRO_ prefix passes through from the shell)
INPUT_TEXT_ENV = "MAESTRO_PRO_LAUNCH_INPUT_TEXT"
# Reading the Android screen tree: max wait per attempt (s) · attempts · pause before retry (s)
UI_DUMP_TIMEOUT_SECONDS = 20
UI_DUMP_ATTEMPT_COUNT = 2
UI_DUMP_RETRY_DELAY_SECONDS = 1.5
# Output when uiautomator cannot attach to UiAutomation (another automation tool holds it, or the system is restarting)
UI_AUTOMATION_FAILURE_MARKERS = ("Killed", "UiAutomation", "TimeoutException", "already registered")
# Output when there is no focused window (screen off · locked · switching, seen right after reboot) — wake and retry usually clears it
NO_FOCUSED_WINDOW_MARKER = "null root node"
NO_FOCUSED_WINDOW_ATTEMPT_COUNT = 3


# ── Shared pure functions (tested without a device) ─────────────────────────────────

def parse_ratio(raw: str | None) -> tuple[float, float] | None:
    """'0.5,0.8' → (0.5, 0.8). None when out of range — blocks calls that put pixels where ratios belong."""
    if not raw:
        return None
    try:
        x, y = (float(v) for v in raw.split(","))
    except ValueError:
        return None
    return (x, y) if 0 <= x <= 1 and 0 <= y <= 1 else None


def make_node(text: str, id_: str, desc: str, clickable: bool, bounds: str) -> dict | None:
    m = BOUNDS.match(bounds or "")
    if not m:
        return None
    x1, y1, x2, y2 = map(int, m.groups())
    if x2 <= x1 or y2 <= y1:   # zero size = node not visible on screen
        return None
    return {"text": text, "id": id_, "desc": desc, "clickable": clickable,
            "bounds": [x1, y1, x2, y2], "center": [(x1 + x2) // 2, (y1 + y2) // 2]}


def ui_nodes(xml_text: str) -> list[dict]:
    """Android uiautomator dump XML → node list."""
    import xml.etree.ElementTree as ET
    # When dump goes to /dev/tty, a 'UI hierchary dumped to' notice follows the XML
    body = xml_text[xml_text.find("<"):xml_text.rfind(">") + 1]
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return []
    nodes = []
    for el in root.iter("node"):
        n = make_node(el.get("text", ""), el.get("resource-id", ""), el.get("content-desc", ""),
                      el.get("clickable") == "true", el.get("bounds", ""))
        if n:
            nodes.append(n)
    return nodes


def maestro_nodes(json_text: str) -> list[dict]:
    """`maestro hierarchy` JSON → node list. On iOS the visible text often comes in accessibilityText."""
    try:
        tree = json.loads(json_text[json_text.find("{"):])
    except ValueError:
        return []
    nodes: list[dict] = []

    def walk(n):
        a = n.get("attributes") or {}
        label = a.get("text") or a.get("accessibilityText") or ""
        if label or a.get("resource-id"):
            node = make_node(label, a.get("resource-id", ""), a.get("accessibilityText", ""),
                             True, a.get("bounds", ""))
            if node:
                nodes.append(node)
        for c in n.get("children") or []:
            walk(c)
    walk(tree)
    return nodes


def maestro_inspect_nodes(json_text: str) -> list[dict]:
    """`maestro mcp` inspect_screen response > node list (flattened into hierarchy shape and read the same way)."""
    return maestro_nodes(maestro_session.inspect_screen_to_hierarchy(json_text) or "{}")


def slim(nodes: list[dict], limit: int = 80) -> list[dict]:
    """Element list for the agent — drops parent/child duplicates and empty values to save tokens."""
    seen, outl = set(), []
    for n in nodes:
        key = (n["text"], n["id"], n["desc"])
        if key in seen:
            continue
        seen.add(key)
        outl.append({k: v for k, v in n.items() if v not in ("", None) and k != "bounds"})
    return outl[:limit]


def maestro_flow(command: dict | list[dict], app_id: str | None) -> str:
    """Maestro flow (one or more steps). The appId header is required, so a placeholder is used when unknown (the app is not launched, so it does not matter)."""
    lines = [f"appId: {app_id or 'any.app'}", "---"]
    for step in (command if isinstance(command, list) else [command]):
        (name, params), = step.items()
        if isinstance(params, dict):
            lines.append(f"- {name}:")
            lines += [f"    {k}: {json.dumps(v, ensure_ascii=False)}" for k, v in params.items()]
        else:
            lines.append(f"- {name}: {json.dumps(params, ensure_ascii=False)}")
    return "\n".join(lines) + "\n"


def pct(p: tuple[float, float]) -> str:
    return f"{round(p[0] * 100)}%,{round(p[1] * 100)}%"


# ── Backends ─────────────────────────────────────────────────────────────────

class Backend:
    """Platform backend contract. Every action returns (success, human-readable reason)."""
    name = "base"
    # True if the backend finds and taps elements itself (e.g. Maestro). If False, find via nodes() and tap with tap_xy
    selects_itself = False
    # True only on platforms with a back button (Android). iOS goes back differently per screen, so it is not taken as a step
    has_back_button = False
    install_hint: str | None = None
    # {code, reason} when the screen tree could not be read or the system is not ready (Android) — becomes the code in tree·tap·run responses
    device_failure: dict | None = None
    # Whether a resident session was used (iOS): {} no session · {"transport": ...} — attached to the response as is
    session_report: dict = {}

    def available(self) -> bool:
        return True

    def locale(self, dev: str) -> str | None:
        return None

    def nodes(self, dev: str) -> list[dict] | None:
        """Screen elements. None on platforms that cannot read them."""
        return None

    def system_readiness_failure(self, dev: str) -> dict | None:
        """{code, reason} when the device system is not ready for input. None when unknown."""
        return None

    def tap_xy(self, dev: str, x: int, y: int) -> tuple[bool, str]:
        raise NotImplementedError

    def tap_ratio(self, dev: str, rx: float, ry: float) -> tuple[bool, str]:
        raise NotImplementedError

    def tap_selector(self, dev: str, field: str, value: str) -> tuple[bool, str]:
        raise NotImplementedError

    def swipe_ratio(self, dev: str, start, end, ms: int) -> tuple[bool, str]:
        raise NotImplementedError

    def input_text(self, dev: str, value: str, submit: bool = False) -> tuple[bool, str]:
        """Type text into the focused input. The value is not left on the command line or in files."""
        raise NotImplementedError

    def press_back(self, dev: str) -> tuple[bool, str]:
        """Go back. Not implemented on platforms without a hardware back button (iOS)."""
        raise NotImplementedError

    def grab(self, dev: str) -> bytes | None:
        """Current screen PNG — used by --shot to pick the 'changed then settled' screen."""
        return None


class AndroidBackend(Backend):
    """adb + uiautomator. Built into the device, so nothing extra to install."""
    name = "android"
    has_back_button = True
    install_hint = "Install Android SDK platform-tools (adb) or set ANDROID_HOME"

    def _adb(self, dev: str, *args: str, timeout: int = 15, binary: bool = False,
             input_text: str | None = None):
        adb = sdk_tool("adb")
        return subprocess.run([adb, "-s", dev, *args], capture_output=True,
                              text=not binary, timeout=timeout, input=input_text)

    def available(self) -> bool:
        return bool(sdk_tool("adb"))

    def locale(self, dev: str) -> str | None:
        # If the user never changed the language the persist value is empty — fall back to the factory default
        for prop in ("persist.sys.locale", "ro.product.locale"):
            v = (self._adb(dev, "shell", "getprop", prop).stdout or "").strip()
            if v:
                return v
        return None

    def nodes(self, dev: str) -> list[dict]:
        """Screen tree: timeout + one retry. On failure returns [] and leaves code and reason in device_failure."""
        self.device_failure = None
        attempt_count = UI_DUMP_ATTEMPT_COUNT
        attempt = 0
        while attempt < attempt_count:
            try:
                # Read via stdout so no file is left on the device
                r = self._adb(dev, "exec-out", "uiautomator", "dump", "/dev/tty", timeout=UI_DUMP_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                self.device_failure = {"code": "ui_dump_timeout",
                                        "reason": f"uiautomator dump did not finish within {UI_DUMP_TIMEOUT_SECONDS}s"}
            else:
                if "<hierarchy" in (r.stdout or ""):
                    return ui_nodes(r.stdout)
                self.device_failure = self._dump_failure(dev, (r.stdout or "") + (r.stderr or ""))
            if self.device_failure["code"] == "no_focused_window":
                # No focused window: wake the screen, dismiss the lock, then retry (with more attempts)
                attempt_count = NO_FOCUSED_WINDOW_ATTEMPT_COUNT
                self._wake_screen(dev)
            attempt += 1
            if self.device_failure["code"] == "android_system_not_ready" or attempt == attempt_count:
                break
            time.sleep(UI_DUMP_RETRY_DELAY_SECONDS)
        return []

    def _wake_screen(self, dev: str) -> None:
        """Wake the screen + unlock (cannot unlock a password lock — failures are ignored)."""
        try:
            self._adb(dev, "shell", "input keyevent WAKEUP; wm dismiss-keyguard", timeout=10)
        except subprocess.TimeoutExpired:
            pass

    def system_readiness_failure(self, dev: str) -> dict | None:
        """Boot animation showing or no window service means the system is (re)starting (seen with repeated system_server restarts)."""
        try:
            probe = self._adb(dev, "shell", "getprop init.svc.bootanim; service check window", timeout=10).stdout or ""
        except subprocess.TimeoutExpired:
            probe = ""
        if probe.startswith("running") or "window: not found" in probe:
            return {"code": "android_system_not_ready",
                    "reason": "Android system is (re)starting — the boot animation is showing or the window service is missing"}
        return None

    def _dump_failure(self, dev: str, output: str) -> dict:
        """Classify dump failure: system restarting (boot animation) > UiAutomation attach failure > other."""
        not_ready = self.system_readiness_failure(dev)
        if not_ready:
            return not_ready
        if NO_FOCUSED_WINDOW_MARKER in output:
            return {"code": "no_focused_window",
                    "reason": "No focused window (screen off, locked or switching) — if it persists after waking, look at the screen with app shot"}
        if any(marker in output for marker in UI_AUTOMATION_FAILURE_MARKERS):
            return {"code": "ui_automation_unavailable",
                    "reason": "uiautomator could not attach to UiAutomation (another automation tool holds it, or the system is unstable)"}
        return {"code": "ui_dump_failed", "reason": (output.strip()[-200:] or "empty output")}

    def _size(self, dev: str) -> tuple[int, int] | None:
        """Screen size. If an Override exists it is the real input coordinate space, so the last value is used."""
        sizes = re.findall(r"(\d+)x(\d+)", self._adb(dev, "shell", "wm", "size").stdout or "")
        return (int(sizes[-1][0]), int(sizes[-1][1])) if sizes else None

    def tap_xy(self, dev, x, y):
        r = self._adb(dev, "shell", "input", "tap", str(x), str(y))
        return r.returncode == 0, (r.stderr or "").strip()

    def tap_ratio(self, dev, rx, ry):
        size = self._size(dev)
        if not size:
            return False, "Could not read wm size"
        return self.tap_xy(dev, round(rx * size[0]), round(ry * size[1]))

    def swipe_ratio(self, dev, start, end, ms):
        size = self._size(dev)
        if not size:
            return False, "Could not read wm size"
        pts = [round(start[0] * size[0]), round(start[1] * size[1]),
               round(end[0] * size[0]), round(end[1] * size[1])]
        r = self._adb(dev, "shell", "input", "swipe", *map(str, pts), str(ms))
        return r.returncode == 0, (r.stderr or "").strip()

    def input_text(self, dev, value, submit=False):
        # Spaces become `%s`. The value is read from stdin and used only inside quotes (never on the command line or exposed to shell metacharacters)
        r = self._adb(dev, "shell", 'IFS= read -r T; input text "$T"', timeout=30,
                      input_text=value.replace(" ", "%s") + "\n")
        if r.returncode == 0 and submit:
            r = self._adb(dev, "shell", "input", "keyevent", "66")   # 66 = Enter
        return r.returncode == 0, (r.stderr or "").strip()

    def press_back(self, dev):
        r = self._adb(dev, "shell", "input", "keyevent", "4")   # 4 = back
        return r.returncode == 0, (r.stderr or "").strip()

    def grab(self, dev):
        # exec-out returns binary as is. Reading via shell changes line endings and breaks the PNG
        r = self._adb(dev, "exec-out", "screencap", "-p", timeout=30, binary=True)
        return r.stdout if r.stdout.startswith(b"\x89PNG") else None


class IOSMaestroBackend(Backend):
    """iOS simulator. simctl has no tap or screen-tree commands, so this delegates to Maestro (open-source E2E).

    Each call starts a fresh Maestro (JVM) and takes 10-40 s. Run long scenarios as the project's Maestro flows.
    """
    name = "ios"
    selects_itself = True
    install_hint = 'curl -fsSL "https://get.maestro.mobile.dev" | bash'

    def __init__(self, app_id: str | None = None, timeout: int = 90):
        self.app_id, self.timeout = app_id, timeout
        # Did it use a resident session (app session start): {} no session · {"transport": "session"} · fell back + reason
        self.session_report: dict = {}

    def has_session(self, dev: str) -> bool:
        """Is a resident session ready for this device (whether the relay is alive is only known by calling it)."""
        return maestro_session.is_ready(maestro_session.read_session(dev))

    def _session_call(self, dev: str, tool: str, arguments: dict) -> dict | None:
        """Call through the session > result. None when there is no usable session (reason goes in session_report)."""
        result, fallback_reason = maestro_session.call(dev, tool, arguments, self.timeout)
        if result is not None:
            self.session_report = {"transport": "session", **({"session_reconnected": True} if result["reconnected"] else {})}
        elif fallback_reason:
            self.session_report = {"transport": "per_call", "session_fallback": fallback_reason}
        return result

    @staticmethod
    def _maestro() -> str | None:
        p = shutil.which("maestro") or str(Path.home() / ".maestro" / "bin" / "maestro")
        return p if Path(p).exists() else None

    def available(self) -> bool:
        return bool(self._maestro())

    def _base(self, dev: str) -> list[str]:
        return [self._maestro()] + (["--device", dev] if dev != "booted" else [])

    def locale(self, dev):
        r = subprocess.run(["xcrun", "simctl", "spawn", dev, "defaults", "read", "-g", "AppleLanguages"],
                           capture_output=True, text=True, errors="replace", timeout=15)
        m = re.search(r'"?([A-Za-z]{2}(?:-[A-Za-z]+)?)"?', r.stdout or "")
        return m.group(1) if m else None

    def nodes(self, dev):
        result = self._session_call(dev, "inspect", {})
        if result is not None and not result["is_error"]:
            return maestro_inspect_nodes(result["text"])
        if result is not None:
            self.session_report = {"transport": "per_call", "session_fallback": "session_inspect_failed"}
        try:
            r = maestro_session.run_recorded(self._base(dev) + ["hierarchy"], capture_output=True, text=True, errors="replace",
                               timeout=self.timeout)
        except subprocess.TimeoutExpired:
            return []
        return maestro_nodes(r.stdout or "")

    def run_flow(self, dev: str, command: dict | list[dict], env: dict | None = None) -> tuple[bool | None, list[str]]:
        """Run a flow once > (success, output lines). On timeout (None, [reason]) — used by the step-result reader (app run).

        Uses the resident session when there is one (except flows with env — secrets are not sent through the session, see maestro_session.py).
        """
        if not env:
            result = self._session_call(dev, "run", {"yaml": maestro_flow(command, self.app_id)})
            if result is not None:
                return maestro_session.flow_outcome(result)
        elif self.has_session(dev):
            # A per-call maestro test drops the session's device connection — the session reattaches on the next call
            self.session_report = {"transport": "per_call", "session_fallback": "secret_input_per_call"}
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "step.yaml"
            f.write_text(maestro_flow(command, self.app_id), encoding="utf-8")
            # Flow with secrets: Maestro writes the real inputText value to maestro.log (observed) —
            # redirect logs into this temp folder and delete them together (so nothing stays in the default ~/.maestro/tests)
            debug_output = ["--debug-output", str(Path(d) / "debug"), "--flatten-debug-output"] if env else []
            try:
                r = maestro_session.run_recorded(self._base(dev) + ["test", *debug_output, str(f)], capture_output=True,
                                   text=True, errors="replace", timeout=self.timeout,
                                   env={**os.environ, **env} if env else None)
            except subprocess.TimeoutExpired:
                return None, [f"maestro did not respond ({self.timeout}s)"]
        # Maestro prints an ad box (│ ╭ ╰) at the end. Strip it so the failure line is visible
        lines = [l for l in ((r.stdout or "") + (r.stderr or "")).splitlines()
                 if l.strip() and not l.lstrip().startswith(("│", "╭", "╰"))]
        return r.returncode == 0, lines

    def _run(self, dev: str, command: dict | list[dict], env: dict | None = None) -> tuple[bool, str]:
        is_success, lines = self.run_flow(dev, command, env)
        if is_success is None:
            return False, lines[0]
        reason = [l for l in lines if "FAILED" in l or "not found" in l.lower() or "Error" in l]
        return is_success, "\n".join((reason or lines)[-6:])

    def tap_selector(self, dev, field, value):
        # Maestro text and id are regexes. Match literally so text with parentheses or question marks does not match the wrong thing
        key = "id" if field == "id" else "text"
        return self._run(dev, {"tapOn": {key: re.escape(value)}})

    def tap_xy(self, dev, x, y):
        # Tree coordinates are in points — same as Maestro absolute coordinates
        return self._run(dev, {"tapOn": {"point": f"{x},{y}"}})

    def tap_ratio(self, dev, rx, ry):
        return self._run(dev, {"tapOn": {"point": pct((rx, ry))}})

    def swipe_ratio(self, dev, start, end, ms):
        return self._run(dev, {"swipe": {"start": pct(start), "end": pct(end), "duration": ms}})

    def input_text(self, dev, value, submit=False):
        # Values pass only via MAESTRO_-prefixed env vars — no plaintext left in the flow file or command line (-e)
        steps: list[dict] = [{"inputText": "${" + INPUT_TEXT_ENV + "}"}]
        if submit:
            steps.append({"pressKey": "Enter"})
        return self._run(dev, steps, env={INPUT_TEXT_ENV: value})

    def grab(self, dev):
        r = subprocess.run(["xcrun", "simctl", "io", dev, "screenshot", "--type=png", "-"],
                           capture_output=True, timeout=30)
        return r.stdout if r.stdout.startswith(b"\x89PNG") else None


# Platform name → backend factory. Must match the names launch_cli._pick_device returns
BACKENDS = {
    "android": lambda app_id=None: AndroidBackend(),
    "ios": lambda app_id=None: IOSMaestroBackend(app_id=app_id),
}


def get_backend(platform: str, app_id: str | None = None) -> Backend | None:
    make = BACKENDS.get(platform)
    return make(app_id) if make else None
