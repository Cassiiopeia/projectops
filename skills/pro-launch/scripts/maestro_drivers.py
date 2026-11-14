"""Find · classify · clean up leftover Maestro iOS driver processes (#922).

When Maestro is cut off by a timeout or its caller dies, the xcodebuild driver · Runner · JVM stay behind.
A leftover driver holding the port makes the next call end in 'no response (90 s)' or session start failure (observed: clears right after cleanup).

Classification (one process > owner)
  session  descendant of a live pro-launch session relay (relay_pid in the maestro-sessions state file)
  orphan   the top parent of the Maestro process chain is 1 (the caller is gone) · a Runner when no driver is attached
  active   anything else — the caller is alive (may be another session's run > report only)
Auto cleanup only touches old orphan drivers·JVMs pointing at the same device (UDID). Anything else via `app session stop --kill-stale`.
Listing only works when ps exists (empty on Windows) — top level uses only the standard library.
"""
from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import time

KIND_XCODEBUILD_DRIVER = "xcodebuild_driver"   # xcodebuild test-without-building ... maestro-driver-ios-config.xctestrun
KIND_DRIVER_RUNNER = "driver_runner"           # maestro-driver-iosUITests-Runner inside the simulator
KIND_MAESTRO_JVM = "maestro_jvm"               # java ... ~/.maestro/lib · maestro.cli.AppKt
# pid that reaps processes whose parent is gone (macOS launchd · Linux init)
ORPHAN_PARENT_PID = 1
# Minimum age for auto cleanup (s) — a just-detached process may still be shutting down
AUTO_CLEAN_MINIMUM_AGE_SECONDS = 60
# Wait after the termination signal (s) — SIGKILL if still running
TERMINATE_GRACE_SECONDS = 2.0
# What this process ended automatically (launch_cli is a new process per call)
CLEANED_DRIVERS: list[dict] = []
UDID_PATTERN = r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}"
# 4 places on the command line that point at the device: -destination id= · --device · --udid · simulator folder
UDID_CONTEXT = re.compile(rf"(?:id=|--device[= ]|--udid[= ]|/Devices/)({UDID_PATTERN})")


def kind_of(command: str) -> str | None:
    """Command line > Maestro process kind. None if not Maestro."""
    if "maestro-driver-iosUITests-Runner" in command:
        return KIND_DRIVER_RUNNER
    if "xcodebuild" in command and "maestro-driver-ios" in command:
        return KIND_XCODEBUILD_DRIVER
    if "java" in command and ("maestro.cli.AppKt" in command or "maestro/lib" in command):
        return KIND_MAESTRO_JVM
    return None


def udid_of(command: str) -> str | None:
    match = UDID_CONTEXT.search(command)
    return match.group(1).upper() if match else None


def parse_elapsed(text: str) -> int | None:
    """ps etime '[[dd-]hh:]mm:ss' > seconds."""
    match = re.fullmatch(r"(?:(\d+)-)?(?:(\d+):)?(\d+):(\d+)", (text or "").strip())
    if not match:
        return None
    days, hours, minutes, seconds = (int(part or 0) for part in match.groups())
    return ((days * 24 + hours) * 60 + minutes) * 60 + seconds


def list_processes() -> list[dict]:
    """[{pid, ppid, age_seconds, command}] — empty list if ps is missing or fails."""
    if not shutil.which("ps"):
        return []
    try:
        # -ww: do not truncate long command lines (xctestrun path · UDID come at the end)
        output = subprocess.run(["ps", "-ax", "-ww", "-o", "pid=,ppid=,etime=,command="], capture_output=True,
                                text=True, encoding="utf-8", errors="replace", timeout=5).stdout or ""
    except (OSError, subprocess.SubprocessError):
        return []
    rows = []
    for line in output.splitlines():
        parts = line.split(None, 3)
        if len(parts) == 4 and parts[0].isdigit() and parts[1].isdigit():
            rows.append({"pid": int(parts[0]), "ppid": int(parts[1]), "age_seconds": parse_elapsed(parts[2]),
                         "command": parts[3]})
    return rows


def live_session_relay_pids() -> set[int]:
    """Live session relay pids (from the maestro-sessions state files)."""
    import maestro_session                 # imported at call time to avoid the maestro_session > maestro_runs > here cycle
    from common.proc import pid_alive
    pids = set()
    try:
        files = list(maestro_session.session_folder().glob("*.json"))
    except OSError:
        return pids
    for path in files:
        session = maestro_session.read_session(path.stem) or {}
        relay_pid = session.get("relay_pid")
        if relay_pid and pid_alive(int(relay_pid)):
            pids.add(int(relay_pid))
    return pids


def classify(processes: list[dict], relay_pids: set[int], own_pid: int | None = None) -> list[dict]:
    """Pick only Maestro processes and attach owner: session · orphan · active (our own descendants excluded)."""
    by_pid = {row["pid"]: row for row in processes}
    own_pid = own_pid if own_pid is not None else os.getpid()
    drivers = []
    for row in processes:
        kind = kind_of(row["command"])
        if not kind:
            continue
        ancestors = _ancestors(row, by_pid)
        if own_pid in ancestors:
            continue
        if relay_pids & set(ancestors):
            owner = "session"
        elif kind != KIND_DRIVER_RUNNER and _chain_top(row, by_pid)["ppid"] == ORPHAN_PARENT_PID:
            owner = "orphan"
        else:
            owner = "active"
        drivers.append({"pid": row["pid"], "ppid": row["ppid"], "kind": kind, "age_seconds": row["age_seconds"],
                        "udid": udid_of(row["command"]), "owner": owner})
    # Runner: if the same device has no non-orphan driver·JVM, nothing is attached to it
    for driver in drivers:
        if driver["kind"] == KIND_DRIVER_RUNNER and driver["owner"] == "active":
            has_live_host = any(other["kind"] != KIND_DRIVER_RUNNER and other["owner"] != "orphan"
                                and other["udid"] in (driver["udid"], None) for other in drivers)
            driver["owner"] = "active" if has_live_host else "orphan"
    return drivers


def _ancestors(row: dict, by_pid: dict) -> list[int]:
    chain, seen, parent = [], set(), row["ppid"]
    while parent in by_pid and parent not in seen:
        seen.add(parent)
        chain.append(parent)
        parent = by_pid[parent]["ppid"]
    return chain + ([parent] if parent not in seen else [])


def _chain_top(row: dict, by_pid: dict) -> dict:
    """Top of the Maestro process chain (linked like JVM > xcodebuild) — if its parent is 1 the whole chain is orphaned."""
    top, seen = row, {row["pid"]}
    while top["ppid"] in by_pid and top["ppid"] not in seen and kind_of(by_pid[top["ppid"]]["command"]):
        seen.add(top["ppid"])
        top = by_pid[top["ppid"]]
    return top


def is_for_device(driver: dict, device: str | None) -> bool:
    """Same device UDID, or the device cannot be told from the command line."""
    return driver["udid"] is None or not device or driver["udid"] == device.upper()


def is_auto_cleanable(driver: dict, device: str | None) -> bool:
    """4 auto-cleanup conditions: orphan · not a Runner · same UDID on the command line · at least the minimum age."""
    return (driver["owner"] == "orphan" and driver["kind"] != KIND_DRIVER_RUNNER
            and bool(device) and driver["udid"] == (device or "").upper()
            and (driver["age_seconds"] or 0) >= AUTO_CLEAN_MINIMUM_AGE_SECONDS)


def public_entry(driver: dict) -> dict:
    return {"pid": driver["pid"], "kind": driver["kind"], "age_seconds": driver["age_seconds"]}


def survey(device: str | None) -> list[dict]:
    """Maestro processes related to this device (with owner)."""
    return [d for d in classify(list_processes(), live_session_relay_pids()) if is_for_device(d, device)]


def terminate(pids: list[int]) -> list[int]:
    """SIGTERM > short wait > SIGKILL the rest. List of ended pids."""
    from common.proc import pid_alive
    for pid in pids:
        _send(pid, signal.SIGTERM)
    deadline = time.monotonic() + TERMINATE_GRACE_SECONDS
    while time.monotonic() < deadline and any(pid_alive(pid) for pid in pids):
        time.sleep(0.1)
    for pid in pids:
        if pid_alive(pid):
            _send(pid, getattr(signal, "SIGKILL", signal.SIGTERM))
    return [pid for pid in pids if not pid_alive(pid)]


def _send(pid: int, signal_number: int) -> None:
    try:
        os.kill(pid, signal_number)
    except (ProcessLookupError, PermissionError, OSError):
        pass


def clean_auto(device: str | None) -> list[dict]:
    """Auto cleanup before acting (only old orphan drivers·JVMs of the same UDID) > what was ended."""
    return _terminate_recorded([d for d in survey(device) if is_auto_cleanable(d, device)])


def clean_after_timeout(device: str | None, run_seconds: float) -> list[dict]:
    """Right after a timeout cut: drivers created during this run that became orphans > what was ended (no age limit — they are ours)."""
    return _terminate_recorded([d for d in survey(device) if d["owner"] == "orphan" and d["kind"] != KIND_DRIVER_RUNNER
                                and (d["age_seconds"] or 0) <= run_seconds + 5])


def _terminate_recorded(targets: list[dict]) -> list[dict]:
    """End them and record in CLEANED_DRIVERS (cleaned_stale_drivers in the response)."""
    killed = set(terminate([d["pid"] for d in targets])) if targets else set()
    cleaned = [public_entry(d) for d in targets if d["pid"] in killed]
    CLEANED_DRIVERS.extend(cleaned)
    return cleaned


def kill_stale(device: str, is_dry_run: bool = False) -> dict:
    """Explicit cleanup (`app session stop --kill-stale`): every orphan of this device (including Runners and ones with unknown device)."""
    drivers = survey(device)
    targets = [d for d in drivers if d["owner"] == "orphan"]
    killed = set(terminate([d["pid"] for d in targets])) if targets and not is_dry_run else set()
    return {"stale_found": [public_entry(d) for d in targets],
            "killed": [d["pid"] for d in targets if d["pid"] in killed],
            "other_maestro_processes": [public_entry(d) for d in drivers if d["owner"] == "active"]}


def failure_fields(device: str | None) -> dict:
    """To attach to failed responses: remaining orphans · other Maestros running now (key omitted when empty)."""
    drivers = survey(device)
    fields = {"stale_maestro_drivers": [public_entry(d) for d in drivers if d["owner"] == "orphan"],
              "other_maestro_processes": [public_entry(d) for d in drivers if d["owner"] == "active"]}
    return {key: value for key, value in fields.items() if value}
