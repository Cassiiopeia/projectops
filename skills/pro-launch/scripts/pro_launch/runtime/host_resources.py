"""Host resource pressure diagnosis: memory·swap > pressure level > big processes > running virtual devices and bound repos (#883).

When several sessions run emulators·simulators together on one Mac, swap fills, the system server inside the device dies,
and captures fail silently. Make it look at host state before piling up retries.
**Report only** — never kill another session's processes.

Uses only standard tools (no dependencies): macOS vm_stat·sysctl, Linux /proc/meminfo, ps everywhere.
OS branching is by 'does the tool exist' — keeping the rule that sys.platform branches live only in procs.py.
"""
from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path

from common.proc import run
from common.state import base_dir

from pro_launch.runtime import procs

PROC_MEMINFO = Path("/proc/meminfo")
MEBIBYTE = 1024 * 1024
TOP_PROCESS_COUNT = 5

# Pressure level thresholds (empirical). With swap nearly full and little free memory, virtual devices start dying
CRITICAL_SWAP_USED_PERCENT = 90
CRITICAL_AVAILABLE_WITH_FULL_SWAP_PERCENT = 20
CRITICAL_AVAILABLE_PERCENT = 5
HIGH_SWAP_USED_PERCENT = 75
HIGH_AVAILABLE_PERCENT = 10
# macOS kern.memorystatus_vm_pressure_level: 1 normal, 2 warning, 4 critical
MACOS_PRESSURE_LEVELS = {1: "ok", 2: "high", 4: "critical"}
PRESSURE_ORDER = ("unknown", "ok", "high", "critical")
# Overloaded: 1-minute load average exceeds this multiple of the core count (observed at load 46·128: Maestro iOS driver startup did not finish in time)
OVERLOAD_LOAD_PER_CORE = 2


def read_memory() -> dict:
    """{total_mb, available_mb, swap_total_mb, swap_used_mb, os_pressure} — unreadable values are None."""
    if PROC_MEMINFO.is_file():
        return _read_proc_meminfo()
    if shutil.which("vm_stat"):
        return _read_vm_stat()
    windows = procs.read_windows_memory()
    if windows:
        return {**windows, "os_pressure": None}
    return {"total_mb": None, "available_mb": None, "swap_total_mb": None, "swap_used_mb": None,
            "os_pressure": None}


def _read_proc_meminfo() -> dict:
    """Linux: kB > MB."""
    values: dict[str, int] = {}
    try:
        for line in PROC_MEMINFO.read_text(encoding="utf-8").splitlines():
            match = re.match(r"(\w+):\s+(\d+)", line)
            if match:
                values[match.group(1)] = int(match.group(2)) // 1024
    except OSError:
        pass
    swap_total = values.get("SwapTotal")
    swap_free = values.get("SwapFree")
    return {"total_mb": values.get("MemTotal"), "available_mb": values.get("MemAvailable"),
            "swap_total_mb": swap_total,
            "swap_used_mb": swap_total - swap_free if swap_total is not None and swap_free is not None else None,
            "os_pressure": None}


def _read_vm_stat() -> dict:
    """macOS: available memory = free + inactive + speculative + purgeable pages (close to Activity Monitor's 'available')."""
    text = run(["vm_stat"])
    page_size_match = re.search(r"page size of (\d+) bytes", text)
    page_size = int(page_size_match.group(1)) if page_size_match else 4096
    pages = {m.group(1).strip(): int(m.group(2))
             for m in re.finditer(r"^Pages ([\w -]+):\s+(\d+)\.", text, re.MULTILINE)}
    reclaimable = sum(pages.get(k, 0) for k in ("free", "inactive", "speculative", "purgeable"))
    total_bytes = _int_or_none(run(["sysctl", "-n", "hw.memsize"]).strip())
    swap_text = run(["sysctl", "-n", "vm.swapusage"])
    swap_total = re.search(r"total\s*=\s*([\d.]+)M", swap_text)
    swap_used = re.search(r"used\s*=\s*([\d.]+)M", swap_text)
    level = _int_or_none(run(["sysctl", "-n", "kern.memorystatus_vm_pressure_level"]).strip())
    return {"total_mb": total_bytes // MEBIBYTE if total_bytes else None,
            "available_mb": reclaimable * page_size // MEBIBYTE if pages else None,
            "swap_total_mb": int(float(swap_total.group(1))) if swap_total else None,
            "swap_used_mb": int(float(swap_used.group(1))) if swap_used else None,
            "os_pressure": MACOS_PRESSURE_LEVELS.get(level) if level is not None else None}


def _int_or_none(text: str) -> int | None:
    return int(text) if text.isdigit() else None


def _percent(part: int | None, whole: int | None) -> int | None:
    return round(part * 100 / whole) if part is not None and whole else None


def pressure_level(memory: dict) -> str:
    """The worse of the numeric verdict and the OS verdict (macOS) > ok | high | critical | unknown."""
    available_percent = _percent(memory.get("available_mb"), memory.get("total_mb"))
    # When the OS reports the pressure level itself (macOS), swap ratio is ignored — macOS grows swap as it uses it, so it is always near 90%
    # (observed in #964: swap 91% · OS verdict warning, yet it was raised to critical and blocked every boot)
    is_swap_judged = memory.get("os_pressure") is None
    swap_used_percent = _percent(memory.get("swap_used_mb"), memory.get("swap_total_mb")) if is_swap_judged else None
    level = "unknown" if available_percent is None else "ok"
    if available_percent is not None:
        is_swap_nearly_full = (swap_used_percent or 0) >= CRITICAL_SWAP_USED_PERCENT
        if (available_percent < CRITICAL_AVAILABLE_PERCENT
                or (is_swap_nearly_full and available_percent < CRITICAL_AVAILABLE_WITH_FULL_SWAP_PERCENT)):
            level = "critical"
        elif (swap_used_percent or 0) >= HIGH_SWAP_USED_PERCENT or available_percent < HIGH_AVAILABLE_PERCENT:
            level = "high"
    os_level = memory.get("os_pressure")
    if os_level and PRESSURE_ORDER.index(os_level) > PRESSURE_ORDER.index(level):
        level = os_level
    return level


def top_processes(count: int = TOP_PROCESS_COUNT) -> list[dict]:
    """Processes using the most memory (RSS) > [{pid, name, rss_mb}]. Empty list if ps is missing."""
    if not shutil.which("ps"):
        return []
    rows = []
    for line in run(["ps", "-axo", "pid=,rss=,comm="]).splitlines():
        parts = line.split(None, 2)
        if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit():
            rows.append({"pid": int(parts[0]), "name": Path(parts[2].strip()).name,
                         "rss_mb": int(parts[1]) // 1024})
    rows.sort(key=lambda row: -row["rss_mb"])
    return rows[:count]


def device_owners() -> dict[str, list[str]]:
    """Device serial·UDID > repo buckets that bound that device to a role (to gauge whether another session uses it)."""
    owners: dict[str, list[str]] = {}
    launch_dir = base_dir() / "launch"
    if not launch_dir.is_dir():
        return owners
    for devices_file in sorted(launch_dir.glob("*/devices.json")):
        try:
            data = json.loads(devices_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for binding in (data.get("bindings") or []) if isinstance(data, dict) else []:
            serial = isinstance(binding, dict) and binding.get("serial")
            if serial:
                owners.setdefault(str(serial), []).append(devices_file.parent.name)
    return owners


def memory_summary() -> dict:
    """Short summary (for the devices response): {pressure, available_mb, available_percent, swap_used_percent}."""
    memory = read_memory()
    return {"pressure": pressure_level(memory), "available_mb": memory.get("available_mb"),
            "available_percent": _percent(memory.get("available_mb"), memory.get("total_mb")),
            "swap_used_percent": _percent(memory.get("swap_used_mb"), memory.get("swap_total_mb"))}


def read_load() -> dict:
    """{load_1m, load_5m, load_15m, cpu_count, is_overloaded} — values are None on OSes without load averages (Windows)."""
    cpu_count = os.cpu_count()
    try:
        load_1m, load_5m, load_15m = (round(value, 1) for value in os.getloadavg())
    except (AttributeError, OSError):
        return {"load_1m": None, "load_5m": None, "load_15m": None, "cpu_count": cpu_count, "is_overloaded": False}
    return {"load_1m": load_1m, "load_5m": load_5m, "load_15m": load_15m, "cpu_count": cpu_count,
            "is_overloaded": bool(cpu_count) and load_1m > OVERLOAD_LOAD_PER_CORE * cpu_count}


def resource_report(devices: dict) -> dict:
    """Full doctor --resources report: memory > pressure level > load > big processes > running virtual devices and bound repos."""
    memory = read_memory()
    owners = device_owners()
    booted = [{"platform": "android", "id": serial, "bound_by": owners.get(serial, [])}
              for serial in devices.get("android", [])]
    for label in devices.get("ios_booted", []):
        udid_match = re.search(r"\[([\w-]{36})\]$", label)
        udid = udid_match.group(1) if udid_match else label
        booted.append({"platform": "ios", "id": udid, "name": label.split(" [")[0],
                       "bound_by": owners.get(udid, [])})
    return {**memory, **memory_summary(), "load": read_load(), "top_processes": top_processes(),
            "booted_devices": booted}


def pressure_advice(level: str) -> str | None:
    """Next action per pressure level. Shutting things down is the user's call."""
    if level == "critical":
        return ("host memory is critical — ask the user before booting another virtual device or running a build. "
                "Do not stop other sessions' devices or processes (bound_by shows who uses them)")
    if level == "high":
        return "memory is tight — booting another virtual device may kill apps on it or make captures fail"
    return None


# The only flag that passes the memory risk gate (critical · device budget) — --yes does not pass it (#972)
USER_APPROVED_FLAG = "--user-approved"
# Next action when the risk gate trips (wording shared by acquire · boot)
MEMORY_RISK_NEXT = (f"Show the user reasons (and non_device_consumers), and after they answer call again with {USER_APPROVED_FLAG}. "
                    "Do not poll doctor --resources waiting for the pressure to ease")
# Next action for actions with no flag to pass (no-device notices, etc.)
MEMORY_RISK_ASK_NEXT = ("Show the user reasons (and non_device_consumers) and ask what to stop — the user decides about other sessions' "
                        "devices and builds. Do not poll doctor --resources waiting for the pressure to ease")


def memory_risk_fields() -> dict:
    """Big memory consumers outside devices, attached to risk-gate responses — so the user can choose what to close (#964 · #972)."""
    from pro_launch.runtime.device_benchmark import non_device_consumers
    try:
        return {"non_device_consumers": non_device_consumers()}
    except Exception:   # noqa: BLE001 — the consumer list is auxiliary
        return {}


def critical_pressure_failure(action: str, is_user_approvable: bool = False) -> dict | None:
    """Call before actions that boot a new virtual device. On critical, a failure result that stops before dying midway (#883).

    is_user_approvable: the action accepts --user-approved (next mentions that flag).
    Caller: `if (failure := critical_pressure_failure("device boot", True)): return out(failure)`.
    """
    summary = memory_summary()
    if summary["pressure"] != "critical":
        return None
    error = (f"host memory is critical ({summary['available_percent']}% available, "
             f"swap {summary['swap_used_percent']}% used)")
    return {"ok": False, "code": "host_memory_pressure", "action": action, "resources": summary,
            "error": error, "reasons": [error], **memory_risk_fields(),
            "next": MEMORY_RISK_NEXT if is_user_approvable else MEMORY_RISK_ASK_NEXT}
