"""`device locale` · `device appearance` — 기기 전역 설정(언어·지역·다크 모드)을 바꾸고 원래 값을 기록한다 (#929 · #925).

바꾸기 전 값을 device_claims 에 남기므로 `--restore` 나 `device release` 가 되돌린다.
iOS 시스템 언어는 기기를 다시 켜야 반영된다(그 시뮬레이터의 앱 상태가 사라진다). Android 앱별 언어는 API 33+.
"""
from __future__ import annotations

import re

from common.proc import sdk_tool

from pro_launch.commands.device.claims import refuse_other_session_owner, resolve_device
from pro_launch.commands.device.setting_support import (
    fail as _fail, record_change as _recorded, restore_recorded as _restore, run_command as _run,
)
from pro_launch.runtime import device_boot
from pro_launch.runtime.device_claims import pop_device_setting
from pro_launch.runtime.output import out

# Android 앱별 언어(cmd locale set-app-locales)가 생긴 API
APP_LOCALE_MINIMUM_SDK = 33
APPEARANCE_MODES = ("light", "dark")
_ANDROID_NIGHT_BY_MODE = {"light": "no", "dark": "yes"}


# ── appearance ───────────────────────────────────────────────────────────


def run_appearance(args) -> int:
    platform, dev_id, err = resolve_device(args)
    if err is not None:
        return err
    if args.restore:
        return _restore(dev_id, platform, "appearance", "appearance")
    if args.mode not in APPEARANCE_MODES:
        return _fail("args_required", "light 또는 dark 를 준다", "device appearance dark --device $DEV")
    if not args.yes and (refusal := refuse_other_session_owner(dev_id, "appearance")) is not None:
        return refusal
    if platform == "ios":
        read = ["xcrun", "simctl", "ui", dev_id, "appearance"]
        is_read, before = _run(read)
        change = [*read, args.mode]
        restore = [[*read, before.strip()]] if is_read and before.strip() in APPEARANCE_MODES else []
    else:
        adb = sdk_tool("adb")
        if not adb:
            return _fail("tool_missing", "adb 를 찾지 못했다", "doctor 의 adb_path 확인")
        night = [adb, "-s", dev_id, "shell", "cmd", "uimode", "night"]
        is_read, text = _run(night)
        before = (re.search(r"Night mode:\s*(\w+)", text) or [None, None])[1] if is_read else None
        change = [*night, _ANDROID_NIGHT_BY_MODE[args.mode]]
        restore = [[*night, before]] if before in ("yes", "no", "auto") else []
    if restore:
        _recorded("appearance", dev_id, before, restore, args)
    is_changed, detail = _run(change)
    if not is_changed:
        pop_device_setting(dev_id, "appearance")
        return _fail("appearance_failed", detail[-300:] or "외관을 바꾸지 못했다", "device list 로 기기 상태를 확인한다")
    return out({"action": "appearance", "platform": platform, "device": dev_id, "mode": args.mode,
                "before": before, "is_restorable": bool(restore),
                "summary": f"{args.mode} 모드로 바꿈 (원래: {before})",
                "next": "device appearance --restore  # 또는 device release"})


# ── locale ───────────────────────────────────────────────────────────────


def _ios_domain_values(udid: str, domain: str) -> dict:
    """iOS defaults 의 AppleLanguages(목록) · AppleLocale(문자열). 없으면 None."""
    base = ["xcrun", "simctl", "spawn", udid, "defaults", "read", domain]
    is_ok, text = _run([*base, "AppleLanguages"])
    languages = [t.strip().strip('",') for t in text.splitlines() if t.strip() not in ("(", ")")] if is_ok else None
    is_ok, text = _run([*base, "AppleLocale"])
    return {"languages": languages, "locale": text.strip() if is_ok else None}


def _ios_write_commands(udid: str, domain: str, values: dict) -> list[list[str]]:
    """값을 쓰는 명령들. 값이 None 이면 키를 지운다 (원래 없던 키를 되돌릴 때)."""
    spawn = ["xcrun", "simctl", "spawn", udid, "defaults"]
    commands = []
    if values["languages"]:
        commands.append([*spawn, "write", domain, "AppleLanguages", "-array", *values["languages"]])
    else:
        commands.append([*spawn, "delete", domain, "AppleLanguages"])
    if values["locale"]:
        commands.append([*spawn, "write", domain, "AppleLocale", values["locale"]])
    else:
        commands.append([*spawn, "delete", domain, "AppleLocale"])
    return commands


def _locale_ios(args, dev_id: str, key: str, lang: str, region: str | None) -> int:
    domain = args.app or "-g"
    before = _ios_domain_values(dev_id, domain)
    after = {"languages": [lang], "locale": f"{lang}_{region}" if region else lang}
    # 시스템 언어는 재부팅해야 반영된다 — 되돌릴 때도 같다
    reboot = [["xcrun", "simctl", "shutdown", dev_id], ["xcrun", "simctl", "boot", dev_id],
              ["xcrun", "simctl", "bootstatus", dev_id, "-b"]]
    _recorded(key, dev_id, before, [*_ios_write_commands(dev_id, domain, before), *(reboot if not args.app else [])],
              args)
    for command in _ios_write_commands(dev_id, domain, after):
        is_ok, detail = _run(command)
        if not is_ok:
            pop_device_setting(dev_id, key)
            return _fail("locale_failed", detail[-300:], "device list 로 기기 상태를 확인한다")
    if args.app:
        return out({"action": "locale", "platform": "ios", "device": dev_id, "app": args.app, "before": before,
                    "after": after, "summary": f"{args.app} 언어 {after['locale']} (앱을 다시 띄워야 반영)",
                    "next": "app relaunch --pkg " + args.app})
    device_boot.shutdown_ios(dev_id)
    booted = device_boot.boot_ios(dev_id, "headless", None)
    return out({"ok": booted["is_ok"], "code": "ok" if booted["is_ok"] else "boot_failed", "action": "locale",
                "platform": "ios", "device": dev_id, "before": before, "after": after, "rebooted": True,
                "summary": f"시스템 언어 {after['locale']} 로 바꾸고 재부팅" + ("" if booted["is_ok"] else " 실패"),
                "next": "device locale --restore  # 또는 device release"})


def _adb_prefix(dev_id: str) -> list[str] | None:
    adb = sdk_tool("adb")
    return [adb, "-s", dev_id, "shell"] if adb else None


def _locale_android(args, dev_id: str, key: str, lang: str, region: str | None) -> int:
    shell = _adb_prefix(dev_id)
    if shell is None:
        return _fail("tool_missing", "adb 를 찾지 못했다", "doctor 의 adb_path 확인")
    tag = f"{lang}-{region}" if region else lang
    _, sdk_text = _run([*shell, "getprop", "ro.build.version.sdk"])
    sdk = int(sdk_text) if sdk_text.isdigit() else 0
    if sdk and sdk < APP_LOCALE_MINIMUM_SDK:
        return out({"ok": False, "code": "unsupported_on_platform", "action": "locale", "platform": "android",
                    "device": dev_id, "error": f"API {sdk}: 앱별·시스템 언어 명령(cmd locale)이 API {APP_LOCALE_MINIMUM_SDK}+ 에 있다",
                    "next": "시스템 설정 앱에서 언어를 바꾸거나 새 AVD 를 쓴다"})
    if args.app:
        is_ok, text = _run([*shell, "cmd", "locale", "get-app-locales", args.app])
        listed = re.search(r"\[(.*?)\]", text)
        before = [t.strip() for t in listed.group(1).split(",") if t.strip()] if is_ok and listed else []
        base = [*shell, "cmd", "locale", "set-app-locales", args.app]
        restore = [[*base, "--locales", ",".join(before)] if before else base]
        change = [*base, "--locales", tag]
        verify = [*shell, "cmd", "locale", "get-app-locales", args.app]
    else:
        _, help_text = _run([*shell, "cmd", "locale", "help"])
        if "set-device-locale" not in help_text:
            return out({"ok": False, "code": "unsupported_on_platform", "action": "locale", "platform": "android",
                        "device": dev_id, "error": "이 이미지에는 cmd locale set-device-locale 이 없다 "
                        "(루트 필요: setprop persist.sys.locale 후 재시작)",
                        "next": "--app <패키지> 로 앱별 언어를 쓰거나 설정 앱에서 바꾼다"})
        is_ok, text = _run([*shell, "cmd", "locale", "get-device-locale"])
        before = text.split()[-1] if is_ok and text.split() else None
        restore = [[*shell, "cmd", "locale", "set-device-locale", before]] if before else []
        change = [*shell, "cmd", "locale", "set-device-locale", tag]
        verify = [*shell, "cmd", "locale", "get-device-locale"]
    if restore:
        _recorded(key, dev_id, before, restore, args)
    is_changed, detail = _run(change)
    _, verified = _run(verify)
    if not is_changed or tag not in verified:
        pop_device_setting(dev_id, key)
        return _fail("locale_failed", (detail or verified)[-300:] or "언어가 바뀌지 않았다",
                     "shell 권한(CHANGE_CONFIGURATION)이 없는 이미지일 수 있다 — 설정 앱에서 바꾼다")
    return out({"action": "locale", "platform": "android", "device": dev_id, "app": args.app, "tag": tag,
                "before": before, "is_restorable": bool(restore),
                "summary": f"{args.app or '시스템'} 언어 {tag} (원래: {before or '기본'})",
                "next": ("app relaunch --pkg " + args.app) if args.app else "device locale --restore  # 또는 device release"})


def run_locale(args) -> int:
    platform, dev_id, err = resolve_device(args)
    if err is not None:
        return err
    key = f"locale:app:{args.app}" if args.app else "locale:system"
    if args.restore:
        return _restore(dev_id, platform, key, "locale")
    if not args.lang:
        return _fail("args_required", "--lang 이 필요합니다", "device locale --device $DEV --lang en --region US")
    # 시스템 언어 변경은 재부팅(iOS)·전역 변경이라 다른 세션 소유 기기에서는 --yes 가 필요하다
    if not args.app and not args.yes and (refusal := refuse_other_session_owner(dev_id, "locale")) is not None:
        return refusal
    handler = _locale_ios if platform == "ios" else _locale_android
    return handler(args, dev_id, key, args.lang, args.region)
