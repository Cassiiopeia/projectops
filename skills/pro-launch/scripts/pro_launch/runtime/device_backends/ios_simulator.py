"""iOS 시뮬레이터 백엔드: simctl 목록 · 부팅 · 종료 (기존 device_boot 를 감싼다)."""
from __future__ import annotations

import re

from pro_launch.runtime import device_boot
from pro_launch.runtime.device_backends.base import FORM_PHONE, FORM_TABLET, Capabilities, DeviceFacts

# simctl 런타임 id > OS 버전: com.apple.CoreSimulator.SimRuntime.iOS-18-3 > 18.3
_RUNTIME_VERSION_PATTERN = re.compile(r"\.(?:iOS|iPadOS)-(\d+(?:-\d+)*)$")
TABLET_NAME_PREFIX = "iPad"


def os_version_of_runtime(runtime: str) -> str | None:
    match = _RUNTIME_VERSION_PATTERN.search(runtime or "")
    return match.group(1).replace("-", ".") if match else None


def form_of_name(name: str) -> str:
    return FORM_TABLET if (name or "").startswith(TABLET_NAME_PREFIX) else FORM_PHONE


class IosSimulatorBackend:
    name = "ios_simulator"
    platform = "ios"
    capabilities = Capabilities(can_boot=True, can_shutdown=True)

    def list_devices(self) -> list[DeviceFacts]:
        # iOS 런타임만 (watchOS·tvOS·visionOS 는 이 백엔드가 다루지 않는다)
        return [DeviceFacts(key=s["udid"], platform=self.platform, backend=self.name, name=s["name"],
                            form=form_of_name(s["name"]), os_version=os_version_of_runtime(s["runtime"]),
                            is_booted=s["state"] == "Booted", instance=s["udid"] if s["state"] == "Booted" else None)
                for s in device_boot.ios_simulators() if os_version_of_runtime(s.get("runtime") or "")]

    def boot(self, key: str, window: str, scale: float | None) -> dict:
        booted = device_boot.boot_ios(key, window, scale)
        return {"is_ok": booted["is_ok"], "instance": key, "already_booted": booted.get("already_booted", False),
                "detail": booted.get("detail"), "raw": booted}

    def shutdown(self, key: str, instance: str | None) -> dict:
        is_ok, detail = device_boot.shutdown_ios(key)
        return {"is_ok": is_ok, "detail": None if is_ok else detail[-300:]}

    def key_of_instance(self, instance: str) -> str | None:
        return instance if device_boot.is_udid(instance) else None
