"""호스트 자원 압박 진단: 메모리·스왑 > 압박 단계 > 큰 프로세스 > 켜진 가상 기기와 묶은 레포 (#883).

여러 세션이 한 맥에서 에뮬레이터·시뮬레이터를 함께 띄우면 스왑이 차서 기기 안 system server 가 죽고
캡처가 조용히 실패한다. 재시도를 거듭하기 전에 호스트 상태를 먼저 보게 한다.
**보고만 한다** — 다른 세션의 프로세스는 절대 끄지 않는다.

표준 도구만 쓴다 (의존성 없음): macOS vm_stat·sysctl, Linux /proc/meminfo, 공통 ps.
OS 분기는 '도구가 있는가'로 가른다 — sys.platform 분기는 procs.py 에만 둔다는 규칙을 지킨다.
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

# 압박 단계 기준 (경험값). 스왑이 거의 찼는데 남은 메모리도 적으면 가상 기기가 죽기 시작한다
CRITICAL_SWAP_USED_PERCENT = 90
CRITICAL_AVAILABLE_WITH_FULL_SWAP_PERCENT = 20
CRITICAL_AVAILABLE_PERCENT = 5
HIGH_SWAP_USED_PERCENT = 75
HIGH_AVAILABLE_PERCENT = 10
# macOS kern.memorystatus_vm_pressure_level: 1 정상, 2 경고, 4 위험
MACOS_PRESSURE_LEVELS = {1: "ok", 2: "high", 4: "critical"}
PRESSURE_ORDER = ("unknown", "ok", "high", "critical")
# 과부하: 1분 평균 부하가 코어 수의 이 배수를 넘는다 (실측 load 46·128 에서 Maestro iOS 드라이버 기동이 시간 안에 못 끝났다)
OVERLOAD_LOAD_PER_CORE = 2


def read_memory() -> dict:
    """{total_mb, available_mb, swap_total_mb, swap_used_mb, os_pressure} — 못 읽은 값은 None."""
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
    # OS 가 압박 단계를 직접 알려 주면(macOS) 스왑 비율은 보지 않는다 — macOS 는 스왑을 쓰는 만큼 늘려 늘 90% 가깝다
    # (실측 #964: 스왑 91% · OS 판정 경고인데 critical 로 올라 모든 부팅이 막혔다)
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


def read_load() -> dict:
    """{load_1m, load_5m, load_15m, cpu_count, is_overloaded} — 부하 평균이 없는 OS(윈도우)면 값이 None."""
    cpu_count = os.cpu_count()
    try:
        load_1m, load_5m, load_15m = (round(value, 1) for value in os.getloadavg())
    except (AttributeError, OSError):
        return {"load_1m": None, "load_5m": None, "load_15m": None, "cpu_count": cpu_count, "is_overloaded": False}
    return {"load_1m": load_1m, "load_5m": load_5m, "load_15m": load_15m, "cpu_count": cpu_count,
            "is_overloaded": bool(cpu_count) and load_1m > OVERLOAD_LOAD_PER_CORE * cpu_count}


def resource_report(devices: dict) -> dict:
    """doctor --resources 전체 보고: 메모리 > 압박 단계 > 부하 > 큰 프로세스 > 켜진 가상 기기와 묶은 레포."""
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
    """압박 단계별 다음 행동. 끄는 일은 사용자 몫이다."""
    if level == "critical":
        return ("host memory is critical — ask the user before booting another virtual device or running a build. "
                "Do not stop other sessions' devices or processes (bound_by shows who uses them)")
    if level == "high":
        return "memory is tight — booting another virtual device may kill apps on it or make captures fail"
    return None


# 메모리 위험 게이트(critical · 기기 예산)를 넘는 유일한 플래그 — --yes 로는 넘지 않는다 (#972)
USER_APPROVED_FLAG = "--user-approved"
# 위험 게이트에 걸렸을 때의 다음 행동 (acquire · boot 공용 문구)
MEMORY_RISK_NEXT = (f"Show the user reasons (and non_device_consumers), and after they answer call again with {USER_APPROVED_FLAG}. "
                    "Do not poll doctor --resources waiting for the pressure to ease")
# 부를 플래그가 없는 동작(기기 없음 안내 등)의 다음 행동
MEMORY_RISK_ASK_NEXT = ("Show the user reasons (and non_device_consumers) and ask what to stop — the user decides about other sessions' "
                        "devices and builds. Do not poll doctor --resources waiting for the pressure to ease")


def memory_risk_fields() -> dict:
    """위험 게이트 응답에 싣는 기기 밖 큰 메모리 소비자 — 사용자가 끌 것을 고르게 (#964 · #972)."""
    from pro_launch.runtime.device_benchmark import non_device_consumers
    try:
        return {"non_device_consumers": non_device_consumers()}
    except Exception:   # noqa: BLE001 — 소비자 목록은 보조다
        return {}


def critical_pressure_failure(action: str, is_user_approvable: bool = False) -> dict | None:
    """가상 기기를 새로 띄우는 동작 앞에서 부른다. critical 이면 중간에 죽기 전에 멈추는 실패 결과 (#883).

    is_user_approvable: 그 동작이 --user-approved 를 받는다 (next 에 그 플래그를 안내).
    부르는 쪽: `if (failure := critical_pressure_failure("device boot", True)): return out(failure)`.
    """
    summary = memory_summary()
    if summary["pressure"] != "critical":
        return None
    error = (f"host memory is critical ({summary['available_percent']}% available, "
             f"swap {summary['swap_used_percent']}% used)")
    return {"ok": False, "code": "host_memory_pressure", "action": action, "resources": summary,
            "error": error, "reasons": [error], **memory_risk_fields(),
            "next": MEMORY_RISK_NEXT if is_user_approvable else MEMORY_RISK_ASK_NEXT}
