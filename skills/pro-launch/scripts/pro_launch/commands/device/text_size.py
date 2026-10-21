"""`device text-size` — 기기 전역 글자 크기를 바꾸고 원래 값을 기록한다 (#947).

큰 글씨에서 레이아웃이 버티는지 보는 QA 용. 바꾸기 전 값을 기록하므로 `--restore` 나 `device release` 가 되돌린다.
iOS 는 `simctl ui content_size`(콘텐츠 크기 범주), Android 는 `font_scale` 설정.
"""
from __future__ import annotations

from common.proc import sdk_tool

from pro_launch.commands.device.claims import refuse_other_session_owner, resolve_device
from pro_launch.commands.device.setting_support import fail, record_change, restore_recorded, run_command
from pro_launch.runtime.device_claims import pop_device_setting
from pro_launch.runtime.output import out

# 이름 하나로 두 플랫폼을 다룬다: (iOS 콘텐츠 크기 범주, Android font_scale)
TEXT_SIZE_PRESETS = {
    "default": ("large", "1.0"),
    "large": ("accessibility-extra-large", "1.3"),
    "largest": ("accessibility-extra-extra-extra-large", "2.0"),
}
ANDROID_FONT_SCALE_RANGE = (0.5, 3.0)
SETTING_KEY = "text_size"


def _target_values(size: str) -> tuple[str, str] | None:
    """프리셋 이름 > (iOS 범주, Android 배율). 숫자(1.3)면 Android 배율로, 프리셋이 아닌 글자는 iOS 범주로 그대로"""
    if size in TEXT_SIZE_PRESETS:
        return TEXT_SIZE_PRESETS[size]
    try:
        scale = float(size)
    except ValueError:
        return size, "1.0"
    low, high = ANDROID_FONT_SCALE_RANGE
    return ("large", str(scale)) if low <= scale <= high else None


def run_text_size(args) -> int:
    platform, dev_id, err = resolve_device(args)
    if err is not None:
        return err
    if args.restore:
        return restore_recorded(dev_id, platform, SETTING_KEY, "text-size")
    if not args.mode:
        return fail("args_required", "Give a size: default · large · largest (or an Android scale such as 1.3, or an iOS category name)",
                    "device text-size large --device $DEV")
    target = _target_values(args.mode)
    if target is None:
        return fail("bad_args", f"Scale must be {ANDROID_FONT_SCALE_RANGE[0]}–{ANDROID_FONT_SCALE_RANGE[1]}: {args.mode}")
    if not args.yes and (refusal := refuse_other_session_owner(dev_id, "text-size")) is not None:
        return refusal
    ios_category, android_scale = target
    if platform == "ios":
        read = ["xcrun", "simctl", "ui", dev_id, "content_size"]
        is_read, before = run_command(read)
        change = [*read, ios_category]
        restore = [[*read, before.strip()]] if is_read and before.strip() else []
        applied = ios_category
    else:
        adb = sdk_tool("adb")
        if not adb:
            return fail("tool_missing", "adb not found", "Check adb_path with doctor")
        scale_setting = [adb, "-s", dev_id, "shell", "settings"]
        is_read, before = run_command([*scale_setting, "get", "system", "font_scale"])
        before = before.strip() if is_read and before.strip() not in ("", "null") else "1.0"
        change = [*scale_setting, "put", "system", "font_scale", android_scale]
        restore = [[*scale_setting, "put", "system", "font_scale", before]]
        applied = android_scale
    if restore:
        record_change(SETTING_KEY, dev_id, before, restore, args)
    is_changed, detail = run_command(change)
    if not is_changed:
        pop_device_setting(dev_id, SETTING_KEY)
        return fail("text_size_failed", detail[-300:] or "Could not change the text size", "Check the device state with device list")
    return out({"action": "text-size", "platform": platform, "device": dev_id, "size": applied,
                "before": before, "is_restorable": bool(restore),
                "summary": f"Text size {applied} (was: {before.strip()})",
                "next": "device text-size --restore  # or device release. Restore right after you finish"})
