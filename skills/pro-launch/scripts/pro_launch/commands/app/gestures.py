"""app 의 탭·스와이프가 함께 쓰는 것 — 백엔드 고르기 · 조작 전후 화면 비교 · 결과 응답."""
from __future__ import annotations

import os
import time

import app_input
import knowledge

from pro_launch.runtime.context import project_root
from pro_launch.runtime.devices import no_device_response, pick_device
from pro_launch.runtime.output import out
from pro_launch.runtime.shots import finish_shot, shot_target


def backend_for(args):
    """(백엔드, 기기 id, 오류 응답). 기기를 못 고르거나 도구가 없으면 오류 응답을 채운다."""
    platform, dev_id, dev = pick_device(args.device)
    if not platform:
        return None, None, no_device_response(dev, args.device)
    be = app_input.get_backend(platform, getattr(args, "pkg", None) or os.environ.get("PKG"))
    if be is None:
        return None, None, out({"ok": False, "code": "platform_unsupported",
                                "error": f"{platform} 은 조작 백엔드가 없다",
                                "next": "references/extending.md 를 보고 백엔드를 추가한다"})
    if not be.available():
        return None, None, out({"ok": False, "code": f"{be.name}_tool_missing",
                                "error": f"{be.name} 조작 도구가 없다", "next": be.install_hint})
    return be, dev_id, None


def before_shot(args, be, dev_id) -> bytes | None:
    """--shot 일 때만 동작 전 화면을 기억한다 — 나중에 '바뀐 뒤 멈춘 화면'을 고르는 기준."""
    return be.grab(dev_id) if getattr(args, "shot", None) else None


def after_shot(args, be, dev_id, before: bytes | None) -> dict:
    """--shot 이면 동작 결과 화면을 찍는다 — 확인용 shot 호출 한 번을 아낀다.

    고정 대기는 실패한다(실측): Android 는 캡처가 느려 전환이 시작되기도 전에 같은 장면을 두 번
    찍고 '멈췄다'고 판단했다. 그래서 **동작 전 화면과 달라진 뒤, 연속 두 장이 같아질 때**를 고른다.
    끝내 안 바뀌면 screen_changed=false — '눌렀는데 반응 없음'을 agent 가 바로 안다.
    """
    if not getattr(args, "shot", None):
        return {}
    prev, data, changed, deadline = None, None, False, time.time() + 5.0
    while time.time() < deadline:
        data = be.grab(dev_id)
        if data is None:
            return {"shot": None}
        changed = changed or (before is not None and data != before)
        if changed and data == prev:
            break
        prev = data
        time.sleep(0.3)
    raw, explicit = shot_target(project_root(args), args.shot)
    raw.write_bytes(data)
    return {"shot": str(finish_shot(raw, explicit, args)),
            "screen_changed": changed if before is not None else None}


def gesture_result(args, be, dev_id, before, ok: bool, detail: str, fail_code: str,
                    summary: str, **extra) -> int:
    res = {"ok": ok, "code": "ok" if ok else fail_code, "device": dev_id, "via": be.name,
           **extra, "error": None if ok else (detail or "")[-400:] or None,
           "summary": summary if ok else f"실패 — {fail_code}",
           "next": "app shot  # 결과 화면 확인"}
    if ok:
        auto_record_backend(be)
        res.update(after_shot(args, be, dev_id, before))
        if res.get("shot"):
            res["next"] = ("shot 이미지를 읽어 결과를 확인한다" if res.get("screen_changed") is not False
                           else "화면이 그대로다 — 다른 요소를 고르거나 app tree 로 다시 본다")
    return out(res)


_BACKEND_HOW = {"android": "앱 누르기·밀기는 launch_cli app tap/swipe (uiautomator + adb input, 화면 요소 기준)로 된다",
                "ios": "앱 누르기·밀기는 launch_cli app tap/swipe (Maestro, 화면 요소 기준)로 된다"}


def auto_record_backend(be) -> None:
    """실제로 성공한 조작 방식을 이 컴퓨터 범위에 남긴다 — 검증된 것만, 하루 한 번."""
    how = _BACKEND_HOW.get(be.name)
    if how:
        try:
            knowledge.auto_record(be.name, f"{be.name}.input", how)
        except Exception:   # noqa: BLE001 — 기록 실패가 조작 결과를 바꾸면 안 된다
            pass


def not_found_response(be, dev_id, field: str, value: str, nodes: list[dict] | None) -> int:
    """못 찾았을 때 추측을 반복하지 않도록 화면 언어와 화면에 실제로 있는 값을 같이 준다."""
    if nodes is None:
        nodes = be.nodes(dev_id) or []
    cands = list(dict.fromkeys(n[field] for n in nodes if n[field]))[:25]
    return out({"ok": False, "code": "not_found", "device": dev_id,
                "error": f"{field}={value!r} 인 요소가 없다",
                "locale": be.locale(dev_id), "candidates": cands,
                "next": "candidates 의 값으로 다시 app tap (문구는 화면 언어 그대로)"})
