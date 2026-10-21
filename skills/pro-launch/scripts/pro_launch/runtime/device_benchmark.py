"""기기 수용량 측정: 기기당 메모리 · 부팅 · 캡처 시간을 잰다 (#964).

이미 켜진 기기가 있으면 그 사용량을 잰다(새로 켜지 않는다). 없으면 실험 기기를 켠다 — 빠른 측정: 종류마다 한 대. 전체 측정(full): 멈춤 신호가 보일 때까지 한 대씩 늘린다 (최대 FULL_MAXIMUM_DEVICES).
실험 기기는 끝나면 언제나 끄고 지운다. 중간에 죽어도 남지 않게 1시간짜리 임시 기기로 원장에 올려 둔다(gc 가 줍는다).
"""
from __future__ import annotations

import subprocess
import tempfile
import time
from pathlib import Path

from common.proc import sdk_tool

from pro_launch.runtime import device_backends, device_capacity, device_marks, host_resources, procs

# 켠 뒤 메모리가 자리 잡기를 기다리는 시간 (초)
SETTLE_SECONDS = 30
# 전체 측정에서 종류마다 최대 몇 대까지 늘리나
FULL_MAXIMUM_DEVICES = 6
# 멈춤 신호: 스왑 여유 (MB) · 처음보다 이만큼 느려지면 (배)
MINIMUM_SWAP_FREE_MB = 1024
SLOW_BOOT_FACTOR = 2.5
SLOW_SHOT_FACTOR = 3.0
# 실험 기기를 켤 때 비용 말고 더 남아 있어야 하는 메모리 (MB) — acquire 의 여유분보다 작다:
# 측정은 한 대씩 켜고 신호를 보며 멈추므로, acquire 기준을 쓰면 바쁜 컴퓨터에서는 영영 못 잰다
BENCHMARK_MINIMUM_FREE_MB = 1024
# 측정한 비용에 더하는 안전 여유 (비율)
COST_MARGIN_RATIO = 0.15
# 실험 기기 원장 기한 (일, 1시간) — 비정상 종료로 남으면 gc 가 지운다
BENCHMARK_DEVICE_TTL_DAYS = 1 / 24
DEVICE_PROCESS_NAMES = ("qemu-system", "launchd_sim", "Simulator", "emulator")


def stop_signal(memory: dict, cost_mb: int) -> str | None:
    """더 켜면 안 되는 신호 > 이유. 없으면 None."""
    pressure = host_resources.pressure_level(memory)
    if pressure == "critical":
        return "메모리 압박이 위험 수준이다"
    swap_total, swap_used = memory.get("swap_total_mb"), memory.get("swap_used_mb")
    if swap_total and swap_used is not None and swap_total - swap_used < MINIMUM_SWAP_FREE_MB \
            and (memory.get("available_mb") or 0) < cost_mb * 2:
        return f"스왑 여유가 {swap_total - swap_used}MB 뿐이다"
    available = memory.get("available_mb")
    if available is not None and available < cost_mb + BENCHMARK_MINIMUM_FREE_MB:
        return f"남은 메모리 {available}MB 가 기기 하나({cost_mb}MB) + {BENCHMARK_MINIMUM_FREE_MB}MB 보다 적다"
    return None


def non_device_consumers(count: int = 5) -> list[dict]:
    """기기가 아닌 큰 메모리 소비자 (이유에 보여 줄 것)."""
    rows = procs.top_memory_processes(count + 10)
    return [row for row in rows if not any(name in row["name"] for name in DEVICE_PROCESS_NAMES)][:count]


def device_process_ids(platform: str, key: str) -> list[int]:
    """그 기기가 쓰는 프로세스들. iOS 는 그 UDID 의 launchd_sim 과 그 아래 전부 — 안쪽 프로세스(SpringBoard 등)는
    명령줄에 UDID 가 없어 UDID 로만 찾으면 대부분 빠진다 (실측: 82MB 로 잘못 잼)."""
    if platform != "ios":
        return procs.process_ids_with_arguments("-avd", key)
    rows = procs.process_table() or []
    roots = {row["pid"] for row in rows if key in (row.get("command") or "") and "launchd_sim" in (row.get("command") or "")}
    found, frontier = set(roots), set(roots)
    while frontier:
        frontier = {row["pid"] for row in rows if row.get("ppid") in frontier} - found
        found |= frontier
    return sorted(found)


def screenshot_seconds(platform: str, instance: str) -> float | None:
    """캡처 한 장 걸리는 시간 (초). 실패하면 None."""
    started = time.monotonic()
    with tempfile.TemporaryDirectory() as folder:
        target = Path(folder) / "benchmark.png"
        try:
            if platform == "ios":
                result = subprocess.run(["xcrun", "simctl", "io", instance, "screenshot", str(target)],
                                        capture_output=True, timeout=60)
            else:
                adb = sdk_tool("adb")
                if not adb:
                    return None
                with open(target, "wb") as handle:
                    result = subprocess.run([adb, "-s", instance, "exec-out", "screencap", "-p"],
                                            stdout=handle, stderr=subprocess.PIPE, timeout=60)
        except (OSError, subprocess.SubprocessError):
            return None
        is_ok = result.returncode == 0 and target.is_file() and target.stat().st_size > 0
    return round(time.monotonic() - started, 2) if is_ok else None


def _boot_and_sample(backend, platform: str, key: str) -> dict:
    """한 대 켜고 재기 > {boot_seconds, footprint_mb, available_drop_mb, cost_mb, shot_seconds, problem}."""
    before = host_resources.read_memory()
    started = time.monotonic()
    booted = backend.boot(key, "headless", None)
    boot_seconds = round(time.monotonic() - started, 1)
    if not booted["is_ok"]:
        return {"key": key, "boot_seconds": boot_seconds, "problem": booted.get("detail") or "boot failed"}
    time.sleep(SETTLE_SECONDS)
    after = host_resources.read_memory()
    footprint = procs.process_memory_mb(device_process_ids(platform, key))
    drop = max(0, (before.get("available_mb") or 0) - (after.get("available_mb") or 0))
    return {"key": key, "instance": booted["instance"], "boot_seconds": boot_seconds, "footprint_mb": footprint,
            "available_drop_mb": drop, "cost_mb": max(footprint, drop),
            "shot_seconds": screenshot_seconds(platform, booted["instance"]), "problem": None}


def _is_slowed(sample: dict, first: dict) -> str | None:
    if sample["boot_seconds"] > first["boot_seconds"] * SLOW_BOOT_FACTOR:
        return f"부팅이 처음({first['boot_seconds']}초)보다 크게 느려졌다 ({sample['boot_seconds']}초)"
    if sample.get("shot_seconds") and first.get("shot_seconds") \
            and sample["shot_seconds"] > first["shot_seconds"] * SLOW_SHOT_FACTOR:
        return f"캡처가 처음({first['shot_seconds']}초)보다 크게 느려졌다 ({sample['shot_seconds']}초)"
    return None


def measure_running_devices() -> dict[str, dict]:
    """이미 켜진 가상 기기의 실제 사용량 > {플랫폼: {samples, cost_mb, method: running}} — 새로 켜지 않는 측정."""
    measured: dict[str, list[dict]] = {}
    for facts in device_backends.all_device_facts():
        if not facts.is_booted or device_backends.backend_named(facts.backend).capabilities.is_physical:
            continue
        footprint = procs.process_memory_mb(device_process_ids(facts.platform, facts.key))
        if footprint:
            measured.setdefault(facts.platform, []).append({"key": facts.key, "name": facts.name,
                                                            "footprint_mb": footprint, "cost_mb": footprint})
    return {platform: {"platform": platform, "samples": samples, "method": "running",
                       "cost_mb": int(max(s["cost_mb"] for s in samples) * (1 + COST_MARGIN_RATIO))}
            for platform, samples in measured.items()}


def measure_platform(platform: str, is_full: bool) -> dict:
    """한 종류 측정 > {platform, samples, cost_mb, healthy_count, stop_reason, skipped}. 실험 기기는 끝나면 지운다."""
    backend = next((b for b in device_backends.backends_for(platform) if b.capabilities.can_create), None)
    if backend is None:
        return {"platform": platform, "skipped": f"{platform} 기기를 만들 수 없다"}
    created, samples, stop_reason = [], [], None
    default_cost, _ = device_capacity.boot_cost_mb(platform)
    try:
        for index in range(FULL_MAXIMUM_DEVICES if is_full else 1):
            stop_reason = stop_signal(host_resources.read_memory(), samples[0]["cost_mb"] if samples else default_cost)
            if stop_reason:
                break
            made = backend.create(f"pro-launch benchmark {platform} {index + 1}", "phone", None)
            if not made["is_ok"]:
                stop_reason = f"실험 기기를 만들지 못했다: {made['detail']}"
                break
            created.append(made["key"])
            device_marks.record_created(made["key"], "device benchmark (#964)", BENCHMARK_DEVICE_TTL_DAYS, backend.name)
            sample = _boot_and_sample(backend, platform, made["key"])
            if sample["problem"]:
                stop_reason = sample["problem"]
                break
            samples.append(sample)
            if (slowed := _is_slowed(sample, samples[0])):
                stop_reason = slowed
                samples.pop()
                break
    finally:
        # (성공·실패·중단 공통) 실험 기기 정리
        for key in created:
            backend.shutdown(key, None)
            backend.delete(key)
            device_marks.forget_device(key)
    if not samples:
        return {"platform": platform, "samples": [], "stop_reason": stop_reason,
                "skipped": stop_reason or "측정하지 못했다"}
    cost = int(max(sample["cost_mb"] for sample in samples) * (1 + COST_MARGIN_RATIO))
    return {"platform": platform, "samples": samples, "cost_mb": cost, "healthy_count": len(samples),
            "stop_reason": stop_reason, "boot_seconds": samples[0]["boot_seconds"],
            "shot_seconds": samples[0].get("shot_seconds")}

