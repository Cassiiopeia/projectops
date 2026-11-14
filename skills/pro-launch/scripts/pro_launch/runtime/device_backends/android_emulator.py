"""Android emulator backend: AVD list · start · stop · create (using an existing AVD as template) · wipe · delete. Key is the AVD name, running id is the serial."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from common.proc import sdk_tool

from pro_launch.runtime import android_device, device_boot, procs
from pro_launch.runtime.device_backends.base import (FORM_PHONE, FORM_TABLET, Capabilities, DeviceFacts,
                                                    RawCommandPattern, folder_bytes, is_os_satisfied)
from pro_launch.runtime.devices import list_devices as list_attached_devices

# Tablet threshold: shortest side in dp (Android standard sw600dp)
TABLET_SMALLEST_WIDTH_DP = 600
BASELINE_DENSITY = 160
_SYSTEM_IMAGE_API_PATTERN = re.compile(r"android-(\d+)")
AVDMANAGER_TIMEOUT_SECONDS = 120
# Characters outside those allowed in AVD names become _
_AVD_NAME_INVALID_PATTERN = re.compile(r"[^A-Za-z0-9._-]")
# Removed by data wipe (same effect as -wipe-data): user data · cache · snapshots
# Runtime artifacts not carried to clones (the emulator recreates them on every start)
CLONE_SKIP_NAMES = ("hardware-qemu.ini", "emu-launch-params.txt", "multiinstance.lock", "read-snapshot.txt")
CLONE_SKIP_SUFFIXES = (".lock",)
# Hardware profile used when there is no template AVD (an id even old avdmanager knows)
DEFAULT_DEVICE_PROFILE_BY_FORM = {FORM_PHONE: "pixel_6", FORM_TABLET: "pixel_c"}
WIPE_FILE_NAMES = ("userdata-qemu.img", "userdata-qemu.img.qcow2", "cache.img", "cache.img.qcow2")
WIPE_FOLDER_NAMES = ("snapshots",)


def avd_home() -> Path:
    """AVD folder: ANDROID_AVD_HOME > ANDROID_USER_HOME/avd > ~/.android/avd."""
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


def _rewrite_ini(path: Path, values: dict[str, str]) -> None:
    """Change a key's value in the ini (appended if missing). Other lines stay."""
    lines, seen = [], set()
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        key = line.partition("=")[0].strip()
        if key in values:
            lines.append(f"{key}={values[key]}")
            seen.add(key)
        else:
            lines.append(line)
    lines += [f"{key}={value}" for key, value in values.items() if key not in seen]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def avd_folder(name: str, home: Path | None = None) -> Path:
    """AVD folder: path in <name>.ini (name and folder may differ, e.g. Medium_Phone_API_36.1 > Medium_Phone.avd) > <name>.avd."""
    root = home or avd_home()
    declared = _read_ini(root / f"{name}.ini").get("path")
    return Path(declared) if declared and Path(declared).is_dir() else root / f"{name}.avd"


def read_avd_config(name: str, home: Path | None = None) -> dict[str, str]:
    """config.ini of the AVD folder > {key: value}. Empty dict if missing."""
    return _read_ini(avd_folder(name, home) / "config.ini")


def form_of_config(config: dict[str, str]) -> str:
    """tablet if shortest side px * 160 / density >= 600. phone if unreadable."""
    try:
        width, height = int(config["hw.lcd.width"]), int(config["hw.lcd.height"])
        density = int(config["hw.lcd.density"])
    except (KeyError, ValueError):
        return FORM_PHONE
    return FORM_TABLET if min(width, height) * BASELINE_DENSITY / density >= TABLET_SMALLEST_WIDTH_DP else FORM_PHONE


def avdmanager_of_emulator_sdk() -> tuple[str | None, Path | None]:
    """(avdmanager path, SDK root): cmdline-tools of the SDK holding the emulator first > avdmanager on PATH."""
    emulator = sdk_tool("emulator")
    sdk_root = Path(emulator).resolve().parents[1] if emulator else None
    if sdk_root:
        # latest first, otherwise a version folder (avdmanager.bat on Windows)
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
    # Clone (#959): copy the whole AVD folder — qcow2 backing paths are relative so it is not tied to the original, and sign-in lives in userdata
    # so it survives even a cold boot when snapshots do not match. The clone's mark is passed on as unverified
    capabilities = Capabilities(can_boot=True, can_shutdown=True, can_create=True, can_clone=True,
                                can_clone_keep_marks=True)

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
        appeared = device_boot.wait_for_emulator(serial, launched["log"], pid=launched.get("pid"))
        if not appeared["is_ok"]:
            if appeared["problem"]:
                device_boot.kill_emulator(serial, key)
            return {"is_ok": False, "instance": serial, "already_booted": False,
                    "detail": appeared["problem"] or f"emulator did not appear in adb (log: {launched['log']})"}
        ready = android_device.wait_until_ready(serial)
        return {"is_ok": bool(ready["is_ready"]), "instance": serial, "already_booted": False,
                "detail": None if ready["is_ready"] else ready.get("detail") or "stopped while waiting for boot to complete"}

    def shutdown(self, key: str, instance: str | None) -> dict:
        serial = instance or {avd: s for s, avd in device_boot.running_emulators().items()}.get(key)
        if not serial:
            return {"is_ok": True, "detail": None}
        killed = device_boot.kill_emulator(serial, key)
        return {"is_ok": killed["is_gone"], "detail": None if killed["is_gone"] else f"processes left: {killed['forced_pids']}"}

    def key_of_instance(self, instance: str) -> str | None:
        return device_boot.emulator_avd_name(instance) if instance.startswith("emulator-") else None

    # ── Create · wipe · delete (#954) ──

    def _avdmanager(self, *arguments: str) -> tuple[bool, str]:
        """Run avdmanager > (success, error line or output). Uses the one from the emulator's SDK (Homebrew's on PATH sees a different SDK, observed)."""
        avdmanager, sdk_root = avdmanager_of_emulator_sdk()
        if not avdmanager:
            return False, "avdmanager not found (check the Android SDK cmdline-tools install)"
        environment = {**os.environ, **({"ANDROID_SDK_ROOT": str(sdk_root), "ANDROID_HOME": str(sdk_root)} if sdk_root else {})}
        try:
            # Answer no to the prompt asking whether to create a custom hardware profile
            result = subprocess.run([avdmanager, *arguments], input="no\n", capture_output=True, text=True, errors="replace",
                                    timeout=AVDMANAGER_TIMEOUT_SECONDS, env=environment)
        except (OSError, subprocess.SubprocessError) as error:
            return False, str(error)
        text = ((result.stdout or "") + (result.stderr or "")).replace("\r", "\n")
        error_lines = [line.strip() for line in text.splitlines() if line.strip().startswith("Error:")]
        return result.returncode == 0, " ".join(error_lines) or text.strip()[-300:]

    def choose_templates(self, form: str, os_minimum: str | None) -> list[dict]:
        """Template candidates for a new AVD: existing AVDs matching form factor·OS, highest API first > [{package, device_name}] (one per image)."""
        templates: dict[str, tuple[int, dict]] = {}
        for facts in self.list_devices():
            config = read_avd_config(facts.key)
            package = system_image_package(config)
            if package and facts.form == form and is_os_satisfied(facts.os_version, os_minimum):
                templates.setdefault(package, (int(facts.os_version or 0),
                                               {"package": package, "device_name": config.get("hw.device.name")}))
        return [template for _, template in sorted(templates.values(), key=lambda pair: pair[0], reverse=True)]

    def installed_image_templates(self, form: str, os_minimum: str | None) -> list[dict]:
        """System images installed in the SDK (highest API first) + form-factor default profile > template candidates (when template AVDs failed)."""
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
        """Try template candidates in turn (new images avdmanager does not know — e.g. android-36.1 — are skipped)."""
        templates = self.choose_templates(form, os_minimum)
        tried = {template["package"] for template in templates}
        templates += [t for t in self.installed_image_templates(form, os_minimum) if t["package"] not in tried]
        if not templates:
            return {"is_ok": False, "key": None,
                    "detail": f"no {form} AVD (system image) to use as a template — create one in Android Studio, then retry"}
        avd_name, failures = avd_name_of(name), []
        for template in templates:
            arguments = ["create", "avd", "-n", avd_name, "-k", template["package"]]
            if template["device_name"]:
                arguments += ["-d", template["device_name"]]
            is_ok, text = self._avdmanager(*arguments)
            if is_ok:
                return {"is_ok": True, "key": avd_name, "detail": None, "system_image": template["package"]}
            failures.append(f"{template['package']}: {text or 'failed'}")
        return {"is_ok": False, "key": None,
                "detail": (" / ".join(failures)[-400:] + " — if avdmanager is old, update it with sdkmanager 'cmdline-tools;latest'")}

    def erase(self, key: str) -> dict:
        if key in device_boot.running_emulators().values():
            return {"is_ok": False, "detail": "a running emulator is not erased — run device shutdown first"}
        folder = avd_folder(key)
        if not folder.is_dir():
            return {"is_ok": False, "detail": f"AVD folder not found: {folder}"}
        for file_name in WIPE_FILE_NAMES:
            (folder / file_name).unlink(missing_ok=True)
        for folder_name in WIPE_FOLDER_NAMES:
            shutil.rmtree(folder / folder_name, ignore_errors=True)
        return {"is_ok": True, "detail": None}

    def delete(self, key: str) -> dict:
        is_ok, text = self._avdmanager("delete", "avd", "-n", key)
        return {"is_ok": is_ok, "detail": None if is_ok else text[-300:]}

    def raw_command_patterns(self) -> tuple[RawCommandPattern, ...]:
        return (RawCommandPattern(r"\bavdmanager\b.*\bcreate\s+avd\b", "launch_cli.py device create --platform android --reason '<why a new device is needed>'"),
                RawCommandPattern(r"\bavdmanager\b.*\bdelete\s+avd\b", "launch_cli.py device delete --device <AVD name>"),
                RawCommandPattern(r"\bemulator\b.*\s-wipe-data\b", "launch_cli.py device erase --device <AVD name>"),
                RawCommandPattern(r"\badb\b.*\bemu\s+kill\b", "launch_cli.py device shutdown --device <serial>"))

    def disk_bytes(self, key: str) -> int:
        return folder_bytes(avd_folder(key))

    def orphan_avd_entries(self) -> list[dict]:
        """Broken AVD pairs: folder only (no .ini) or .ini only (no folder) > [{name, path, bytes}] — report only."""
        home, orphans = avd_home(), []
        if not home.is_dir():
            return []
        declared_folders = set()
        for ini in home.glob("*.ini"):
            folder = avd_folder(ini.stem, home)
            declared_folders.add(folder.resolve())
            if not folder.is_dir():
                orphans.append({"name": ini.stem, "path": str(ini), "kind": "ini_without_folder", "bytes": 0})
        for folder in home.glob("*.avd"):
            if folder.resolve() not in declared_folders:
                orphans.append({"name": folder.stem, "path": str(folder), "kind": "folder_without_ini",
                                "bytes": folder_bytes(folder)})
        return orphans

    def clone(self, key: str, name: str) -> dict:
        """Clone a powered-off AVD folder > new .ini · update AVD name in config · remove runtime artifacts."""
        if key in device_boot.running_emulators().values():
            return {"is_ok": False, "key": None, "detail": "a running emulator is not cloned"}
        home, clone_name = avd_home(), avd_name_of(name)
        source_folder, target_folder = avd_folder(key, home), home / f"{clone_name}.avd"
        if target_folder.exists() or (home / f"{clone_name}.ini").exists():
            return {"is_ok": False, "key": None, "detail": f"an AVD with the same name already exists: {clone_name}"}
        is_copied, detail = procs.clone_tree(str(source_folder), str(target_folder))
        if not is_copied:
            shutil.rmtree(target_folder, ignore_errors=True)
            return {"is_ok": False, "key": None, "detail": detail or "could not clone the AVD folder"}
        for path in list(target_folder.rglob("*")):
            if path.name not in CLONE_SKIP_NAMES and path.suffix not in CLONE_SKIP_SUFFIXES:
                continue
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink(missing_ok=True)
        _rewrite_ini(target_folder / "config.ini", {"AvdId": clone_name, "avd.ini.displayname": clone_name})
        source_ini = _read_ini(home / f"{key}.ini")
        ini_lines = {**source_ini, "path": str(target_folder), "path.rel": f"avd/{clone_name}.avd"}
        (home / f"{clone_name}.ini").write_text("".join(f"{k}={v}\n" for k, v in ini_lines.items()), encoding="utf-8")
        return {"is_ok": True, "key": clone_name, "detail": None}
