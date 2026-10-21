"""`app type` — 포커스된 입력창에 글자를 넣는다."""
from __future__ import annotations

import os
import re
import subprocess

from common.proc import sdk_tool

import app_input
import credentials

from pro_launch.commands.app import android_ime
from pro_launch.commands.app.gestures import backend_on, elapsed_seconds, session_fields, with_session_advice
from pro_launch.registry import Action
from pro_launch.runtime.creds import cred_field, with_login_policy
from pro_launch.runtime.devices import no_device_response, pick_device
from pro_launch.runtime.output import out

# 대조 결과에 보이는 글자를 싣지 않을 환경변수 이름 (비밀번호·토큰·코드류)
SECRET_ENV_NAME_PATTERN = re.compile(r"PASS|PW|PWD|TOKEN|SECRET|KEY|OTP|PIN|CODE|AUTH|CRED", re.IGNORECASE)


def _app_type(args) -> int:
    """기기 화면의 포커스된 입력창에 글자를 넣는다. 로그인 정보는 저장된 자격증명에서 꺼내 쓴다.

    값은 명령줄에 싣지 않는다 (호스트 `ps` 에 남지 않게): Android 표준입력, iOS Maestro 환경변수.
    iOS 는 simctl 에 텍스트 명령이 없어 Maestro inputText 로 넣는다 (#895).
    """
    if getattr(args, "cred", None):
        value, err = cred_field(args.cred, getattr(args, "cred_field", None))
        if err:
            return out(err)
    elif getattr(args, "text_env", None):
        if args.text_env not in os.environ:
            return out({"ok": False, "code": "env_not_set", "error": f"Environment variable {args.text_env} is empty"})
        value = os.environ[args.text_env]
    else:
        # 비밀 아닌 값도 --text-env 로 — 명령줄 값은 세션 기록·호스트 ps 에 평문으로 남는다
        return out({"ok": False, "code": "text_required",
                    "error": "--cred or --text-env is required (do not pass the value as --text — it stays in the records in plain text)",
                    "next": "SEARCH_TEXT='coffee' app type --text-env SEARCH_TEXT  # a plain value (Android accepts ASCII only)",
                    "hint": "For login details use app type --cred <name> (cred list shows saved names)"})
    platform, dev_id, dev = pick_device(args.device)
    if not platform:
        return no_device_response(dev, args.device)
    if platform == "ios":
        return _type_with_backend(args, platform, dev_id, value)
    if platform != "android":
        return out({"ok": False, "code": "ios_text_unsupported",
                    "error": f"{platform} has no way to type text",
                    "next": "Ask the user to type it themselves"})
    if not value.isascii():
        return out({"ok": False, "code": "non_ascii_unsupported",
                    "error": "adb input text accepts ASCII only (no Korean)",
                    "next": "Use a letters/digits value instead, or install an IME such as ADBKeyboard"})
    if not sdk_tool("adb"):
        return out({"ok": False, "code": "adb_missing", "error": "adb not found"})
    return _type_on_android(args, dev_id, value)


def _type_on_android(args, dev_id: str, value: str) -> int:
    """Android: 입력기 확인·전환 > 입력(표준입력) > 필드 대조 > Enter > 원복 (#926)."""
    be = app_input.get_backend("android")
    mode = getattr(args, "ime", None) or "auto"
    should_submit = bool(getattr(args, "submit", False))
    is_secret = _is_secret_source(args)
    verification: dict = {}
    try:
        with android_ime.ascii_input_method(android_ime.android_shell(be, dev_id), mode, dev_id) as ime_report:
            if mode == "ascii" and ime_report["reason"] in ("no_ascii_input_method_installed",
                                                             "default_input_method_unknown"):
                return out({"ok": False, "code": "ascii_input_method_missing", "device": dev_id, "ime": ime_report,
                            "error": "No IME that types characters as-is (Maestro IME · ADBKeyboard), or the default IME to restore is unknown",
                            "next": "Running Maestro once on this device (app flow · app tap) installs the Maestro IME. "
                                    "Or install ADBKeyboard"})
            ok, detail, verification = android_ime.type_and_verify(be, dev_id, value, is_secret, should_submit)
    except subprocess.TimeoutExpired:
        return out({"ok": False, "code": "app_type_timeout", "error": "Device did not respond (30s)"})
    entry = {"password": value, "token": value}
    is_mismatch = detail == "typed_text_mismatch"
    result = {"ok": ok, "code": "ok" if ok else ("typed_text_mismatch" if is_mismatch else "app_type_failed"),
              "device": dev_id,
              "chars": len(value), "submitted": should_submit and ok, "ime": ime_report, **verification,
              "elapsed_seconds": elapsed_seconds(args),
              "error": None if ok else ("The text shown in the field differs from the typed value (a composing keyboard may have composed the ASCII)"
                                        if is_mismatch else credentials.mask(detail or "", entry)[:300] or None),
              "summary": f"Typed {len(value)} chars" + (" + Enter" if should_submit and ok else ""),
              "next": _next_after_android_type(ok, is_mismatch, ime_report)}
    # 로그인 입력이면 중간 화면 정책을 싣는다 (#905)
    return out(with_login_policy(result, getattr(args, "cred", None)))


def _is_secret_source(args) -> bool:
    """대조 결과에 보이는 글자를 실어도 되나 — 저장된 자격증명이거나 이름이 비밀 같은 환경변수면 비밀."""
    if getattr(args, "cred", None):
        return True
    return bool(SECRET_ENV_NAME_PATTERN.search(getattr(args, "text_env", None) or ""))


def _next_after_android_type(ok: bool, is_mismatch: bool, ime_report: dict) -> str:
    if ok:
        return "app shot  # check on screen that it was typed (password fields show masked)"
    if is_mismatch:
        if ime_report.get("switched_to"):
            return "Still different after switching the IME — check with app tree that this is the right field"
        return ("Clear the field, then type again with app type --ime ascii "
                "(switches to Maestro IME · ADBKeyboard only while typing, then restores)")
    return "Tap the field first with app tap to focus it, then try again"


def _type_with_backend(args, platform: str, dev_id: str, value: str) -> int:
    """iOS — 조작 백엔드(Maestro)의 input_text. 도구가 없으면 ios_tool_missing (tap·swipe 와 같은 code)."""
    be, err = backend_on(platform, args)
    if err is not None:
        return err
    should_submit = bool(getattr(args, "submit", False))
    ok, detail = be.input_text(dev_id, value, submit=should_submit)
    entry = {"password": value, "token": value}
    # 비밀 값은 상주 세션에 싣지 않는다 — 세션이 있으면 session_fallback=secret_input_per_call 로 보인다
    result = {"ok": ok, "code": "ok" if ok else "app_type_failed", "device": dev_id, "via": be.name,
              **session_fields(be), "chars": len(value), "submitted": should_submit and ok,
              "elapsed_seconds": elapsed_seconds(args),
              "error": None if ok else credentials.mask(detail, entry)[-400:] or None,
              "summary": f"Typed {len(value)} chars" + (" + Enter" if should_submit and ok else ""),
              "next": "app shot  # check on screen that it was typed (password fields show masked)" if ok
                      else "Tap the field first with app tap to focus it, then try again"}
    with_session_advice(result, be, dev_id, args)
    # 로그인 입력이면 중간 화면 정책을 싣는다 (#905)
    return out(with_login_policy(result, getattr(args, "cred", None)))


def configure(p) -> None:
    p.add_argument("--cred", default=None, help="type: saved login name (cred list)")
    p.add_argument("--cred-field", dest="cred_field", default=None, help="type: field to type (default password, e.g. account)")
    p.add_argument("--text-env", dest="text_env", default=None, help="type: environment variable to read the value from (one-time)")
    p.add_argument("--submit", action="store_true", help="type: press Enter after typing")
    p.add_argument("--ime", choices=android_ime.IME_MODES, default="auto",
                   help="type·run (Android): auto = with a composing keyboard (Korean etc.) switch to an as-is IME only while typing, then restore · "
                        "keep = leave as is · ascii = always switch")


ACTION = Action(name="type", device_use="mutate", run=_app_type, configure=configure)
