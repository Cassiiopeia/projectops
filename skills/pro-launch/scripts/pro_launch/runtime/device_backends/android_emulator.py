"""Android 에뮬레이터 백엔드: AVD 목록 · 띄우기 · 끄기 · 만들기(기존 AVD 를 본으로) · 초기화 · 지우기. 키는 AVD 이름, 실행 중 id 는 시리얼."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from common.proc import sdk_tool

from pro_launch.runtime import android_device, device_boot
from pro_launch.runtime.device_backends.base import (FORM_PHONE, FORM_TABLET, Capabilities, DeviceFacts,
                                                    RawCommandPattern, is_os_satisfied)
from pro_launch.runtime.devices import list_devices as list_attached_devices

# 태블릿 판정 기준: 가장 짧은 변의 dp (Android 표준 sw600dp)
TABLET_SMALLEST_WIDTH_DP = 600
BASELINE_DENSITY = 160
_SYSTEM_IMAGE_API_PATTERN = re.compile(r"android-(\d+)")
AVDMANAGER_TIMEOUT_SECONDS = 120
# AVD 이름에 쓸 수 있는 글자 밖은 _ 로
_AVD_NAME_INVALID_PATTERN = re.compile(r"[^A-Za-z0-9._-]")
# 데이터 초기화(-wipe-data 와 같은 효과)로 지우는 것: 사용자 데이터 · 캐시 · 스냅샷
# 본 AVD 가 없을 때 쓰는 하드웨어 프로필 (오래된 avdmanager 도 아는 id)
DEFAULT_DEVICE_PROFILE_BY_FORM = {FORM_PHONE: "pixel_6", FORM_TABLET: "pixel_c"}
WIPE_FILE_NAMES = ("userdata-qemu.img", "userdata-qemu.img.qcow2", "cache.img", "cache.img.qcow2")
WIPE_FOLDER_NAMES = ("snapshots",)


def avd_home() -> Path:
    """AVD 폴더: ANDROID_AVD_HOME > ANDROID_USER_HOME/avd > ~/.android/avd."""
    if os.environ.get("ANDROID_AVD_HOME"):
        return Path(os.environ["ANDROID_AVD_HOME"])
    if os.environ.get("ANDROID_USER_HOME"):
        return Path(os.environ["ANDROID_USER_HOME"]) / "avd"
    return Path.home() / ".android" / "avd"


def _read_ini(path: Path) -> dict[str, str]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    return {k.strip(): v.strip() for k, _, v in (line.partition("=") for line in text.splitlines()) if _}


def avd_folder(name: str, home: Path | None = None) -> Path:
    """AVD 폴더: <이름>.ini 의 path (이름과 폴더명이 다를 수 있다, 예: Medium_Phone_API_36.1 > Medium_Phone.avd) > <이름>.avd."""
    root = home or avd_home()
    declared = _read_ini(root / f"{name}.ini").get("path")
    return Path(declared) if declared and Path(declared).is_dir() else root / f"{name}.avd"


def read_avd_config(name: str, home: Path | None = None) -> dict[str, str]:
    """AVD 폴더의 config.ini > {키: 값}. 없으면 빈 dict."""
    return _read_ini(avd_folder(name, home) / "config.ini")


def form_of_config(config: dict[str, str]) -> str:
    """가장 짧은 변 px * 160 / density >= 600 이면 tablet. 못 읽으면 phone."""
    try:
        width, height = int(config["hw.lcd.width"]), int(config["hw.lcd.height"])
        density = int(config["hw.lcd.density"])
    except (KeyError, ValueError):
        return FORM_PHONE
    return FORM_TABLET if min(width, height) * BASELINE_DENSITY / density >= TABLET_SMALLEST_WIDTH_DP else FORM_PHONE


def avdmanager_of_emulator_sdk() -> tuple[str | None, Path | None]:
    """(avdmanager 경로, SDK 루트): 에뮬레이터가 든 SDK 의 cmdline-tools 우선 > PATH 의 avdmanager."""
    emulator = sdk_tool("emulator")
    sdk_root = Path(emulator).resolve().parents[1] if emulator else None
    if sdk_root:
        # latest 를 먼저, 없으면 버전 폴더 (Windows 는 avdmanager.bat)
        candidates = sorted((sdk_root / "cmdline-tools").glob("*/bin/avdmanager*"),
                            key=lambda path: (path.parent.parent.name != "latest", path.parent.parent.name))
        if candidates:
            return str(candidates[0]), sdk_root
    return sdk_tool("avdmanager"), sdk_root


def system_image_package(config: dict[str, str]) -> str | None:
    """image.sysdir.1=system-images/android-36/google_apis/arm64-v8a/ > system-images;android-36;google_apis;arm64-v8a"""
    folder = config.get("image.sysdir.1", "").strip("/\\")
    return folder.replace("/", ";").replace("\\", ";") if folder.startswith("system-images") else None


def avd_name_of(name: str) -> str:
    return _AVD_NAME_INVALID_PATTERN.sub("_", name)


def api_level_of_config(config: dict[str, str]) -> str | None:
    match = _SYSTEM_IMAGE_API_PATTERN.search(config.get("image.sysdir.1", ""))
    return match.group(1) if match else None


class AndroidEmulatorBackend:
    name = "android_emulator"
    platform = "android"
    capabilities = Capabilities(can_boot=True, can_shutdown=True, can_create=True)

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

    # ── 만들기 · 초기화 · 지우기 (#954) ──

    def _avdmanager(self, *arguments: str) -> tuple[bool, str]:
        """avdmanager 실행 > (성공, 오류 줄 또는 출력). 에뮬레이터와 같은 SDK 의 것을 쓴다 (PATH 의 Homebrew 것은 다른 SDK 를 본다, 실측)."""
        avdmanager, sdk_root = avdmanager_of_emulator_sdk()
        if not avdmanager:
            return False, "avdmanager 를 찾지 못했다 (Android SDK cmdline-tools 설치 확인)"
        environment = {**os.environ, **({"ANDROID_SDK_ROOT": str(sdk_root), "ANDROID_HOME": str(sdk_root)} if sdk_root else {})}
        try:
            # 사용자 하드웨어 프로필을 만들지 묻는 질문에 no
            result = subprocess.run([avdmanager, *arguments], input="no\n", capture_output=True, text=True,
                                    timeout=AVDMANAGER_TIMEOUT_SECONDS, env=environment)
        except (OSError, subprocess.SubprocessError) as error:
            return False, str(error)
        text = ((result.stdout or "") + (result.stderr or "")).replace("\r", "\n")
        error_lines = [line.strip() for line in text.splitlines() if line.strip().startswith("Error:")]
        return result.returncode == 0, " ".join(error_lines) or text.strip()[-300:]

    def choose_templates(self, form: str, os_minimum: str | None) -> list[dict]:
        """새 AVD 의 본 후보: 같은 폼팩터·OS 조건의 기존 AVD, API 높은 순 > [{package, device_name}] (같은 이미지는 하나)."""
        templates: dict[str, tuple[int, dict]] = {}
        for facts in self.list_devices():
            config = read_avd_config(facts.key)
            package = system_image_package(config)
            if package and facts.form == form and is_os_satisfied(facts.os_version, os_minimum):
                templates.setdefault(package, (int(facts.os_version or 0),
                                               {"package": package, "device_name": config.get("hw.device.name")}))
        return [template for _, template in sorted(templates.values(), key=lambda pair: pair[0], reverse=True)]

    def installed_image_templates(self, form: str, os_minimum: str | None) -> list[dict]:
        """SDK 에 설치된 시스템 이미지 (API 높은 순) + 폼팩터 기본 프로필 > 본 후보 (본 AVD 가 실패했을 때)."""
        emulator = sdk_tool("emulator")
        images_root = Path(emulator).resolve().parents[1] / "system-images" if emulator else None
        if not images_root or not images_root.is_dir():
            return []
        found = []
        for image in images_root.glob("android-*/*/*"):
            api = _SYSTEM_IMAGE_API_PATTERN.search(image.parts[-3])
            if api and (image / "system.img").exists() and is_os_satisfied(api.group(1), os_minimum):
                found.append((int(api.group(1)), {"package": ";".join(("system-images", *image.parts[-3:])),
                                                  "device_name": DEFAULT_DEVICE_PROFILE_BY_FORM.get(form)}))
        return [template for _, template in sorted(found, key=lambda pair: pair[0], reverse=True)]

    def create(self, name: str, form: str, os_minimum: str | None) -> dict:
        """본 후보를 차례로 시도 (avdmanager 가 모르는 새 이미지 — 예: android-36.1 — 는 건너뛴다)."""
        templates = self.choose_templates(form, os_minimum)
        tried = {template["package"] for template in templates}
        templates += [t for t in self.installed_image_templates(form, os_minimum) if t["package"] not in tried]
        if not templates:
            return {"is_ok": False, "key": None,
                    "detail": f"본으로 쓸 {form} AVD(시스템 이미지)가 없다 — Android Studio 에서 하나 만든 뒤 다시"}
        avd_name, failures = avd_name_of(name), []
        for template in templates:
            arguments = ["create", "avd", "-n", avd_name, "-k", template["package"]]
            if template["device_name"]:
                arguments += ["-d", template["device_name"]]
            is_ok, text = self._avdmanager(*arguments)
            if is_ok:
                return {"is_ok": True, "key": avd_name, "detail": None, "system_image": template["package"]}
            failures.append(f"{template['package']}: {text or '실패'}")
        return {"is_ok": False, "key": None,
                "detail": (" / ".join(failures)[-400:] + " — avdmanager 가 오래됐으면 sdkmanager 'cmdline-tools;latest' 로 올린다")}

    def erase(self, key: str) -> dict:
        if key in device_boot.running_emulators().values():
            return {"is_ok": False, "detail": "켜져 있는 에뮬레이터는 초기화하지 않는다 — device shutdown 먼저"}
        folder = avd_folder(key)
        if not folder.is_dir():
            return {"is_ok": False, "detail": f"AVD 폴더가 없다: {folder}"}
        for file_name in WIPE_FILE_NAMES:
            (folder / file_name).unlink(missing_ok=True)
        for folder_name in WIPE_FOLDER_NAMES:
            shutil.rmtree(folder / folder_name, ignore_errors=True)
        return {"is_ok": True, "detail": None}

    def delete(self, key: str) -> dict:
        is_ok, text = self._avdmanager("delete", "avd", "-n", key)
        return {"is_ok": is_ok, "detail": None if is_ok else text[-300:]}

    def raw_command_patterns(self) -> tuple[RawCommandPattern, ...]:
        return (RawCommandPattern(r"\bavdmanager\b.*\bcreate\s+avd\b", "launch_cli.py device create --platform android --reason '<왜 새 기기가 필요한가>'"),
                RawCommandPattern(r"\bavdmanager\b.*\bdelete\s+avd\b", "launch_cli.py device delete --device <AVD 이름>"),
                RawCommandPattern(r"\bemulator\b.*\s-wipe-data\b", "launch_cli.py device erase --device <AVD 이름>"),
                RawCommandPattern(r"\badb\b.*\bemu\s+kill\b", "launch_cli.py device shutdown --device <시리얼>"))
