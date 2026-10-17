"""호스트 자원 압박 진단: 메모리·스왑 > 압박 단계 > 큰 프로세스 > 켜진 가상 기기와 묶은 레포 (#883).

여러 세션이 한 맥에서 에뮬레이터·시뮬레이터를 함께 띄우면 스왑이 차서 기기 안 system server 가 죽고
캡처가 조용히 실패한다. 재시도를 거듭하기 전에 호스트 상태를 먼저 보게 한다.
**보고만 한다** — 다른 세션의 프로세스는 절대 끄지 않는다.

표준 도구만 쓴다 (의존성 없음): macOS vm_stat·sysctl, Linux /proc/meminfo, 공통 ps.
OS 분기는 '도구가 있는가'로 가른다 — sys.platform 분기는 procs.py 에만 둔다는 규칙을 지킨다.
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from common.proc import run
from common.state import base_dir

PROC_MEMINFO = Path("/proc/meminfo")
MEBIBYTE = 1024 * 1024
TOP_PROCESS_COUNT = 5

# 압박 단계 기준 (경험값). 스왑이 거의 찼는데 남은 메모리도 적으면 가상 기기가 죽기 시작한다
CRITICAL_SWAP_USED_PERCENT = 90
CRITICAL_AVAILABLE_WITH_FULL_SWAP_PERCENT = 20
CRITICAL_AVAILABLE_PERCENT = 5
HIGH_SWAP_USED_PERCENT = 75
HIGH_AVAILABLE_PERCENT = 10
# macOS kern.memorystatus_vm_pressure_level: 1 정상, 2 경고, 4 위험
MACOS_PRESSURE_LEVELS = {1: "ok", 2: "high", 4: "critical"}
PRESSURE_ORDER = ("unknown", "ok", "high", "critical")


def read_memory() -> dict:
    """{total_mb, available_mb, swap_total_mb, swap_used_mb, os_pressure} — 못 읽은 값은 None."""
    if PROC_MEMINFO.is_file():
        return _read_proc_meminfo()
    if shutil.which("vm_stat"):
        return _read_vm_stat()
    return {"total_mb": None, "available_mb": None, "swap_total_mb": None, "swap_used_mb": None,
            "os_pressure": None}


def _read_proc_meminfo() -> dict:
    """Linux: kB 단위 > MB."""
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
    """macOS: 남은 메모리 = free + inactive + speculative + purgeable 페이지 (활동 모니터 '사용 가능'에 가깝다)."""
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
    """수치 판정과 OS 판정(macOS) 중 더 나쁜 쪽 > ok | high | critical | unknown."""
    available_percent = _percent(memory.get("available_mb"), memory.get("total_mb"))
    swap_used_percent = _percent(memory.get("swap_used_mb"), memory.get("swap_total_mb"))
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
    """메모리(RSS)를 가장 많이 쓰는 프로세스 > [{pid, name, rss_mb}]. ps 가 없으면 빈 목록."""
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
    """기기 시리얼·UDID > 그 기기를 역할에 묶어 둔 레포 버킷들 (다른 세션이 쓰는 기기인지 가늠)."""
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
    """짧은 요약 (devices 응답용): {pressure, available_mb, available_percent, swap_used_percent}."""
    memory = read_memory()
    return {"pressure": pressure_level(memory), "available_mb": memory.get("available_mb"),
            "available_percent": _percent(memory.get("available_mb"), memory.get("total_mb")),
            "swap_used_percent": _percent(memory.get("swap_used_mb"), memory.get("swap_total_mb"))}


def resource_report(devices: dict) -> dict:
    """doctor --resources 전체 보고: 메모리 > 압박 단계 > 큰 프로세스 > 켜진 가상 기기와 묶은 레포."""
    memory = read_memory()
    owners = device_owners()
    booted = [{"platform": "android", "id": serial, "bound_by": owners.get(serial, [])}
              for serial in devices.get("android", [])]
    for label in devices.get("ios_booted", []):
        udid_match = re.search(r"\[([\w-]{36})\]$", label)
        udid = udid_match.group(1) if udid_match else label
        booted.append({"platform": "ios", "id": udid, "name": label.split(" [")[0],
                       "bound_by": owners.get(udid, [])})
    return {**memory, **memory_summary(), "top_processes": top_processes(), "booted_devices": booted}


def pressure_advice(level: str) -> str | None:
    """압박 단계별 다음 행동. 끄는 일은 사용자 몫이다."""
    if level == "critical":
        return ("호스트 메모리가 위험 수준이다 — 가상 기기를 새로 띄우거나 빌드를 돌리기 전에 사용자에게 먼저 묻는다. "
                "다른 세션의 기기·프로세스는 끄지 않는다 (bound_by 로 누가 쓰는지 본다)")
    if level == "high":
        return "메모리가 빠듯하다 — 가상 기기를 하나 더 띄우면 기기 안 앱이 죽거나 캡처가 실패할 수 있다"
    return None


def critical_pressure_failure(action: str) -> dict | None:
    """가상 기기를 새로 띄우는 동작 앞에서 부른다. critical 이면 중간에 죽기 전에 멈추는 실패 결과 (#883).

    부르는 쪽: `if (failure := critical_pressure_failure("app launch")): return out(failure)`.
    """
    summary = memory_summary()
    if summary["pressure"] != "critical":
        return None
    return {"ok": False, "code": "host_memory_pressure", "action": action, "resources": summary,
            "error": (f"호스트 메모리가 위험 수준이다 (남은 {summary['available_percent']}%, "
                      f"스왑 {summary['swap_used_percent']}% 사용)"),
            "next": "사용자에게 먼저 묻는다 — 다른 세션의 기기·빌드를 끌지는 사용자가 정한다. doctor --resources 로 누가 쓰는지 본다"}
