"""기기 백엔드 등록표 — 새 플랫폼은 파일 하나 + 아래 BACKENDS 한 줄 (#953)."""
from __future__ import annotations

from pro_launch.runtime.device_backends.android_emulator import AndroidEmulatorBackend
from pro_launch.runtime.device_backends.base import Capabilities, DeviceBackend, DeviceFacts
from pro_launch.runtime.device_backends.ios_simulator import IosSimulatorBackend
from pro_launch.runtime.device_backends.physical import PhysicalAndroidBackend

BACKENDS: tuple[DeviceBackend, ...] = (IosSimulatorBackend(), AndroidEmulatorBackend(), PhysicalAndroidBackend())

__all__ = ["BACKENDS", "Capabilities", "DeviceBackend", "DeviceFacts", "backend_named", "backends_for",
           "all_device_facts"]


def backend_named(name: str) -> DeviceBackend:
    return next(backend for backend in BACKENDS if backend.name == name)


def backends_for(platform: str) -> list[DeviceBackend]:
    return [backend for backend in BACKENDS if backend.platform == platform]


def all_device_facts(platform: str | None = None) -> list[DeviceFacts]:
    """등록된 백엔드의 기기 사실 전부 (platform 을 주면 그 플랫폼만)."""
    chosen = backends_for(platform) if platform else list(BACKENDS)
    return [facts for backend in chosen for facts in backend.list_devices()]
