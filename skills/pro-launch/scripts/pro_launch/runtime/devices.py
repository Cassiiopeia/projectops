"""Finding attached devices · binding roles · picking (Android adb, iOS simctl)."""
from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path

from common.proc import run, sdk_tool
from common.state import launch_file

from pro_launch.runtime.context import state_home
from pro_launch.runtime.host_resources import critical_pressure_failure
from pro_launch.runtime.output import out, set_area


def list_devices() -> dict:
    android: list[str] = []
    adb = sdk_tool("adb")
    if adb:
        for line in run([adb, "devices"]).splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "device":
                android.append(parts[0])
    ios: list[str] = []
    if shutil.which("xcrun"):
        for line in run(["xcrun", "simctl", "list", "devices", "booted"]).splitlines():
            m = re.match(r"\s+(.+?)\s+\(([\w-]{36})\)\s+\(Booted\)", line)
            if m:
                ios.append(f"{m.group(1)} [{m.group(2)}]")
    avds: list[str] = []
    emu = sdk_tool("emulator")
    if emu:
        avds = [l.strip() for l in run([emu, "-list-avds"]).splitlines()
                if l.strip() and not l.startswith("INFO")]
    return {"android": android, "ios_booted": ios, "android_avds": avds,
            "adb_path": adb, "emulator_path": emu}


def ios_udids(dev: dict) -> list[str]:
    return [re.search(r"\[([\w-]{36})\]$", s).group(1)
            for s in dev.get("ios_booted", []) if re.search(r"\[([\w-]{36})\]$", s)]


def sole_device(platform: str | None = None) -> str | None:
    """Default DEV candidate for env.sh: the id if exactly one attached device remains after excluding those held by other sessions (only that platform if given).

    If this session holds exactly one device, that comes first. None if undecided — never fills DEV with someone else's device (#972).
    """
    from pro_launch.runtime import device_claims
    try:
        dev = list_devices()
        found = [("android", serial) for serial in dev["android"]] + [("ios", udid) for udid in ios_udids(dev)]
        found = [dev_id for kind, dev_id in found if platform in (None, kind)]
        free = [dev_id for dev_id in found if device_claims.check_device_owner(dev_id) is None]
        owned = [dev_id for dev_id in free if _is_live_own(device_claims.device_owner(dev_id), device_claims)]
    except Exception:   # noqa: BLE001 — picking a default is auxiliary. Left empty if none can be picked
        return None
    if len(owned) == 1:
        return owned[0]
    return free[0] if len(free) == 1 else None


def _is_live_own(owner: dict | None, device_claims) -> bool:
    return bool(owner and owner.get("is_live") and owner.get("session") == device_claims.session_identity())


# ── Role ↔ device (#583) ─────────────────────────────────────────────────
#
# Here we **only bind and compare**. adb is not wrapped — its surface is too wide; wrapping it becomes
# an adb reimplementation, and any escape hatch lets commands without `-s` leak through again.
_DEVICES_FILE = "devices.json"


_DEVICES_SCHEMA = 1


def devices_path(root: Path) -> Path:
    state_home(root)
    return launch_file(root, _DEVICES_FILE)


def load_devices(root: Path) -> dict:
    """{package, bindings:[{role, serial, note?}]} — **list order is the DEV1·DEV2 number.**"""
    p = devices_path(root)
    empty = {"package": None, "bindings": []}
    if not p.is_file():
        return empty
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty
    if not isinstance(data, dict):
        return empty
    rows = [r for r in (data.get("bindings") or [])
            if isinstance(r, dict) and r.get("role") and r.get("serial")]
    return {"package": data.get("package"), "bindings": rows}


def save_devices(root: Path, package: str | None, bindings: list[dict]) -> Path:
    p = devices_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"schema": _DEVICES_SCHEMA, "package": package,
                             "bindings": bindings},
                            ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return p


def adb_shell(serial: str, *args: str, timeout: int = 20) -> str:
    adb = sdk_tool("adb")
    if not adb:
        return ""
    return run([adb, "-s", serial, "shell", *args], timeout=timeout).replace("\r", "")


def build_info(serial: str, package: str | None) -> dict:
    """What is installed on the device. **Do not measure by version** — a rebuild that only changed compile-time flags
    has the same version (#603). Measuring by APK hash shows when only one side was reinstalled."""
    info: dict = {"screen": None, "package": package, "version": None,
                  "apk": None, "apk_by": None}
    m = re.search(r"Physical size:\s*(\d+x\d+)", adb_shell(serial, "wm", "size"))
    if m:
        info["screen"] = m.group(1)
    if not package:
        return info
    dump = adb_shell(serial, "dumpsys", "package", package, timeout=30)
    if "Unable to find package" in dump or not dump.strip():
        info["installed"] = False
        return info
    info["installed"] = True
    vn = re.search(r"versionName=(\S+)", dump)
    vc = re.search(r"versionCode=(\d+)", dump)
    if vn or vc:
        info["version"] = "%s+%s" % (vn.group(1) if vn else "?", vc.group(1) if vc else "?")
    apk = None
    for line in adb_shell(serial, "pm", "path", package).splitlines():
        if line.startswith("package:"):
            apk = line.split(":", 1)[1].strip()
            break
    if apk:
        for tool in ("sha1sum", "md5sum"):
            head = adb_shell(serial, tool, apk, timeout=60).split()
            if head and re.fullmatch(r"[0-9a-f]{32,40}", head[0]):
                info["apk"], info["apk_by"] = head[0], tool
                break
    if not info["apk"]:
        m2 = re.search(r"lastUpdateTime=(\S+\s+\S+)", dump)
        if m2:
            info["apk"], info["apk_by"] = m2.group(1), "lastUpdateTime"
    return info


def build_mismatch(rows: list[dict]) -> list[dict]:
    """Do installed builds differ between roles. Same version with different hashes means only one side was reinstalled."""
    seen = [(r["role"], (r.get("build") or {}).get("apk"),
             (r.get("build") or {}).get("version")) for r in rows if r.get("role")]
    known = [(role, apk, ver) for role, apk, ver in seen if apk]
    if len(known) < 2 or len({apk for _, apk, _ in known}) == 1:
        return []
    vers = {ver for _, _, ver in known}
    detail = ("Same version but different APKs — only one side may have been reinstalled"
              if len(vers) == 1 else "The installed versions differ")
    return [{"roles": [role for role, _, _ in known], "field": "apk", "detail": detail}]


def pick_device(want: str | None) -> tuple[str | None, str | None, dict]:
    """(platform, id, device list). --device → $DEV → the only attached device if there is just one."""
    dev = list_devices()
    udids = ios_udids(dev)
    cand = want or os.environ.get("DEV") or None
    if not cand:
        every = dev["android"] + udids
        cand = every[0] if len(every) == 1 else None
    if not cand:
        return None, None, dev
    if cand in dev["android"]:
        set_area("android")
        return "android", cand, dev
    if cand in udids or cand == "booted":
        set_area("ios")
        return "ios", cand, dev
    return None, cand, dev


def shutdown_device_fields(target: str | None, dev: dict) -> dict | None:
    """device_shutdown response field if the requested device is a powered-off simulator·AVD. Otherwise None (#972)."""
    if not target:
        return None
    from pro_launch.runtime import device_boot
    simulators = [s for s in device_boot.find_ios_simulators(target) if s.get("state") != "Booted"]
    if len(simulators) == 1:
        simulator = simulators[0]
        return {"ok": False, "code": "device_shutdown", "platform": "ios", "device": simulator["udid"],
                "name": simulator["name"], "state": simulator["state"],
                "error": f"Simulator '{target}' is shut down ({simulator['state']})",
                "next": f"device boot --device {simulator['udid']}  # boot it, then call again (to borrow one: device acquire --platform ios)"}
    if target in dev.get("android_avds", []) and target not in device_boot.running_emulators().values():
        return {"ok": False, "code": "device_shutdown", "platform": "android", "device": target,
                "error": f"AVD '{target}' is shut down",
                "next": f"device boot --device {target}  # boot it, then call again with the serial it prints (emulator-NNNN)"}
    return None


def no_device_response(dev: dict, want: str | None) -> int:
    shutdown = shutdown_device_fields(want or os.environ.get("DEV"), dev)
    if shutdown is not None:
        return out(shutdown)
    is_boot_suggested = not (dev["android"] or dev["ios_booted"])
    # Check host memory before suggesting a new device boot — on critical, ask the user instead of booting (#883)
    if is_boot_suggested:
        pressure_failure = critical_pressure_failure("device boot")
        if pressure_failure:
            return out({**pressure_failure, "android_avds": dev["android_avds"]})
    return out({
        "ok": False, "code": "no_device",
        "error": (f"Device '{want}' not found" if want
                  else "Cannot tell which device to use (none attached, or several)"),
        "android": dev["android"], "ios_booted": dev["ios_booted"],
        "android_avds": dev["android_avds"],
        "next": ("device boot --device <AVD name|simulator name|UDID>" if not
                 (dev["android"] or dev["ios_booted"]) else "Pick one with --device"),
    })
