"""Booting virtual devices: iOS simulator · Android emulator — window mode (headless · small · normal) and window size decided in one place.

Motivated by the simulator window filling the MacBook screen and using resources and disk. Capture size is independent of window size
(capture reads the device screen directly and shrinks with --max-side). The window is only needed when a person debugs.

**A Simulator.app used by another session is never closed.** If it is running, the window size cannot change and `window_scale_pending` reports it.
"""
from __future__ import annotations

import json
import plistlib
import re
import shutil
import subprocess
import time
from pathlib import Path

from common.proc import sdk_tool
from common.state import MACHINE_BUCKET, base_dir

from pro_launch.runtime import procs

WINDOW_MODES = ("headless", "small", "normal")
# Default scale for small — big enough to debug, small enough not to cover the screen
SMALL_WINDOW_SCALE = 0.4
WINDOW_SCALE_MINIMUM = 0.3
WINDOW_SCALE_MAXIMUM = 1.0
SIMULATOR_PREFERENCES_DOMAIN = "com.apple.iphonesimulator"
SIMCTL_BOOT_TIMEOUT_SECONDS = 90
SIMCTL_BOOTSTATUS_TIMEOUT_SECONDS = 240
SIMCTL_QUICK_TIMEOUT_SECONDS = 30
# Limit for waiting until the emulator appears in adb (s)
EMULATOR_APPEAR_TIMEOUT_SECONDS = 120
EMULATOR_PORT_FIRST, EMULATOR_PORT_LAST = 5554, 5584
# "No acceleration" signs in the emulator log — boot never finishes in this state
EMULATOR_NO_ACCELERATION_MARKERS = ("hvf is not enabled", "qemu_mprotect__osdep: mprotect failed")
# Host CPU virtualization itself is off (BIOS VT-x/AMD-V · Windows hypervisor · Linux KVM) — the emulator exits right away (#987)
EMULATOR_NO_VIRTUALIZATION_MARKERS = ("requires hardware acceleration", "kvm is required to run this avd",
                                      "/dev/kvm is not found", "/dev/kvm device: permission denied")
# Log tail attached to failed responses (lines · max characters)
EMULATOR_LOG_TAIL_LINES = 20
EMULATOR_LOG_TAIL_MAX_CHARACTERS = 2000
SIMULATOR_WINDOW_HINT = ("Shrink it with Simulator's Window menu > Physical Size / Fit Screen "
                         "(an already open Simulator.app may be used by another session, so it is not quit)")
_UDID_PATTERN = re.compile(r"^[0-9A-Fa-f]{8}-(?:[0-9A-Fa-f]{4}-){3}[0-9A-Fa-f]{12}$")


def resolve_window(window: str | None, scale: float | None) -> tuple[str, float | None]:
    """(window mode, scale). No mode means headless; scale alone means small. Default small scale 0.4; normal keeps the default size (None)."""
    mode = window or ("small" if scale is not None else "headless")
    if mode == "headless":
        return mode, None
    if scale is not None:
        return mode, scale
    return mode, SMALL_WINDOW_SCALE if mode == "small" else None


def is_valid_scale(scale: float | None) -> bool:
    return scale is None or WINDOW_SCALE_MINIMUM <= scale <= WINDOW_SCALE_MAXIMUM


def _run(command: list[str], timeout: int) -> tuple[bool, str]:
    try:
        r = subprocess.run(command, capture_output=True, text=True, errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, f"no response ({timeout}s)"
    except OSError as error:
        return False, str(error)
    return r.returncode == 0, ((r.stdout or "") + (r.stderr or "")).replace("\r", "").strip()


# ── iOS ──────────────────────────────────────────────────────────────────


def ios_simulators() -> list[dict]:
    """Simulators simctl knows > [{udid, name, state, runtime}]. Available ones only."""
    if not shutil.which("xcrun"):
        return []
    is_ok, text = _run(["xcrun", "simctl", "list", "devices", "available", "-j"], SIMCTL_QUICK_TIMEOUT_SECONDS)
    try:
        groups = json.loads(text).get("devices", {}) if is_ok else {}
    except json.JSONDecodeError:
        return []
    return [{"udid": d.get("udid"), "name": d.get("name"), "state": d.get("state"), "runtime": runtime}
            for runtime, devices in groups.items() for d in devices if d.get("udid")]


def is_udid(value: str | None) -> bool:
    return bool(_UDID_PATTERN.match(value or ""))


def find_ios_simulators(value: str) -> list[dict]:
    """Simulators matching the UDID exactly, otherwise the name exactly (names can repeat)."""
    simulators = ios_simulators()
    if is_udid(value):
        return [s for s in simulators if s["udid"].lower() == value.lower()]
    return [s for s in simulators if s["name"] == value]


def is_simulator_app_running() -> bool:
    is_ok, _ = _run(["pgrep", "-x", "Simulator"], 5)
    return is_ok


def _read_simulator_preferences() -> dict:
    try:
        r = subprocess.run(["defaults", "export", SIMULATOR_PREFERENCES_DOMAIN, "-"], capture_output=True,
                           timeout=SIMCTL_QUICK_TIMEOUT_SECONDS)
        return plistlib.loads(r.stdout) if r.returncode == 0 and r.stdout else {}
    except (OSError, subprocess.SubprocessError, plistlib.InvalidFileException, ValueError):
        return {}


def write_window_scale(udid: str, scale: float) -> tuple[bool, str]:
    """Write the simulator's window scale to preferences. Only meaningful while Simulator.app is closed.

    DevicePreferences.<UDID>.SimulatorWindowGeometry.<screen id>.WindowScale — the screen id is borrowed from an existing entry.
    """
    device_preferences = _read_simulator_preferences().get("DevicePreferences") or {}
    entry = dict(device_preferences.get(udid) or {})
    geometry = dict(entry.get("SimulatorWindowGeometry") or {})
    screen_id = next(iter(geometry), None) or next(
        (next(iter(other.get("SimulatorWindowGeometry") or {}), None) for other in device_preferences.values()
         if isinstance(other, dict) and other.get("SimulatorWindowGeometry")), None)
    if screen_id is None:
        return False, "screen id unknown (Simulator.app has never been opened on this Mac)"
    geometry[screen_id] = {**(geometry.get(screen_id) or {}), "WindowScale": float(scale)}
    entry["SimulatorWindowGeometry"] = geometry
    return _run(["defaults", "write", SIMULATOR_PREFERENCES_DOMAIN, "DevicePreferences", "-dict-add", udid,
                 plistlib.dumps(entry, fmt=plistlib.FMT_XML).decode("utf-8")], SIMCTL_QUICK_TIMEOUT_SECONDS)


def boot_ios(udid: str, window: str, scale: float | None) -> dict:
    """Boot a simulator: (write window scale) > simctl boot > wait for bootstatus > (in window mode open only that device).

    Changes nothing if already booted. > {is_ok, already_booted, window, scale, window_scale_pending, ...}
    """
    state = next((s["state"] for s in ios_simulators() if s["udid"] == udid), None)
    result = {"is_ok": True, "udid": udid, "window": window, "scale": scale, "already_booted": state == "Booted",
              "window_scale_pending": False, "window_opened": False}
    if state == "Booted":
        return result
    is_simulator_running = is_simulator_app_running()
    if window != "headless" and scale is not None:
        is_written, detail = write_window_scale(udid, scale)
        result["window_scale_written"] = is_written
        if not is_written:
            result["window_scale_detail"] = detail[-200:]
        # With Simulator.app running, there is no way to confirm the new window uses the value
        result["window_scale_pending"] = is_simulator_running
    is_booted, detail = _run(["xcrun", "simctl", "boot", udid], SIMCTL_BOOT_TIMEOUT_SECONDS)
    if not is_booted and "current state: Booted" not in detail:
        return {**result, "is_ok": False, "step": "boot", "detail": detail[-300:]}
    is_ready, detail = _run(["xcrun", "simctl", "bootstatus", udid, "-b"], SIMCTL_BOOTSTATUS_TIMEOUT_SECONDS)
    if not is_ready:
        return {**result, "is_ok": False, "step": "bootstatus", "detail": detail[-300:]}
    if window != "headless" and not is_simulator_running:
        # Open only this device's window (other device windows stay closed)
        _run(["open", "-a", "Simulator", "--args", "-CurrentDeviceUDID", udid], SIMCTL_QUICK_TIMEOUT_SECONDS)
        result["window_opened"] = True
    if is_simulator_running:
        result["simulator_app_running"] = True
        result["window_hint"] = SIMULATOR_WINDOW_HINT
    return result


def shutdown_ios(udid: str) -> tuple[bool, str]:
    is_ok, detail = _run(["xcrun", "simctl", "shutdown", udid], SIMCTL_BOOT_TIMEOUT_SECONDS)
    # Already being off is not a failure
    return is_ok or "current state: Shutdown" in detail, detail


# ── Android ──────────────────────────────────────────────────────────────


def adb_serials() -> list[str]:
    """Every serial from adb devices (including offline)."""
    adb = sdk_tool("adb")
    if not adb:
        return []
    is_ok, text = _run([adb, "devices"], SIMCTL_QUICK_TIMEOUT_SECONDS)
    return [line.split()[0] for line in text.splitlines()[1:] if len(line.split()) >= 2] if is_ok else []


def emulator_avd_name(serial: str) -> str | None:
    """AVD name of a running emulator. None if not an emulator."""
    adb = sdk_tool("adb")
    if not adb or not serial.startswith("emulator-"):
        return None
    is_ok, text = _run([adb, "-s", serial, "emu", "avd", "name"], SIMCTL_QUICK_TIMEOUT_SECONDS)
    first_line = text.splitlines()[0].strip() if is_ok and text else ""
    return first_line if first_line and first_line != "OK" else None


def running_emulators() -> dict[str, str]:
    """{serial: AVD name} (ones whose name cannot be read are skipped)."""
    return {s: n for s in adb_serials() if s.startswith("emulator-") and (n := emulator_avd_name(s))}


def _free_emulator_port() -> int | None:
    used = {int(m.group(1)) for s in adb_serials() if (m := re.match(r"emulator-(\d+)$", s))}
    return next((p for p in range(EMULATOR_PORT_FIRST, EMULATOR_PORT_LAST + 1, 2) if p not in used), None)


def emulator_log_path(avd: str) -> Path:
    path = base_dir() / "launch" / MACHINE_BUCKET
    path.mkdir(parents=True, exist_ok=True)
    return path / f"emulator-{re.sub(r'[^A-Za-z0-9._-]', '_', avd)}.log"


def emulator_command(emulator: str, avd: str, window: str, scale: float | None, is_cold: bool,
                     port: int) -> list[str]:
    """emulator args: -no-window for headless, -scale for window modes. Cold boot does not load snapshots."""
    command = [emulator, "-avd", avd, "-port", str(port)]
    if window == "headless":
        command.append("-no-window")
    elif scale is not None:
        command += ["-scale", str(scale)]
    if is_cold:
        command.append("-no-snapshot-load")
    return command


def launch_emulator(avd: str, window: str, scale: float | None, is_cold: bool,
                    port: int | None = None) -> dict:
    """Start the emulator in the background > {is_ok, serial, pid, command, log}. Waiting for readiness is up to the caller."""
    emulator = sdk_tool("emulator")
    if not emulator:
        return {"is_ok": False, "detail": "emulator not found (check emulator_path in doctor)"}
    chosen_port = port or _free_emulator_port()
    if chosen_port is None:
        return {"is_ok": False, "detail": "no free emulator port (5554-5584)"}
    command = emulator_command(emulator, avd, window, scale, is_cold, chosen_port)
    log = emulator_log_path(avd)
    pid = procs.spawn_detached(command, str(Path(emulator).parent), log, is_stdout_logged=True)
    return {"is_ok": True, "serial": f"emulator-{chosen_port}", "pid": pid, "command": command, "log": str(log)}


def emulator_start_problem(log_path: str | Path | None) -> str | None:
    """Signs in the emulator log that boot will never finish > description. None if none.

    Without hardware acceleration (HVF) it falls back to software mode, repeatedly failing mprotect and stalling offline —
    observed: on a host with nearly full swap (28.9/29.7GB) it could not get new VM memory. Waiting does not help.
    """
    try:
        text = Path(log_path).read_text(encoding="utf-8", errors="replace") if log_path else ""
    except OSError:
        return None
    lowered_text = text.lower()
    if any(marker in lowered_text for marker in EMULATOR_NO_VIRTUALIZATION_MARKERS):
        return ("the host has no CPU virtualization for the emulator — turn on VT-x / AMD-V (SVM) in the BIOS/UEFI, "
                "and on Windows enable Windows Hypervisor Platform. Waiting will not help; ask the user")
    if any(marker in text for marker in EMULATOR_NO_ACCELERATION_MARKERS):
        return ("the emulator got no hardware acceleration (HVF) and stalled in software mode — this happens when host memory or swap runs low. "
                "Run fewer virtual devices or free memory, then start it again")
    return None


def emulator_log_tail(log_path: str | Path | None) -> str:
    """Last few lines of the emulator log (to see the failure cause without opening the log file, #987). Empty string if unreadable"""
    try:
        text = Path(log_path).read_text(encoding="utf-8", errors="replace") if log_path else ""
    except OSError:
        return ""
    return "\n".join(text.splitlines()[-EMULATOR_LOG_TAIL_LINES:])[-EMULATOR_LOG_TAIL_MAX_CHARACTERS:]


def _failed_to_appear(problem: str | None, log_path, pid: int | None) -> dict:
    """Did not appear > {is_ok, problem, log_tail, process_alive}. process_alive is None if pid is unknown"""
    return {"is_ok": False, "problem": problem, "log_tail": emulator_log_tail(log_path),
            "process_alive": procs.pid_alive(pid) if pid else None}


def wait_for_emulator(serial: str, log_path: str | Path | None = None,
                      timeout_seconds: float = EMULATOR_APPEAR_TIMEOUT_SECONDS, pid: int | None = None) -> dict:
    """Until adb sees that serial in device state > {is_ok, problem(, log_tail, process_alive)}. Ends right away if the log shows stall signs."""
    adb = sdk_tool("adb")
    deadline = time.monotonic() + timeout_seconds
    while adb and time.monotonic() < deadline:
        _, text = _run([adb, "devices"], SIMCTL_QUICK_TIMEOUT_SECONDS)
        if any(line.split()[:2] == [serial, "device"] for line in text.splitlines()[1:]):
            return {"is_ok": True, "problem": None}
        if (problem := emulator_start_problem(log_path)):
            return _failed_to_appear(problem, log_path, pid)
        time.sleep(2)
    return _failed_to_appear(emulator_start_problem(log_path), log_path, pid)


def kill_emulator(serial: str, avd: str) -> dict:
    """Stop the emulator: adb emu kill > force-kill qemu if it does not die. > {killed_by, forced_pids, is_gone}"""
    adb = sdk_tool("adb")
    pids = procs.process_ids_with_arguments("-avd", avd)
    if adb:
        _run([adb, "-s", serial, "emu", "kill"], SIMCTL_QUICK_TIMEOUT_SECONDS)
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline and any(procs.pid_alive(p) for p in pids):
        time.sleep(1)
    survivors = [p for p in pids if procs.pid_alive(p)]
    # emu kill is ignored (qemu unresponsive under host memory pressure, observed) — force kill
    still_alive = [p for p in survivors if procs.force_kill(p)]
    return {"killed_by": "emu_kill" if not survivors else "force_kill", "forced_pids": survivors,
            "is_gone": not still_alive}
