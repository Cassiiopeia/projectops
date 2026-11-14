"""Windows mouse·keyboard input — uses only SendInput from standard-library ctypes (#985).

Coordinates are physical pixels. Called after making the process Per-Monitor DPI Aware v2, so they share the basis of UIA coordinates.
"""
from __future__ import annotations

import ctypes
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)

INPUT_MOUSE, INPUT_KEYBOARD = 0, 1
MOUSEEVENTF_MOVE, MOUSEEVENTF_ABSOLUTE, MOUSEEVENTF_VIRTUALDESK = 0x0001, 0x8000, 0x4000
MOUSE_BUTTON_FLAGS = {"left": (0x0002, 0x0004), "right": (0x0008, 0x0010), "middle": (0x0020, 0x0040)}
KEYEVENTF_KEYUP, KEYEVENTF_UNICODE = 0x0002, 0x0004
SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN, SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 76, 77, 78, 79
# Pause between press and release · between actions (s) — too fast and some apps (installer wizards) miss clicks
PRESS_GAP_SECONDS = 0.03

# name → virtual key code
VIRTUAL_KEYS = {
    "enter": 0x0D, "return": 0x0D, "tab": 0x09, "esc": 0x1B, "escape": 0x1B, "space": 0x20,
    "backspace": 0x08, "delete": 0x2E, "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28, "insert": 0x2D,
    **{f"f{i}": 0x6F + i for i in range(1, 13)},
}
MODIFIER_KEYS = {"ctrl": 0x11, "control": 0x11, "shift": 0x10, "alt": 0x12, "win": 0x5B, "cmd": 0x5B}

ULONG_PTR = ctypes.c_size_t


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("union", _INPUTUNION)]


def _send(*inputs: INPUT) -> bool:
    array = (INPUT * len(inputs))(*inputs)
    sent = user32.SendInput(len(inputs), array, ctypes.sizeof(INPUT))
    return sent == len(inputs)


def _mouse(flags: int, dx: int = 0, dy: int = 0) -> INPUT:
    return INPUT(type=INPUT_MOUSE, union=_INPUTUNION(mi=MOUSEINPUT(dx, dy, 0, flags, 0, 0)))


def _key(vk: int = 0, scan: int = 0, flags: int = 0) -> INPUT:
    return INPUT(type=INPUT_KEYBOARD, union=_INPUTUNION(ki=KEYBDINPUT(vk, scan, flags, 0, 0)))


def absolute_coords(x: int, y: int, virtual: tuple[int, int, int, int]) -> tuple[int, int]:
    """Physical pixels → SendInput absolute coordinates (0-65535, over the whole virtual screen). Handles multiple monitors."""
    vx, vy, vw, vh = virtual
    nx = int(round((x - vx) * 65535 / max(vw - 1, 1)))
    ny = int(round((y - vy) * 65535 / max(vh - 1, 1)))
    return max(0, min(65535, nx)), max(0, min(65535, ny))


def virtual_screen() -> tuple[int, int, int, int]:
    m = user32.GetSystemMetrics
    return m(SM_XVIRTUALSCREEN), m(SM_YVIRTUALSCREEN), m(SM_CXVIRTUALSCREEN), m(SM_CYVIRTUALSCREEN)


def cursor() -> tuple[int, int] | None:
    pt = wintypes.POINT()
    return (pt.x, pt.y) if user32.GetCursorPos(ctypes.byref(pt)) else None


def click(x: int, y: int, button: str = "left", is_double: bool = False) -> tuple[bool, str]:
    down, up = MOUSE_BUTTON_FLAGS.get(button, MOUSE_BUTTON_FLAGS["left"])
    ax, ay = absolute_coords(x, y, virtual_screen())
    move = MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK
    if not _send(_mouse(move, ax, ay)):
        return False, f"SendInput refused the mouse move (error {ctypes.get_last_error()})"
    for _ in range(2 if is_double else 1):
        time.sleep(PRESS_GAP_SECONDS)
        if not _send(_mouse(down), _mouse(up)):
            return False, f"SendInput refused the click (error {ctypes.get_last_error()})"
    return True, f"{'double ' if is_double else ''}{button} click at {x},{y}"


def type_text(text: str) -> tuple[bool, str]:
    """Send one character at a time as Unicode — Korean and emoji go in regardless of keyboard layout."""
    for ch in text:
        if ch == "\n":
            ok = _send(_key(VIRTUAL_KEYS["enter"]), _key(VIRTUAL_KEYS["enter"], flags=KEYEVENTF_KEYUP))
        else:
            units = ch.encode("utf-16-le")
            codes = [int.from_bytes(units[i:i + 2], "little") for i in range(0, len(units), 2)]
            ok = _send(*[_key(scan=c, flags=KEYEVENTF_UNICODE) for c in codes],
                       *[_key(scan=c, flags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP) for c in codes])
        if not ok:
            return False, f"SendInput refused a key (error {ctypes.get_last_error()})"
    return True, f"typed {len(text)} characters"


def press(key: str, mods: list[str]) -> tuple[bool, str]:
    name = (key or "").lower()
    vk = VIRTUAL_KEYS.get(name) or (ord(name.upper()) if len(name) == 1 and name.isalnum() else None)
    if vk is None:
        return False, f"unknown key {key!r} (known: {', '.join(sorted(VIRTUAL_KEYS))}, or one letter/digit)"
    mod_codes = []
    for m in mods:
        code = MODIFIER_KEYS.get(m.lower())
        if code is None:
            return False, f"unknown modifier {m!r} (known: {', '.join(sorted(MODIFIER_KEYS))})"
        mod_codes.append(code)
    downs = [_key(c) for c in mod_codes] + [_key(vk)]
    ups = [_key(vk, flags=KEYEVENTF_KEYUP)] + [_key(c, flags=KEYEVENTF_KEYUP) for c in reversed(mod_codes)]
    if not _send(*downs, *ups):
        return False, f"SendInput refused the key (error {ctypes.get_last_error()})"
    return True, "+".join([*mods, key])
