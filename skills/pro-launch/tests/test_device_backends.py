"""기기 백엔드 (#953) — simctl·adb 없이 가짜 목록으로 검사한다."""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from pro_launch.runtime import device_backends  # noqa: E402
from pro_launch.runtime.device_backends import android_emulator, ios_simulator, physical  # noqa: E402

UDID = "3F328F1A-16D1-453B-A0D3-94CDC21C4189"


def test_ios_lists_only_ios_runtimes_with_form_and_version(monkeypatch):
    monkeypatch.setattr(ios_simulator.device_boot, "ios_simulators", lambda: [
        {"udid": UDID, "name": "iPhone 16 Pro", "state": "Booted",
         "runtime": "com.apple.CoreSimulator.SimRuntime.iOS-18-3"},
        {"udid": "X", "name": "iPad Air 11-inch (M2)", "state": "Shutdown",
         "runtime": "com.apple.CoreSimulator.SimRuntime.iOS-18-3"},
        {"udid": "W", "name": "Apple Watch", "state": "Shutdown",
         "runtime": "com.apple.CoreSimulator.SimRuntime.watchOS-11-2"}])
    facts = ios_simulator.IosSimulatorBackend().list_devices()
    assert [(f.name, f.form, f.os_version, f.is_booted, f.instance) for f in facts] == [
        ("iPhone 16 Pro", "phone", "18.3", True, UDID), ("iPad Air 11-inch (M2)", "tablet", "18.3", False, None)]


def test_android_form_from_config_ini(tmp_path):
    for name, (width, height, density) in {"Phone": (1080, 2400, 420), "Tab": (1600, 2560, 320)}.items():
        folder = tmp_path / f"{name}.avd"
        folder.mkdir()
        (folder / "config.ini").write_text(
            f"hw.lcd.width={width}\nhw.lcd.height={height}\nhw.lcd.density={density}\n"
            "image.sysdir.1=system-images/android-36/google_apis/arm64-v8a/\n", encoding="utf-8")
    phone = android_emulator.read_avd_config("Phone", tmp_path)
    assert android_emulator.form_of_config(phone) == "phone"
    assert android_emulator.form_of_config(android_emulator.read_avd_config("Tab", tmp_path)) == "tablet"
    assert android_emulator.api_level_of_config(phone) == "36"
    assert android_emulator.form_of_config({}) == "phone"


def test_android_lists_avds_with_running_serial(monkeypatch, tmp_path):
    monkeypatch.setenv("ANDROID_AVD_HOME", str(tmp_path))
    monkeypatch.setattr(android_emulator.device_boot, "running_emulators", lambda: {"emulator-5554": "Medium_Phone"})
    monkeypatch.setattr(android_emulator, "list_attached_devices",
                        lambda: {"android_avds": ["Medium_Phone", "Tablet"], "android": ["emulator-5554"]})
    facts = {f.key: f for f in android_emulator.AndroidEmulatorBackend().list_devices()}
    assert facts["Medium_Phone"].instance == "emulator-5554" and facts["Medium_Phone"].is_booted
    assert facts["Tablet"].instance is None and not facts["Tablet"].is_booted


def test_physical_lists_only_non_emulator_serials(monkeypatch):
    monkeypatch.setattr(physical, "list_attached_devices", lambda: {"android": ["emulator-5554", "R5CT1234"]})
    assert [f.key for f in physical.PhysicalAndroidBackend().list_devices()] == ["R5CT1234"]


def test_backend_registry_covers_ios_android_physical():
    names = {backend.name for backend in device_backends.BACKENDS}
    assert names == {"ios_simulator", "android_emulator", "physical_android"}
    assert all(backend.platform in ("ios", "android") for backend in device_backends.BACKENDS)


def test_capabilities_phase1_have_no_create_or_clone():
    for backend in device_backends.BACKENDS:
        capabilities = backend.capabilities
        assert not (capabilities.can_create or capabilities.can_clone or capabilities.can_readonly_instance)
    assert device_backends.backend_named("physical_android").capabilities.is_physical
    assert not device_backends.backend_named("physical_android").capabilities.can_boot
