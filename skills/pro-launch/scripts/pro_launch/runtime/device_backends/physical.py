"""실기기 백엔드 (USB Android): 빌리기·반납만. 켜고 끄고 만들지 않는다."""
from __future__ import annotations

from pro_launch.runtime.device_backends.base import FORM_PHONE, Capabilities, DeviceFacts, RawCommandPattern
from pro_launch.runtime.devices import list_devices as list_attached_devices


class PhysicalAndroidBackend:
    name = "physical_android"
    platform = "android"
    capabilities = Capabilities(is_physical=True)

    def list_devices(self) -> list[DeviceFacts]:
        return [DeviceFacts(key=serial, platform=self.platform, backend=self.name, name=serial, form=FORM_PHONE,
                            os_version=None, is_booted=True, instance=serial)
                for serial in list_attached_devices()["android"] if not serial.startswith("emulator-")]

    def boot(self, key: str, window: str, scale: float | None) -> dict:
        return {"is_ok": False, "instance": key, "already_booted": True, "detail": "실기기는 켜고 끄지 않는다"}

    def shutdown(self, key: str, instance: str | None) -> dict:
        return {"is_ok": False, "detail": "실기기는 켜고 끄지 않는다"}

    def key_of_instance(self, instance: str) -> str | None:
        return instance if not instance.startswith("emulator-") else None

    def create(self, name: str, form: str, os_minimum: str | None) -> dict:
        return {"is_ok": False, "key": None, "detail": "실기기는 만들 수 없다"}

    def erase(self, key: str) -> dict:
        return {"is_ok": False, "detail": "실기기는 초기화하지 않는다"}

    def delete(self, key: str) -> dict:
        return {"is_ok": False, "detail": "실기기는 지울 수 없다"}

    def raw_command_patterns(self) -> tuple[RawCommandPattern, ...]:
        return ()
