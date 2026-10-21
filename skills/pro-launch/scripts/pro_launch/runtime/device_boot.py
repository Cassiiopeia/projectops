"""가상 기기 띄우기: iOS 시뮬레이터 · Android 에뮬레이터 — 창 모드(headless · small · normal)와 창 크기를 한 곳에서 정한다.

시뮬레이터 창이 맥북 화면을 가득 채워 자원과 디스크를 쓰는 문제가 근거다. 캡처 크기는 창 크기와 무관하다
(캡처는 기기 화면을 그대로 읽고 --max-side 로 줄인다). 창은 사람이 디버깅할 때만 필요하다.

**다른 세션이 쓰는 Simulator.app 은 끄지 않는다.** 떠 있으면 창 크기를 못 바꾸고 `window_scale_pending` 으로 알린다.
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
# small 의 기본 배율 — 디버깅은 되고 화면은 안 덮는 크기
SMALL_WINDOW_SCALE = 0.4
WINDOW_SCALE_MINIMUM = 0.3
WINDOW_SCALE_MAXIMUM = 1.0
SIMULATOR_PREFERENCES_DOMAIN = "com.apple.iphonesimulator"
SIMCTL_BOOT_TIMEOUT_SECONDS = 90
SIMCTL_BOOTSTATUS_TIMEOUT_SECONDS = 240
SIMCTL_QUICK_TIMEOUT_SECONDS = 30
# 에뮬레이터가 adb 에 나타나기를 기다리는 한도 (초)
EMULATOR_APPEAR_TIMEOUT_SECONDS = 120
EMULATOR_PORT_FIRST, EMULATOR_PORT_LAST = 5554, 5584
# 에뮬레이터 로그의 "가속 없음" 징후 — 이 상태는 부팅이 끝나지 않는다
EMULATOR_NO_ACCELERATION_MARKERS = ("hvf is not enabled", "qemu_mprotect__osdep: mprotect failed")
SIMULATOR_WINDOW_HINT = ("Shrink it with Simulator's Window menu > Physical Size / Fit Screen "
                         "(an already open Simulator.app may be used by another session, so it is not quit)")
_UDID_PATTERN = re.compile(r"^[0-9A-Fa-f]{8}-(?:[0-9A-Fa-f]{4}-){3}[0-9A-Fa-f]{12}$")


def resolve_window(window: str | None, scale: float | None) -> tuple[str, float | None]:
    """(창 모드, 배율). 모드를 안 주면 headless, 배율만 주면 small. small 의 배율 기본은 0.4, normal 은 기본 크기 그대로(None)."""
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
        r = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, f"no response ({timeout}s)"
    except OSError as error:
        return False, str(error)
    return r.returncode == 0, ((r.stdout or "") + (r.stderr or "")).replace("\r", "").strip()


# ── iOS ──────────────────────────────────────────────────────────────────


def ios_simulators() -> list[dict]:
    """simctl 이 아는 시뮬레이터 > [{udid, name, state, runtime}]. 사용 가능한 것만."""
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
    """UDID 정확히, 아니면 이름 정확히 일치하는 시뮬레이터들 (이름은 여러 개일 수 있다)."""
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
    """그 시뮬레이터의 창 배율을 환경설정에 쓴다. Simulator.app 이 꺼져 있을 때만 의미가 있다.

    DevicePreferences.<UDID>.SimulatorWindowGeometry.<화면 id>.WindowScale — 화면 id 는 이미 있는 항목에서 빌린다.
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
    """시뮬레이터 부팅: (창 배율 쓰기) > simctl boot > bootstatus 대기 > (창 모드면 그 기기만 연다).

    이미 켜져 있으면 아무것도 바꾸지 않는다. > {is_ok, already_booted, window, scale, window_scale_pending, ...}
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
        # Simulator.app 이 떠 있으면 새 창이 쓰는 값인지 확인할 수 없다
        result["window_scale_pending"] = is_simulator_running
    is_booted, detail = _run(["xcrun", "simctl", "boot", udid], SIMCTL_BOOT_TIMEOUT_SECONDS)
    if not is_booted and "current state: Booted" not in detail:
        return {**result, "is_ok": False, "step": "boot", "detail": detail[-300:]}
    is_ready, detail = _run(["xcrun", "simctl", "bootstatus", udid, "-b"], SIMCTL_BOOTSTATUS_TIMEOUT_SECONDS)
    if not is_ready:
        return {**result, "is_ok": False, "step": "bootstatus", "detail": detail[-300:]}
    if window != "headless" and not is_simulator_running:
        # 이 기기 창만 연다 (다른 기기 창은 열지 않는다)
        _run(["open", "-a", "Simulator", "--args", "-CurrentDeviceUDID", udid], SIMCTL_QUICK_TIMEOUT_SECONDS)
        result["window_opened"] = True
    if is_simulator_running:
        result["simulator_app_running"] = True
        result["window_hint"] = SIMULATOR_WINDOW_HINT
    return result


def shutdown_ios(udid: str) -> tuple[bool, str]:
    is_ok, detail = _run(["xcrun", "simctl", "shutdown", udid], SIMCTL_BOOT_TIMEOUT_SECONDS)
    # 이미 꺼져 있던 것은 실패가 아니다
    return is_ok or "current state: Shutdown" in detail, detail


# ── Android ──────────────────────────────────────────────────────────────


def adb_serials() -> list[str]:
    """adb devices 의 모든 시리얼 (offline 포함)."""
    adb = sdk_tool("adb")
    if not adb:
        return []
    is_ok, text = _run([adb, "devices"], SIMCTL_QUICK_TIMEOUT_SECONDS)
    return [line.split()[0] for line in text.splitlines()[1:] if len(line.split()) >= 2] if is_ok else []


def emulator_avd_name(serial: str) -> str | None:
    """실행 중인 에뮬레이터의 AVD 이름. 에뮬레이터가 아니면 None."""
    adb = sdk_tool("adb")
    if not adb or not serial.startswith("emulator-"):
        return None
    is_ok, text = _run([adb, "-s", serial, "emu", "avd", "name"], SIMCTL_QUICK_TIMEOUT_SECONDS)
    first_line = text.splitlines()[0].strip() if is_ok and text else ""
    return first_line if first_line and first_line != "OK" else None


def running_emulators() -> dict[str, str]:
    """{시리얼: AVD 이름} (이름을 못 읽은 것은 뺀다)."""
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
    """emulator 인자: headless 는 -no-window, 창 모드는 -scale. 콜드 부팅은 스냅샷을 읽지 않는다."""
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
    """에뮬레이터를 백그라운드로 띄운다 > {is_ok, serial, pid, command, log}. 준비 완료 대기는 부르는 쪽이 한다."""
    emulator = sdk_tool("emulator")
    if not emulator:
        return {"is_ok": False, "detail": "emulator not found (check emulator_path in doctor)"}
    chosen_port = port or _free_emulator_port()
    if chosen_port is None:
        return {"is_ok": False, "detail": "no free emulator port (5554-5584)"}
    command = emulator_command(emulator, avd, window, scale, is_cold, chosen_port)
    log = emulator_log_path(avd)
    pid = procs.spawn_detached(command, str(Path(emulator).parent), log)
    return {"is_ok": True, "serial": f"emulator-{chosen_port}", "pid": pid, "command": command, "log": str(log)}


def emulator_start_problem(log_path: str | Path | None) -> str | None:
    """에뮬레이터 로그에서 부팅이 끝나지 않을 징후 > 설명. 없으면 None.

    하드웨어 가속(HVF)을 못 얻으면 소프트웨어 모드로 떨어져 mprotect 실패를 반복하며 offline 에 멈춘다 —
    실측: 스왑이 거의 찬 호스트(28.9/29.7GB)에서 새 VM 메모리를 못 받았다. 기다려도 끝나지 않는다.
    """
    try:
        text = Path(log_path).read_text(encoding="utf-8", errors="replace") if log_path else ""
    except OSError:
        return None
    if any(marker in text for marker in EMULATOR_NO_ACCELERATION_MARKERS):
        return ("the emulator got no hardware acceleration (HVF) and stalled in software mode — this happens when host memory or swap runs low. "
                "Run fewer virtual devices or free memory, then start it again")
    return None


def wait_for_emulator(serial: str, log_path: str | Path | None = None,
                      timeout_seconds: float = EMULATOR_APPEAR_TIMEOUT_SECONDS) -> dict:
    """adb 가 그 시리얼을 device 상태로 볼 때까지 > {is_ok, problem}. 로그에 멈춤 징후가 보이면 바로 끝낸다."""
    adb = sdk_tool("adb")
    deadline = time.monotonic() + timeout_seconds
    while adb and time.monotonic() < deadline:
        _, text = _run([adb, "devices"], SIMCTL_QUICK_TIMEOUT_SECONDS)
        if any(line.split()[:2] == [serial, "device"] for line in text.splitlines()[1:]):
            return {"is_ok": True, "problem": None}
        if (problem := emulator_start_problem(log_path)):
            return {"is_ok": False, "problem": problem}
        time.sleep(2)
    return {"is_ok": False, "problem": emulator_start_problem(log_path)}


def kill_emulator(serial: str, avd: str) -> dict:
    """에뮬레이터 끄기: adb emu kill > 안 죽으면 qemu 강제 종료. > {killed_by, forced_pids, is_gone}"""
    adb = sdk_tool("adb")
    pids = procs.process_ids_with_arguments("-avd", avd)
    if adb:
        _run([adb, "-s", serial, "emu", "kill"], SIMCTL_QUICK_TIMEOUT_SECONDS)
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline and any(procs.pid_alive(p) for p in pids):
        time.sleep(1)
    survivors = [p for p in pids if procs.pid_alive(p)]
    # emu kill 이 안 먹는다 (호스트 메모리 압박으로 응답 없는 qemu, 실측) — 강제 종료
    still_alive = [p for p in survivors if procs.force_kill(p)]
    return {"killed_by": "emu_kill" if not survivors else "force_kill", "forced_pids": survivors,
            "is_gone": not still_alive}
