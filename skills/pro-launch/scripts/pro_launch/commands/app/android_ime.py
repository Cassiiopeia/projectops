"""Android 글자 입력의 입력기(IME)와 결과 대조: 기본 IME 읽기 > 조합형이면 잠시 바꾸기 > 입력 > 필드 다시 읽기 > 원복 (#926).

`adb input text` 는 키 이벤트다. 한국어·일본어·중국어 자판(Gboard 한국어 등)은 ASCII 키도 조합해
'chan' 이 'ㅊㅗㅁ…' 으로 들어간다(실측). 그래서 입력 동안만 글자를 그대로 넣는 IME 로 바꾸고, 넣은 뒤 필드를 다시 읽어 대조한다.
기기 전역 설정이므로 바꾸기 전 값을 기억해 finally 에서 되돌린다.
"""
from __future__ import annotations

import re
import subprocess
import time
import xml.etree.ElementTree as ET
from contextlib import contextmanager

# --ime 값: auto 조합형이면 바꿈 · keep 그대로 · ascii 항상 바꿈
IME_MODES = ("auto", "keep", "ascii")
# 글자를 조합 없이 그대로 넣는 IME (설치된 것 중 앞의 것을 쓴다). Maestro IME 는 Maestro 를 한 번 돌린 기기에 깔린다
MAESTRO_INPUT_METHOD = "dev.mobile.maestro/.input.MaestroInputMethodService"
ADB_KEYBOARD_INPUT_METHOD = "com.android.adbkeyboard/.AdbIME"
ASCII_INPUT_METHODS = (MAESTRO_INPUT_METHOD, ADB_KEYBOARD_INPUT_METHOD)
# 언제나 조합하는 IME (한국어·일본어·중국어 전용) — id 일부
ALWAYS_COMPOSING_INPUT_METHOD_MARKERS = (
    "inputmethod.korean", "inputmethod.japanese", "inputmethod.pinyin", "navercorp.android.smartboard",
    "nhn.android.inputmethod", "jp.co.omronsoft", "com.baidu.input", "com.sohu.inputmethod")
# 언어에 따라 조합하는 IME (Gboard · 삼성 키보드) — 하위 유형 언어 또는 기기 언어로 가른다
LANGUAGE_DEPENDENT_INPUT_METHOD_MARKERS = (
    "com.google.android.inputmethod.latin", "com.samsung.android.honeyboard", "com.sec.android.inputmethod")
COMPOSING_LANGUAGES = ("ko", "ja", "zh")
# 상태 읽기 한 번: 기본 IME @@ 하위 유형 줄 @@ 기기 언어 @@ 설치된 IME @@ 켜진 IME
PROBE_SECTION_SEPARATOR = "@@"
PROBE_COMMAND = ("settings get secure default_input_method; echo @@; "
                 "dumpsys input_method | grep -iE 'subtype|locale'; echo @@; "
                 "getprop persist.sys.locale; getprop ro.product.locale; echo @@; "
                 "ime list -s -a; echo @@; ime list -s")
# 하위 유형 줄의 언어 (mSubtypeLocale=ko_KR · languageTag=ko-KR 등 형식이 버전마다 다르다)
SUBTYPE_LANGUAGE_PATTERN = re.compile(r"(?:locale|languagetag)\s*[=:]\s*([a-z]{2})(?:[_-]|\b)", re.IGNORECASE)
# IME 를 바꾼 뒤 입력창이 새 IME 에 다시 붙을 때까지 (초)
SWITCH_SETTLE_SECONDS = 0.6
# 필드 다시 읽기: uiautomator dump 최대 대기 (초)
FIELD_READ_TIMEOUT_SECONDS = 20


def parse_probe(probe_output: str) -> dict:
    """PROBE_COMMAND 출력 > {default, subtype_language, device_language, installed, enabled}."""
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
    """기본 IME 가 ASCII 키를 조합할 것인가. 언어 의존 IME 는 하위 유형 언어 > 기기 언어 순으로 본다."""
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
    """(바꿀 IME 또는 None, 이유). 이유: keep · already_ascii · not_composing · no_ascii_input_method_installed · composing · requested."""
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
    """셸 한 번. 시간 초과·실행 실패는 빈 출력 (IME 처리가 입력 자체를 막지 않게)."""
    try:
        return shell(command) or ""
    except (OSError, subprocess.SubprocessError):
        return ""


@contextmanager
def ascii_input_method(shell, mode: str):
    """입력 동안만 ASCII IME 로 바꾸고 원복 > report dict (with 블록이 끝난 뒤 restored 가 채워진다).

    shell(명령 문자열) > 표준출력. report: mode · default · reason · switched_to · restored.
    """
    report: dict = {"mode": mode}
    if mode == "keep":
        report["reason"] = "keep"
        yield report
        return
    state = parse_probe(_quiet(shell, PROBE_COMMAND))
    target, reason = choose_switch(state, mode)
    if target and not state["default"]:
        # 되돌릴 값을 모르면 바꾸지 않는다 (남의 기기 설정을 바꿔 둔 채로 두지 않게)
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
    try:
        yield report
    finally:
        # 원복 (성공·실패 공통): 기본 IME 되돌리기 > 우리가 켠 IME 끄기 > 되돌아갔는지 확인
        _quiet(shell, f"ime set {state['default']}")
        if not was_enabled:
            _quiet(shell, f"ime disable {target}")
        restored = _quiet(shell, "settings get secure default_input_method").strip()
        report["restored"] = restored == state["default"] if restored else None


def focused_field(xml_text: str) -> dict | None:
    """uiautomator dump > 포커스된 입력창 {text, is_password}. 못 읽으면 None, 포커스 없으면 {}."""
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
    """넣은 값 <-> 포커스된 필드의 글자 > {verification, ...}. 비밀 값이면 길이와 일치 여부만 싣는다.

    verification: matched · mismatch · skipped_password_field · skipped_no_focused_field · skipped_read_failed
    """
    field = focused_field(xml_text)
    if field is None:
        return {"verification": "skipped_read_failed"}
    if not field:
        return {"verification": "skipped_no_focused_field"}
    if field["is_password"]:
        # Android 는 비밀번호 칸 글자를 가린다 — 대조할 수 없다
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
    """포커스된 필드를 읽을 화면 구조 XML (파일을 기기에 남기지 않게 표준출력으로)."""
    try:
        return be._adb(dev_id, "exec-out", "uiautomator", "dump", "/dev/tty",
                       timeout=FIELD_READ_TIMEOUT_SECONDS).stdout or ""
    except (OSError, subprocess.SubprocessError):
        return ""


def type_and_verify(be, dev_id: str, value: str, is_secret: bool, should_submit: bool) -> tuple[bool, str, dict]:
    """입력 > 필드 대조 > (일치하거나 대조 불가일 때만) Enter. (성공 여부, 사유, 대조 결과)."""
    is_success, detail = be.input_text(dev_id, value, submit=False)
    if not is_success:
        return False, detail, {}
    verification = verify_typed_text(read_focused_field_xml(be, dev_id), value, is_secret)
    if verification["verification"] == "mismatch":
        # 틀린 값으로 제출하지 않는다 (잘못된 계정으로 로그인 시도 방지)
        return False, "typed_text_mismatch", verification
    if should_submit:
        submitted = be._adb(dev_id, "shell", "input", "keyevent", "66")   # 66 = Enter
        if submitted.returncode != 0:
            return False, (submitted.stderr or "").strip(), verification
    return True, "", verification


def android_shell(be, dev_id: str):
    """ascii_input_method 에 넘길 셸 (명령 문자열 > 표준출력)."""
    return lambda command: be._adb(dev_id, "shell", command).stdout
