"""iOS 시뮬레이터 백엔드: simctl 목록 · 부팅 · 종료(device_boot 를 감싼다) · 만들기 · 초기화 · 지우기."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from pro_launch.runtime import device_boot
from pro_launch.runtime.device_backends.base import (FORM_PHONE, FORM_TABLET, Capabilities, DeviceFacts,
                                                    RawCommandPattern, folder_bytes, is_os_satisfied)

# simctl 런타임 id > OS 버전: com.apple.CoreSimulator.SimRuntime.iOS-18-3 > 18.3
_RUNTIME_VERSION_PATTERN = re.compile(r"\.(?:iOS|iPadOS)-(\d+(?:-\d+)*)$")
TABLET_NAME_PREFIX = "iPad"
# 폼팩터 > simctl 기기 종류의 productFamily
PRODUCT_FAMILY_BY_FORM = {FORM_PHONE: "iPhone", FORM_TABLET: "iPad"}
SIMCTL_TIMEOUT_SECONDS = 120
# 시뮬레이터 데이터 폴더: {이 폴더}/{UDID}
SIMULATOR_DEVICES_FOLDER = Path.home() / "Library" / "Developer" / "CoreSimulator" / "Devices"


def os_version_of_runtime(runtime: str) -> str | None:
    match = _RUNTIME_VERSION_PATTERN.search(runtime or "")
    return match.group(1).replace("-", ".") if match else None


def form_of_name(name: str) -> str:
    return FORM_TABLET if (name or "").startswith(TABLET_NAME_PREFIX) else FORM_PHONE


class IosSimulatorBackend:
    name = "ios_simulator"
    platform = "ios"
    # 복제 실측 (#955): 꺼진 원본만 된다 · 데이터·키체인 파일이 같다 · APFS 복제라 디스크 10MB · 8초
    capabilities = Capabilities(can_boot=True, can_shutdown=True, can_create=True, can_clone=True,
                                can_clone_keep_marks=True)

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

    # ── 만들기 · 초기화 · 지우기 (#954) ──

    def _simctl(self, *arguments: str) -> tuple[bool, str]:
        try:
            result = subprocess.run(["xcrun", "simctl", *arguments], capture_output=True, text=True,
                                    timeout=SIMCTL_TIMEOUT_SECONDS)
        except (OSError, subprocess.SubprocessError) as error:
            return False, str(error)
        return result.returncode == 0, ((result.stdout or "") + (result.stderr or "")).strip()

    def choose_device_type(self, form: str, os_minimum: str | None) -> tuple[str, str] | None:
        """(기기 종류 id, 런타임 id): 조건을 만족하는 가장 새 iOS 런타임 > 그 런타임이 지원하는 첫 기기 종류(가장 새 모델)."""
        is_ok, text = self._simctl("list", "runtimes", "-j")
        try:
            runtimes = json.loads(text).get("runtimes", []) if is_ok else []
        except json.JSONDecodeError:
            return None
        family = PRODUCT_FAMILY_BY_FORM.get(form, "iPhone")
        usable = [r for r in runtimes if r.get("isAvailable") and os_version_of_runtime(r.get("identifier", ""))
                  and is_os_satisfied(r.get("version"), os_minimum)]
        for runtime in sorted(usable, key=lambda r: [int(p) for p in str(r.get("version", "0")).split(".") if p.isdigit()],
                              reverse=True):
            device_type = next((t for t in runtime.get("supportedDeviceTypes", []) if t.get("productFamily") == family), None)
            if device_type:
                return device_type["identifier"], runtime["identifier"]
        return None

    def create(self, name: str, form: str, os_minimum: str | None) -> dict:
        chosen = self.choose_device_type(form, os_minimum)
        if chosen is None:
            return {"is_ok": False, "key": None, "detail": f"no iOS runtime or device type matches {form} · OS {os_minimum or 'any'}"}
        is_ok, text = self._simctl("create", name, *chosen)
        udid = text.strip().splitlines()[-1] if is_ok and text.strip() else None
        return {"is_ok": bool(is_ok and udid and device_boot.is_udid(udid)), "key": udid,
                "detail": None if is_ok else text[-300:]}

    def clone(self, key: str, name: str) -> dict:
        is_ok, text = self._simctl("clone", key, name)
        udid = text.strip().splitlines()[-1] if is_ok and text.strip() else None
        return {"is_ok": bool(is_ok and udid and device_boot.is_udid(udid)), "key": udid,
                "detail": None if is_ok else text[-300:]}

    def erase(self, key: str) -> dict:
        is_ok, text = self._simctl("erase", key)
        return {"is_ok": is_ok, "detail": None if is_ok else text[-300:]}

    def delete(self, key: str) -> dict:
        is_ok, text = self._simctl("delete", key)
        return {"is_ok": is_ok, "detail": None if is_ok else text[-300:]}

    def raw_command_patterns(self) -> tuple[RawCommandPattern, ...]:
        return (RawCommandPattern(r"\bsimctl\s+(create|clone)\b", "launch_cli.py device create --platform ios --reason '<why a new device is needed>'"),
                RawCommandPattern(r"\bsimctl\s+(delete|erase)\b", "launch_cli.py device delete|erase --device <UDID>"),
                RawCommandPattern(r"\bsimctl\s+shutdown\s+all\b", "launch_cli.py device shutdown --device <UDID>  (also shuts down other sessions' devices)"))

    def disk_bytes(self, key: str) -> int:
        return folder_bytes(SIMULATOR_DEVICES_FOLDER / key)

    def unavailable_devices(self) -> list[dict]:
        """런타임이 사라져 쓸 수 없게 된 시뮬레이터 > [{udid, name, bytes}] (정리 대상)."""
        is_ok, text = self._simctl("list", "devices", "unavailable", "-j")
        try:
            groups = json.loads(text).get("devices", {}) if is_ok else {}
        except json.JSONDecodeError:
            return []
        return [{"udid": d["udid"], "name": d.get("name"), "bytes": self.disk_bytes(d["udid"])}
                for devices in groups.values() for d in devices if d.get("udid")]

    def delete_unavailable(self) -> dict:
        is_ok, text = self._simctl("delete", "unavailable")
        return {"is_ok": is_ok, "detail": None if is_ok else text[-300:]}
