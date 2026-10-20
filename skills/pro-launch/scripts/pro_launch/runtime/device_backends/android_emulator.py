"""Android 에뮬레이터 백엔드: AVD 목록 · 띄우기 · 끄기. 원장 키는 AVD 이름, 실행 중 id 는 시리얼."""
from __future__ import annotations

import os
import re
from pathlib import Path

from pro_launch.runtime import android_device, device_boot
from pro_launch.runtime.device_backends.base import FORM_PHONE, FORM_TABLET, Capabilities, DeviceFacts
from pro_launch.runtime.devices import list_devices as list_attached_devices

# 태블릿 판정 기준: 가장 짧은 변의 dp (Android 표준 sw600dp)
TABLET_SMALLEST_WIDTH_DP = 600
BASELINE_DENSITY = 160
_SYSTEM_IMAGE_API_PATTERN = re.compile(r"android-(\d+)")


def avd_home() -> Path:
    """AVD 폴더: ANDROID_AVD_HOME > ANDROID_USER_HOME/avd > ~/.android/avd."""
    if os.environ.get("ANDROID_AVD_HOME"):
        return Path(os.environ["ANDROID_AVD_HOME"])
    if os.environ.get("ANDROID_USER_HOME"):
        return Path(os.environ["ANDROID_USER_HOME"]) / "avd"
    return Path.home() / ".android" / "avd"


def read_avd_config(name: str, home: Path | None = None) -> dict[str, str]:
    """<이름>.avd/config.ini > {키: 값}. 없으면 빈 dict."""
    try:
        text = ((home or avd_home()) / f"{name}.avd" / "config.ini").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    return {k.strip(): v.strip() for k, _, v in (line.partition("=") for line in text.splitlines()) if _}


def form_of_config(config: dict[str, str]) -> str:
    """가장 짧은 변 px * 160 / density >= 600 이면 tablet. 못 읽으면 phone."""
    try:
        width, height = int(config["hw.lcd.width"]), int(config["hw.lcd.height"])
        density = int(config["hw.lcd.density"])
    except (KeyError, ValueError):
        return FORM_PHONE
    return FORM_TABLET if min(width, height) * BASELINE_DENSITY / density >= TABLET_SMALLEST_WIDTH_DP else FORM_PHONE


def api_level_of_config(config: dict[str, str]) -> str | None:
    match = _SYSTEM_IMAGE_API_PATTERN.search(config.get("image.sysdir.1", ""))
    return match.group(1) if match else None


class AndroidEmulatorBackend:
    name = "android_emulator"
    platform = "android"
    capabilities = Capabilities(can_boot=True, can_shutdown=True)

    def list_devices(self) -> list[DeviceFacts]:
        serial_by_avd = {avd: serial for serial, avd in device_boot.running_emulators().items()}
        facts = []
        for avd in list_attached_devices()["android_avds"]:
            config = read_avd_config(avd)
            facts.append(DeviceFacts(key=avd, platform=self.platform, backend=self.name, name=avd,
                                     form=form_of_config(config), os_version=api_level_of_config(config),
                                     is_booted=avd in serial_by_avd, instance=serial_by_avd.get(avd)))
        return facts

    def boot(self, key: str, window: str, scale: float | None) -> dict:
        running = {avd: serial for serial, avd in device_boot.running_emulators().items()}
        if key in running:
            return {"is_ok": True, "instance": running[key], "already_booted": True, "detail": None}
        launched = device_boot.launch_emulator(key, window, scale, is_cold=False)
        if not launched["is_ok"]:
            return {"is_ok": False, "instance": None, "already_booted": False, "detail": launched["detail"]}
        serial = launched["serial"]
        if not device_boot.wait_for_adb_device(serial):
            return {"is_ok": False, "instance": serial, "already_booted": False,
                    "detail": f"에뮬레이터가 adb 에 나타나지 않았다 (로그: {launched['log']})"}
        ready = android_device.wait_until_ready(serial)
        return {"is_ok": bool(ready["is_ready"]), "instance": serial, "already_booted": False,
                "detail": None if ready["is_ready"] else ready.get("detail") or "부팅 완료를 기다리다 멈췄다"}

    def shutdown(self, key: str, instance: str | None) -> dict:
        serial = instance or {avd: s for s, avd in device_boot.running_emulators().items()}.get(key)
        if not serial:
            return {"is_ok": True, "detail": None}
        killed = device_boot.kill_emulator(serial, key)
        return {"is_ok": killed["is_gone"], "detail": None if killed["is_gone"] else f"남은 프로세스 {killed['forced_pids']}"}

    def key_of_instance(self, instance: str) -> str | None:
        return device_boot.emulator_avd_name(instance) if instance.startswith("emulator-") else None
