"""기기 백엔드 (#953) — simctl·adb 없이 가짜 목록으로 검사한다."""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from pro_launch.runtime.device_backends import android_emulator  # noqa: E402


def test_android_erase_removes_user_data_but_not_config(monkeypatch, tmp_path):
    monkeypatch.setenv("ANDROID_AVD_HOME", str(tmp_path))
    folder = tmp_path / "Phone.avd"
    (folder / "snapshots").mkdir(parents=True)
    for name in ("config.ini", "userdata-qemu.img", "cache.img"):
        (folder / name).write_text("x", encoding="utf-8")
    monkeypatch.setattr(android_emulator.device_boot, "running_emulators", lambda: {})
    assert android_emulator.AndroidEmulatorBackend().erase("Phone")["is_ok"]
    assert sorted(p.name for p in folder.iterdir()) == ["config.ini"]


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
