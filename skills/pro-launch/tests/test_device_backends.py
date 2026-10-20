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


def test_capabilities_follow_experiment_results():
    # 실측: iOS 복제는 데이터·키체인 유지 (#955) · Android 는 AVD 폴더 복제 (#959), 읽기전용 동시 실행은 쓰지 않는다
    for name in ("ios_simulator", "android_emulator"):
        capabilities = device_backends.backend_named(name).capabilities
        assert capabilities.can_create and capabilities.can_clone and capabilities.can_clone_keep_marks
    for backend in device_backends.BACKENDS:
        assert not backend.capabilities.can_readonly_instance
    assert device_backends.backend_named("android_emulator").capabilities.can_create
    physical = device_backends.backend_named("physical_android").capabilities
    assert physical.is_physical and not (physical.can_boot or physical.can_create)


def test_ios_create_picks_newest_runtime_and_family(monkeypatch):
    backend = ios_simulator.IosSimulatorBackend()
    runtimes = {"runtimes": [
        {"identifier": "com.apple.CoreSimulator.SimRuntime.iOS-17-5", "version": "17.5", "isAvailable": True,
         "supportedDeviceTypes": [{"identifier": "iPhone-15", "productFamily": "iPhone"}]},
        {"identifier": "com.apple.CoreSimulator.SimRuntime.iOS-18-3", "version": "18.3.1", "isAvailable": True,
         "supportedDeviceTypes": [{"identifier": "iPad-Air", "productFamily": "iPad"},
                                  {"identifier": "iPhone-16", "productFamily": "iPhone"}]}]}
    import json as json_module
    calls = []

    def fake_simctl(*arguments):
        calls.append(arguments)
        if arguments[:2] == ("list", "runtimes"):
            return True, json_module.dumps(runtimes)
        return True, "3F328F1A-16D1-453B-A0D3-94CDC21C4189"
    monkeypatch.setattr(backend, "_simctl", fake_simctl)
    assert backend.choose_device_type("phone", None) == ("iPhone-16", "com.apple.CoreSimulator.SimRuntime.iOS-18-3")
    assert backend.choose_device_type("tablet", ">=19") is None
    created = backend.create("pro-launch test", "phone", "17")
    assert created["is_ok"] and calls[-1][0] == "create"


def test_android_system_image_package_and_avd_name():
    config = {"image.sysdir.1": "system-images/android-36.1/google_apis_playstore/arm64-v8a/"}
    assert android_emulator.system_image_package(config) == "system-images;android-36.1;google_apis_playstore;arm64-v8a"
    assert android_emulator.avd_name_of("pro-launch 20261020-1530") == "pro-launch_20261020-1530"


def test_avd_folder_follows_ini_path(tmp_path):
    folder = tmp_path / "Medium_Phone.avd"
    folder.mkdir()
    (tmp_path / "Medium_Phone_API_36.1.ini").write_text(f"path={folder}\n", encoding="utf-8")
    assert android_emulator.avd_folder("Medium_Phone_API_36.1", tmp_path) == folder


def test_android_erase_removes_user_data_but_not_config(monkeypatch, tmp_path):
    monkeypatch.setenv("ANDROID_AVD_HOME", str(tmp_path))
    folder = tmp_path / "Phone.avd"
    (folder / "snapshots").mkdir(parents=True)
    for name in ("config.ini", "userdata-qemu.img", "cache.img"):
        (folder / name).write_text("x", encoding="utf-8")
    monkeypatch.setattr(android_emulator.device_boot, "running_emulators", lambda: {})
    assert android_emulator.AndroidEmulatorBackend().erase("Phone")["is_ok"]
    assert sorted(p.name for p in folder.iterdir()) == ["config.ini"]


def test_raw_command_patterns_come_from_backends():
    import re
    patterns = device_backends.raw_command_patterns()
    blocked = ["xcrun simctl create x y z", "xcrun simctl delete ABC", "avdmanager create avd -n X -k p",
               "emulator -avd X -wipe-data", "adb -s emulator-5554 emu kill"]
    allowed = ["xcrun simctl boot ABC", "xcrun simctl io booted screenshot a.png", "adb shell am start x"]
    assert all(any(re.search(p.pattern, command) for p in patterns) for command in blocked)
    assert not any(re.search(p.pattern, command) for p in patterns for command in allowed)


def test_avdmanager_comes_from_the_emulator_sdk_not_path(monkeypatch, tmp_path):
    sdk = tmp_path / "sdk"
    (sdk / "emulator").mkdir(parents=True)
    (sdk / "emulator" / "emulator").write_text("", encoding="utf-8")
    for version in ("9.0", "latest"):
        tool = sdk / "cmdline-tools" / version / "bin" / "avdmanager"
        tool.parent.mkdir(parents=True)
        tool.write_text("", encoding="utf-8")
    monkeypatch.setattr(android_emulator, "sdk_tool",
                        lambda name: str(sdk / "emulator" / "emulator") if name == "emulator" else "/opt/homebrew/bin/avdmanager")
    path, root = android_emulator.avdmanager_of_emulator_sdk()
    assert path.endswith("cmdline-tools/latest/bin/avdmanager") and root == sdk.resolve()


def test_android_create_falls_back_to_next_template(monkeypatch):
    backend = android_emulator.AndroidEmulatorBackend()
    monkeypatch.setattr(backend, "choose_templates", lambda form, os_minimum: [
        {"package": "system-images;android-36.1;x;arm64-v8a", "device_name": "medium_phone"}])
    monkeypatch.setattr(backend, "installed_image_templates", lambda form, os_minimum: [
        {"package": "system-images;android-34;google_apis;arm64-v8a", "device_name": "pixel_6"}])
    tried = []

    def fake_avdmanager(*arguments):
        tried.append(arguments[arguments.index("-k") + 1])
        return ("android-34" in tried[-1]), "Error: Package path is not valid."
    monkeypatch.setattr(backend, "_avdmanager", fake_avdmanager)
    created = backend.create("pro-launch x", "phone", None)
    assert created["is_ok"] and created["system_image"].endswith("android-34;google_apis;arm64-v8a")
    assert len(tried) == 2


def test_emulator_without_acceleration_is_reported_from_log(tmp_path):
    from pro_launch.runtime import device_boot
    log = tmp_path / "emulator.log"
    log.write_text("WARNING | hvf is not enabled on this aarch64 host.\n", encoding="utf-8")
    assert "HVF" in device_boot.emulator_start_problem(log)
    log.write_text("INFO | boot completed\n", encoding="utf-8")
    assert device_boot.emulator_start_problem(log) is None
    assert device_boot.emulator_start_problem(tmp_path / "missing.log") is None


def test_wait_for_emulator_stops_early_on_problem(monkeypatch, tmp_path):
    from pro_launch.runtime import device_boot
    log = tmp_path / "emulator.log"
    log.write_text("qemu-system-aarch64-headless: qemu_mprotect__osdep: mprotect failed: Permission denied\n",
                   encoding="utf-8")
    monkeypatch.setattr(device_boot, "sdk_tool", lambda name: "/x/adb")
    monkeypatch.setattr(device_boot, "_run", lambda command, timeout: (True, "List of devices attached\nemulator-5570\toffline\n"))
    monkeypatch.setattr(device_boot.time, "sleep", lambda seconds: (_ for _ in ()).throw(AssertionError("기다리면 안 된다")))
    result = device_boot.wait_for_emulator("emulator-5570", log, timeout_seconds=60)
    assert result["is_ok"] is False and result["problem"]


def _fake_avd(home, name: str) -> Path:
    folder = home / f"{name}.avd"
    folder.mkdir(parents=True)
    (folder / "config.ini").write_text(f"AvdId={name}\navd.ini.displayname={name}\nhw.lcd.width=1080\n", encoding="utf-8")
    for file_name in ("userdata-qemu.img.qcow2", "userdata-qemu.img", "hardware-qemu.ini", "multiinstance.lock"):
        (folder / file_name).write_bytes(b"data-" + file_name.encode())
    (home / f"{name}.ini").write_text(f"avd.ini.encoding=UTF-8\npath={folder}\npath.rel=avd/{name}.avd\ntarget=android-34\n",
                                       encoding="utf-8")
    return folder


def test_android_clone_copies_folder_and_rewrites_names(monkeypatch, tmp_path):
    monkeypatch.setenv("ANDROID_AVD_HOME", str(tmp_path))
    monkeypatch.setattr(android_emulator.device_boot, "running_emulators", lambda: {})
    source = _fake_avd(tmp_path, "Tablet")
    result = android_emulator.AndroidEmulatorBackend().clone("Tablet", "pro-launch copy")
    assert result["is_ok"] and result["key"] == "pro-launch_copy"
    target = tmp_path / "pro-launch_copy.avd"
    assert (target / "userdata-qemu.img.qcow2").read_bytes() == b"data-userdata-qemu.img.qcow2"
    assert not (target / "hardware-qemu.ini").exists() and not (target / "multiinstance.lock").exists()
    assert "AvdId=pro-launch_copy" in (target / "config.ini").read_text(encoding="utf-8")
    ini = (tmp_path / "pro-launch_copy.ini").read_text(encoding="utf-8")
    assert f"path={target}" in ini and "path.rel=avd/pro-launch_copy.avd" in ini and "target=android-34" in ini
    assert (source / "hardware-qemu.ini").exists() and "AvdId=Tablet" in (source / "config.ini").read_text(encoding="utf-8")
    assert android_emulator.avd_folder("pro-launch_copy", tmp_path) == target


def test_android_clone_refuses_running_or_existing(monkeypatch, tmp_path):
    monkeypatch.setenv("ANDROID_AVD_HOME", str(tmp_path))
    _fake_avd(tmp_path, "Tablet")
    backend = android_emulator.AndroidEmulatorBackend()
    monkeypatch.setattr(android_emulator.device_boot, "running_emulators", lambda: {"emulator-5554": "Tablet"})
    assert backend.clone("Tablet", "copy")["is_ok"] is False
    monkeypatch.setattr(android_emulator.device_boot, "running_emulators", lambda: {})
    _fake_avd(tmp_path, "copy")
    assert "이미 있다" in backend.clone("Tablet", "copy")["detail"]
