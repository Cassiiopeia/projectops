"""기기 수용량 · 메모리 예산 · 켜기 차례 (#964) — 기기 없이 검사한다."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from pro_launch.commands.device import benchmark  # noqa: E402
from pro_launch.runtime import boot_turn, device_capacity, procs  # noqa: E402

ROOMY = {"total_mb": 32768, "available_mb": 20000, "swap_total_mb": 0, "swap_used_mb": 0, "os_pressure": "ok"}


@pytest.fixture
def settings(monkeypatch):
    """config launch.devices 를 가짜로."""
    store = {"launch": {"devices": {}}, "github": {"global_pat": "keep-me"}}
    monkeypatch.setattr(device_capacity.common_config, "get_section", lambda name: store.get(name))
    monkeypatch.setattr(device_capacity.common_config, "load", lambda: store)
    monkeypatch.setattr(device_capacity.common_config, "save", lambda data: store.update(data))
    return store


def test_budget_counts_every_booted_device_by_its_platform_cost(settings):
    settings["launch"]["devices"].update({"boot_cost_mb": {"ios": 1000, "android": 5000}, "memory_budget_mb": 12000})
    assert device_capacity.boot_block_reason("ios", {"android": 2}, ROOMY) is None          # 10000 + 1000 <= 12000
    blocked = device_capacity.boot_block_reason("android", {"android": 2}, ROOMY)          # 10000 + 5000 > 12000
    assert blocked and "예산 초과" in blocked


def test_live_memory_shortage_blocks_even_within_budget(settings):
    tight = {**ROOMY, "available_mb": 2000}
    reason = device_capacity.boot_block_reason("ios", {}, tight)
    assert reason and "남은 메모리" in reason


def test_benchmark_refuses_while_other_sessions_use_devices(monkeypatch, capsys, settings):
    monkeypatch.setattr(benchmark, "_others_using_devices", lambda: [{"device": "X", "session": "other", "purpose": "#1"}])
    benchmark.run_benchmark(argparse.Namespace(platform=None, full=False, yes=False))
    data = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert data["code"] == "devices_in_use" and settings["launch"]["devices"] == {}


def test_benchmark_saves_budget_and_keeps_other_config(monkeypatch, capsys, settings):
    monkeypatch.setattr(benchmark, "_others_using_devices", lambda: [])
    monkeypatch.setattr(benchmark.host_resources, "read_memory", lambda: ROOMY)
    monkeypatch.setattr(benchmark.device_pool_facts, "booted_virtual_counts", lambda: {"android": 1})
    monkeypatch.setattr(benchmark.device_benchmark, "non_device_consumers", lambda: [])
    monkeypatch.setattr(benchmark.device_benchmark, "measure_platform",
                        lambda platform, is_full: {"platform": platform, "cost_mb": 1200 if platform == "ios" else 6400})
    benchmark.run_benchmark(argparse.Namespace(platform=None, full=False, yes=False))
    data = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    saved = settings["launch"]["devices"]
    # 예산 = 남은 20000 + 켜져 있던 android 1대 6400 - 여유분 3072
    assert saved["memory_budget_mb"] == 20000 + 6400 - device_capacity.DEFAULT_MEMORY_RESERVE_MB == data["memory_budget_mb"]
    assert saved["boot_cost_mb"] == {"ios": 1200, "android": 6400} and settings["github"]["global_pat"] == "keep-me"


def test_boot_turn_is_one_at_a_time(monkeypatch):
    monkeypatch.setattr(boot_turn, "BOOT_TURN_RETRY_SECONDS", 0.01)
    with boot_turn.boot_turn():
        monkeypatch.setattr(boot_turn.procs, "try_lock_file", lambda handle: False)
        with pytest.raises(boot_turn.BootTurnBusyError):
            with boot_turn.boot_turn(wait_seconds=0.05):
                pass


def test_top_size_notation_is_parsed():
    assert procs._size_to_mb("5611M") == 5611 and procs._size_to_mb("1.5G") == 1536
    assert procs._size_to_mb("2048K") == 2 and procs._size_to_mb("812M+") == 812
