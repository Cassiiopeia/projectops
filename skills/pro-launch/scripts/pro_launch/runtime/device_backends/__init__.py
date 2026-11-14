"""Device backend registry — a new platform is one file + one line in BACKENDS below (#953)."""
from __future__ import annotations

from pro_launch.runtime.device_backends.android_emulator import AndroidEmulatorBackend
from pro_launch.runtime.device_backends.base import Capabilities, DeviceBackend, DeviceFacts
from pro_launch.runtime.device_backends.ios_simulator import IosSimulatorBackend
from pro_launch.runtime.device_backends.physical import PhysicalAndroidBackend

BACKENDS: tuple[DeviceBackend, ...] = (IosSimulatorBackend(), AndroidEmulatorBackend(), PhysicalAndroidBackend())

__all__ = ["BACKENDS", "Capabilities", "DeviceBackend", "DeviceFacts", "backend_named", "backends_for",
           "all_device_facts", "find_device", "raw_command_patterns"]


def backend_named(name: str) -> DeviceBackend:
    return next(backend for backend in BACKENDS if backend.name == name)


def backends_for(platform: str) -> list[DeviceBackend]:
    return [backend for backend in BACKENDS if backend.platform == platform]


def all_device_facts(platform: str | None = None) -> list[DeviceFacts]:
    """Device facts from every registered backend (only that platform when platform is given)."""
    chosen = backends_for(platform) if platform else list(BACKENDS)
    return [facts for backend in chosen for facts in backend.list_devices()]


def find_device(want: str, platform: str | None = None) -> tuple[DeviceFacts | None, list[DeviceFacts]]:
    """Device whose key · running id · name matches exactly > (one, candidates). (None, candidates) if the name repeats — finds powered-off devices too."""
    every = all_device_facts(platform)
    exact = [facts for facts in every if want in (facts.key, facts.instance)]
    if exact:
        return exact[0], exact
    named = [facts for facts in every if facts.name == want]
    return (named[0] if len(named) == 1 else None), named


def raw_command_patterns():
    """Every pattern the raw-command blocking hook should block (gathered from the backend declarations in one place)."""
    return [pattern for backend in BACKENDS for pattern in backend.raw_command_patterns()]
