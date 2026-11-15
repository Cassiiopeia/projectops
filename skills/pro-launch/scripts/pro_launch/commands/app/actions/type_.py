"""`app type` — type text into the focused input field."""
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

# Environment variable names whose visible characters stay out of the check result (passwords, tokens, codes)
SECRET_ENV_NAME_PATTERN = re.compile(r"PASS|PW|PWD|TOKEN|SECRET|KEY|OTP|PIN|CODE|AUTH|CRED", re.IGNORECASE)


def _app_type(args) -> int:
    """Type text into the focused input field on the device screen. Login info comes from stored credentials.

    Values never go on the command line (so they do not show in host `ps`): Android via stdin, iOS via Maestro environment variables.
    iOS has no text command in simctl, so text goes in via Maestro inputText (#895).
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
        # Use --text-env for non-secret values too — command-line values stay in plain text in session logs and host ps
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
    """Android: check and switch IME > input (stdin) > field check > Enter > restore (#926)."""
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
        return out({"ok": False, "code": "app_type_timeout", "error": "Device did not respond (30s)",
                    "next": "device doctor to check the device is alive (it may be frozen or asleep), then type again"})
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
    # For login input, attach the interstitial screen policy (#905)
    return out(with_login_policy(result, getattr(args, "cred", None)))


def _is_secret_source(args) -> bool:
    """Whether visible characters may go in the check result — secret if it is a stored credential or an env var with a secret-like name."""
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
    """iOS — input_text of the control backend (Maestro). If the tool is missing, ios_tool_missing (same code as tap and swipe)."""
    be, err = backend_on(platform, args)
    if err is not None:
        return err
    should_submit = bool(getattr(args, "submit", False))
    ok, detail = be.input_text(dev_id, value, submit=should_submit)
    entry = {"password": value, "token": value}
    # Secret values are not sent to the persistent session — with a session, this shows as session_fallback=secret_input_per_call
    result = {"ok": ok, "code": "ok" if ok else "app_type_failed", "device": dev_id, "via": be.name,
              **session_fields(be), "chars": len(value), "submitted": should_submit and ok,
              "elapsed_seconds": elapsed_seconds(args),
              "error": None if ok else credentials.mask(detail, entry)[-400:] or None,
              "summary": f"Typed {len(value)} chars" + (" + Enter" if should_submit and ok else ""),
              "next": "app shot  # check on screen that it was typed (password fields show masked)" if ok
                      else "Tap the field first with app tap to focus it, then try again"}
    with_session_advice(result, be, dev_id, args)
    # For login input, attach the interstitial screen policy (#905)
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
