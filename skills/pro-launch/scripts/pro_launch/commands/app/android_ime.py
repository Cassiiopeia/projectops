"""IME handling and result check for Android text input: read default IME > switch briefly if composing > input > re-read field > restore (#926).

`adb input text` sends key events. Korean, Japanese and Chinese keyboards (e.g. Gboard Korean) compose even ASCII keys,
so 'chan' comes out as 'ㅊㅗㅁ…' (measured). So during input we switch to an IME that inserts text as is, then re-read the field to check.
It is a device-wide setting, so the previous value is remembered and restored in finally.
"""
from __future__ import annotations

import re
import subprocess
import time
import xml.etree.ElementTree as ET
from contextlib import contextmanager

from common.proc import sdk_tool

from pro_launch.runtime.device_claims import pop_device_setting, record_device_setting

# --ime values: auto switches if composing, keep leaves it, ascii always switches
IME_MODES = ("auto", "keep", "ascii")
# IMEs that insert text without composing (the first installed one is used). The Maestro IME is installed on devices that ran Maestro once
MAESTRO_INPUT_METHOD = "dev.mobile.maestro/.input.MaestroInputMethodService"
ADB_KEYBOARD_INPUT_METHOD = "com.android.adbkeyboard/.AdbIME"
ASCII_INPUT_METHODS = (MAESTRO_INPUT_METHOD, ADB_KEYBOARD_INPUT_METHOD)
# IMEs that always compose (Korean, Japanese, Chinese only) — id fragment
ALWAYS_COMPOSING_INPUT_METHOD_MARKERS = (
    "inputmethod.korean", "inputmethod.japanese", "inputmethod.pinyin", "navercorp.android.smartboard",
    "nhn.android.inputmethod", "jp.co.omronsoft", "com.baidu.input", "com.sohu.inputmethod")
# IMEs that compose depending on language (Gboard, Samsung Keyboard) — decided by subtype language or device language
LANGUAGE_DEPENDENT_INPUT_METHOD_MARKERS = (
    "com.google.android.inputmethod.latin", "com.samsung.android.honeyboard", "com.sec.android.inputmethod")
COMPOSING_LANGUAGES = ("ko", "ja", "zh")
# One state read: default IME @@ subtype line @@ device language @@ installed IMEs @@ enabled IMEs
PROBE_SECTION_SEPARATOR = "@@"
PROBE_COMMAND = ("settings get secure default_input_method; echo @@; "
                 "dumpsys input_method | grep -iE 'subtype|locale'; echo @@; "
                 "getprop persist.sys.locale; getprop ro.product.locale; echo @@; "
                 "ime list -s -a; echo @@; ime list -s")
# Language in the subtype line (format varies by version: mSubtypeLocale=ko_KR, languageTag=ko-KR, etc.)
SUBTYPE_LANGUAGE_PATTERN = re.compile(r"(?:locale|languagetag)\s*[=:]\s*([a-z]{2})(?:[_-]|\b)", re.IGNORECASE)
# Time for the input field to reattach to the new IME after switching (seconds)
SWITCH_SETTLE_SECONDS = 0.6
# Field re-read: maximum wait for uiautomator dump (seconds)
FIELD_READ_TIMEOUT_SECONDS = 20


def parse_probe(probe_output: str) -> dict:
    """PROBE_COMMAND output > {default, subtype_language, device_language, installed, enabled}."""
    sections = [s.strip() for s in (probe_output or "").split(PROBE_SECTION_SEPARATOR)]
    sections += [""] * (5 - len(sections))
    default = sections[0].splitlines()[0].strip() if sections[0] else ""
    subtype_match = SUBTYPE_LANGUAGE_PATTERN.search(sections[1])
    device_locale = next((line.strip() for line in sections[2].splitlines() if line.strip()), "")
    return {"default": "" if default == "null" else default,
            "subtype_language": subtype_match.group(1).lower() if subtype_match else None,
            "device_language": device_locale[:2].lower() or None,
            "installed": [line.strip() for line in sections[3].splitlines() if line.strip()],
            "enabled": [line.strip() for line in sections[4].splitlines() if line.strip()]}


def is_composing(state: dict) -> bool:
    """Whether the default IME will compose ASCII keys. Language-dependent IMEs check subtype language, then device language."""
    default = state["default"]
    if not default or default in ASCII_INPUT_METHODS:
        return False
    if any(marker in default for marker in ALWAYS_COMPOSING_INPUT_METHOD_MARKERS):
        return True
    if any(marker in default for marker in LANGUAGE_DEPENDENT_INPUT_METHOD_MARKERS):
        language = state["subtype_language"] or state["device_language"]
        return language in COMPOSING_LANGUAGES
    return False


def choose_switch(state: dict, mode: str) -> tuple[str | None, str]:
    """(IME to switch to or None, reason). Reasons: keep, already_ascii, not_composing, no_ascii_input_method_installed, composing, requested."""
    if mode == "keep":
        return None, "keep"
    if state["default"] in ASCII_INPUT_METHODS:
        return None, "already_ascii"
    if mode == "auto" and not is_composing(state):
        return None, "not_composing"
    target = next((ime for ime in ASCII_INPUT_METHODS if ime in state["installed"]), None)
    if not target:
        return None, "no_ascii_input_method_installed"
    return target, "composing" if mode == "auto" else "requested"


def _quiet(shell, command: str) -> str:
    """One shell call. Timeout or run failure gives empty output (so IME handling never blocks the input itself)."""
    try:
        return shell(command) or ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _record_ime_change(dev_id: str | None, before_ime: str) -> None:
    """Record the pre-switch IME and the restore command in the device claim. A record failure does not block input."""
    if not dev_id:
        return
    try:
        record_device_setting(dev_id, "ime", before_ime,
                              [[sdk_tool("adb"), "-s", dev_id, "shell", "ime", "set", before_ime]])
    except (OSError, ValueError, KeyError):
        return  # The record is a backup safety net — even without it, the try/finally restore runs first


def _forget_ime_change(dev_id: str | None) -> None:
    """Restored normally, so remove the IME entry from the device claim."""
    if not dev_id:
        return
    try:
        pop_device_setting(dev_id, "ime")
    except (OSError, ValueError, KeyError):
        return  # Even if not removed, the next device release just resets it to the already restored value


@contextmanager
def ascii_input_method(shell, mode: str, dev_id: str | None = None):
    """Switch to an ASCII IME only during input, then restore > report dict (restored is filled after the with block ends).

    shell(command string) > stdout. report: mode, default, reason, switched_to, restored.
    With dev_id, the switched IME is recorded in the device claim — device release restores it even if the process dies midway (#925).
    """
    report: dict = {"mode": mode}
    if mode == "keep":
        report["reason"] = "keep"
        yield report
        return
    state = parse_probe(_quiet(shell, PROBE_COMMAND))
    target, reason = choose_switch(state, mode)
    if target and not state["default"]:
        # Do not switch if the value to restore is unknown (never leave someone else's device settings changed)
        target, reason = None, "default_input_method_unknown"
    report.update(default=state["default"] or None, reason=reason)
    if not target:
        yield report
        return
    was_enabled = target in state["enabled"]
    if not was_enabled:
        _quiet(shell, f"ime enable {target}")
    _quiet(shell, f"ime set {target}")
    time.sleep(SWITCH_SETTLE_SECONDS)
    report["switched_to"] = target
    _record_ime_change(dev_id, state["default"])
    try:
        yield report
    finally:
        # Restore (success or failure): restore default IME > disable the IME we enabled > confirm it is back
        _quiet(shell, f"ime set {state['default']}")
        if not was_enabled:
            _quiet(shell, f"ime disable {target}")
        restored = _quiet(shell, "settings get secure default_input_method").strip()
        report["restored"] = restored == state["default"] if restored else None
        if report["restored"]:
            _forget_ime_change(dev_id)


def focused_field(xml_text: str) -> dict | None:
    """uiautomator dump > focused input field {text, is_password}. None if unreadable, {} if nothing is focused."""
    body = (xml_text or "")[(xml_text or "").find("<"):(xml_text or "").rfind(">") + 1]
    if "<hierarchy" not in body:
        return None
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return None
    focused = [el for el in root.iter("node") if el.get("focused") == "true"]
    editable = [el for el in focused if "EditText" in (el.get("class") or "")]
    chosen = (editable or focused or [None])[0]
    if chosen is None:
        return {}
    return {"text": chosen.get("text", ""), "is_password": chosen.get("password") == "true"}


def verify_typed_text(xml_text: str, value: str, is_secret: bool) -> dict:
    """Typed value <-> text of the focused field > {verification, ...}. For secret values only length and match are included.

    verification: matched · mismatch · skipped_password_field · skipped_no_focused_field · skipped_read_failed
    """
    field = focused_field(xml_text)
    if field is None:
        return {"verification": "skipped_read_failed"}
    if not field:
        return {"verification": "skipped_no_focused_field"}
    if field["is_password"]:
        # Android masks password field text — cannot be checked
        return {"verification": "skipped_password_field"}
    visible = field["text"]
    is_match = value in visible
    report = {"verification": "matched" if is_match else "mismatch", "is_match": is_match,
              "expected_length": len(value), "visible_length": len(visible),
              "visible_has_non_ascii": not visible.isascii()}
    if not is_secret:
        report["visible_value"] = visible
    return report


def read_focused_field_xml(be, dev_id: str) -> str:
    """Screen tree XML for reading the focused field (via stdout so no file is left on the device)."""
    try:
        return be._adb(dev_id, "exec-out", "uiautomator", "dump", "/dev/tty",
                       timeout=FIELD_READ_TIMEOUT_SECONDS).stdout or ""
    except (OSError, subprocess.SubprocessError):
        return ""


def type_and_verify(be, dev_id: str, value: str, is_secret: bool, should_submit: bool) -> tuple[bool, str, dict]:
    """Input > field check > Enter (only if it matches or cannot be checked). (success, reason, check result)."""
    is_success, detail = be.input_text(dev_id, value, submit=False)
    if not is_success:
        return False, detail, {}
    verification = verify_typed_text(read_focused_field_xml(be, dev_id), value, is_secret)
    if verification["verification"] == "mismatch":
        # Do not submit a wrong value (avoid login attempts with the wrong account)
        return False, "typed_text_mismatch", verification
    if should_submit:
        submitted = be._adb(dev_id, "shell", "input", "keyevent", "66")   # 66 = Enter
        if submitted.returncode != 0:
            return False, (submitted.stderr or "").strip(), verification
    return True, "", verification


def android_shell(be, dev_id: str):
    """Shell to pass to ascii_input_method (command string > stdout)."""
    return lambda command: be._adb(dev_id, "shell", command).stdout
