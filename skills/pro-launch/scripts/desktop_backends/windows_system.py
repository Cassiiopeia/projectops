"""Windows window list · privileges · secure desktop · bring to front — uses only standard-library ctypes (#985)."""
from __future__ import annotations

import ctypes
import os
from ctypes import wintypes

import desktop_input

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
dwmapi = ctypes.WinDLL("dwmapi")

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
TOKEN_QUERY = 0x0008
TOKEN_ELEVATION_CLASS = 20
DWMWA_EXTENDED_FRAME_BOUNDS, DWMWA_CLOAKED = 9, 14
UOI_NAME = 2
DESKTOP_READOBJECTS = 0x0001
SW_RESTORE = 9
GW_OWNER = 4
# Processes that draw the lock·login screen — if one is in front a person must unlock it
LOCK_SCREEN_APPS = {"lockapp.exe", "logonui.exe"}
# UAC consent window (invisible when on the secure desktop; this is its name when set to show on the normal desktop)
CONSENT_APPS = {"consent.exe"}
# Shell windows excluded from the window list — the agent never needs to pick them
SHELL_CLASSES = {"Shell_TrayWnd", "Shell_SecondaryTrayWnd", "Progman", "WorkerW"}

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

# Functions returning handles declare their return type — the default (int) truncates values on 64-bit
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
kernel32.QueryFullProcessImageNameW.argtypes = (wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                ctypes.POINTER(wintypes.DWORD))
advapi32.OpenProcessToken.argtypes = (wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE))
advapi32.GetTokenInformation.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
                                         ctypes.POINTER(wintypes.DWORD))
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindow.restype = wintypes.HWND
user32.GetWindow.argtypes = (wintypes.HWND, wintypes.UINT)
user32.OpenInputDesktop.restype = wintypes.HANDLE
user32.CloseDesktop.argtypes = (wintypes.HANDLE,)
user32.GetUserObjectInformationW.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
                                             ctypes.POINTER(wintypes.DWORD))
user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
user32.GetLastInputInfo.argtypes = (ctypes.c_void_p,)
kernel32.GetTickCount.restype = wintypes.DWORD
dwmapi.DwmGetWindowAttribute.argtypes = (wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD)


def enable_dpi_awareness() -> None:
    """Per-Monitor DPI Aware v2 — UIA coordinates·SendInput·capture all line up in physical pixels. Ignored if already on."""
    try:
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except (AttributeError, OSError):
        pass


def _text(hwnd) -> str:
    n = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def _class(hwnd) -> str:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def _pid(hwnd) -> int:
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def _bounds(hwnd) -> list[int] | None:
    """Real window area without the shadow. GetWindowRect if DWM is unavailable."""
    rect = wintypes.RECT()
    if dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(rect), ctypes.sizeof(rect)) != 0:
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return None
    return [rect.left, rect.top, rect.right, rect.bottom]


def _is_cloaked(hwnd) -> bool:
    """Windows on other virtual desktops·hidden UWP windows act visible but are not on screen."""
    cloaked = wintypes.DWORD()
    return dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked)) == 0 \
        and cloaked.value != 0


def process_image(pid: int) -> str:
    """Executable name (lowercase). Empty string if unreadable."""
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(1024)
        buf = ctypes.create_unicode_buffer(1024)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value).lower()
        return ""
    finally:
        kernel32.CloseHandle(handle)


def is_elevated(pid: int) -> bool | None:
    """Is it running elevated. None if it cannot be opened (protected processes, etc.)."""
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    token = wintypes.HANDLE()
    try:
        if not advapi32.OpenProcessToken(handle, TOKEN_QUERY, ctypes.byref(token)):
            return None
        elevation, size = wintypes.DWORD(), wintypes.DWORD()
        ok = advapi32.GetTokenInformation(token, TOKEN_ELEVATION_CLASS, ctypes.byref(elevation),
                                          ctypes.sizeof(elevation), ctypes.byref(size))
        return bool(elevation.value) if ok else None
    finally:
        if token:
            kernel32.CloseHandle(token)
        kernel32.CloseHandle(handle)


def self_elevated() -> bool:
    return bool(is_elevated(os.getpid()))


def foreground_handle() -> int:
    return user32.GetForegroundWindow() or 0


def list_windows() -> list[dict]:
    """Visible top-level windows (with title, no owner, hidden·other-desktop excluded). Front first."""
    found: list[int] = []

    def collect(hwnd, _):
        if user32.IsWindowVisible(hwnd) and not user32.GetWindow(hwnd, GW_OWNER) \
                and _text(hwnd) and _class(hwnd) not in SHELL_CLASSES and not _is_cloaked(hwnd):
            found.append(hwnd)
        return True

    user32.EnumWindows(WNDENUMPROC(collect), 0)
    front = foreground_handle()
    mine = self_elevated()
    rows = []
    for hwnd in found:   # EnumWindows is in Z order (front → back)
        bounds = _bounds(hwnd)
        # Zero-size windows cannot be picked — placeholder windows that spawn dialogs (OpenWith, observed) remain like this
        if not bounds or bounds[2] <= bounds[0] or bounds[3] <= bounds[1]:
            if not user32.IsIconic(hwnd):
                continue
        pid = _pid(hwnd)
        elevated = is_elevated(pid)
        rows.append({"handle": int(hwnd), "pid": pid, "app": process_image(pid), "title": _text(hwnd),
                     "bounds": bounds, "foreground": int(hwnd) == front,
                     "minimized": bool(user32.IsIconic(hwnd)),
                     # The OS blocks input to windows with higher privileges than ours (UIPI)
                     "elevated": bool(elevated) and not mine})
    return rows


def input_desktop_name() -> str | None:
    """Name of the desktop receiving input. None on the secure desktop (UAC·Ctrl+Alt+Del·lock) since it cannot be opened."""
    desk = user32.OpenInputDesktop(0, False, DESKTOP_READOBJECTS)
    if not desk:
        return None
    try:
        buf = ctypes.create_unicode_buffer(256)
        needed = wintypes.DWORD()
        if user32.GetUserObjectInformationW(desk, UOI_NAME, buf, ctypes.sizeof(buf), ctypes.byref(needed)):
            return buf.value
        return None
    finally:
        user32.CloseDesktop(desk)


def readiness() -> dict:
    desktop = input_desktop_name()
    front = foreground_handle()
    front_app = process_image(_pid(front)) if front else ""
    return {"secure_desktop": desktop is None or desktop.lower() != "default",
            "locked": front_app in LOCK_SCREEN_APPS,
            "consent_prompt": front_app in CONSENT_APPS,
            "foreground_app": front_app, "self_elevated": self_elevated(), "permissions": {}}


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


def seconds_since_last_input() -> float | None:
    """Seconds since the last keyboard·mouse input (GetLastInputInfo, whole session). None on failure (#985)."""
    info = LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(LASTINPUTINFO)
    if not user32.GetLastInputInfo(ctypes.byref(info)):
        return None
    return desktop_input.tick_elapsed_seconds(int(kernel32.GetTickCount()), int(info.dwTime))


TH32CS_SNAPPROCESS = 0x00000002
INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value
kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
kernel32.CreateToolhelp32Snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * 260)]


kernel32.Process32FirstW.argtypes = (wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W))
kernel32.Process32NextW.argtypes = (wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W))


def parent_by_pid() -> dict[int, int]:
    """pid → parent pid (Toolhelp snapshot). Empty dict on failure."""
    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if not snapshot or snapshot == INVALID_HANDLE_VALUE:
        return {}
    parents: dict[int, int] = {}
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        more = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while more:
            parents[int(entry.th32ProcessID)] = int(entry.th32ParentProcessID)
            more = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    return parents


def bring_to_front(hwnd: int) -> tuple[bool, str]:
    """Restore from minimized and bring to front. Windows blocks other processes stealing the foreground, so input threads are briefly attached."""
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    if foreground_handle() == hwnd:
        return True, "already in front"
    front = foreground_handle()
    me = kernel32.GetCurrentThreadId()
    other = user32.GetWindowThreadProcessId(front, None) if front else 0
    attached = bool(other) and other != me and user32.AttachThreadInput(me, other, True)
    try:
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    finally:
        if attached:
            user32.AttachThreadInput(me, other, False)
    return (True, "brought to front") if foreground_handle() == hwnd else \
        (False, "Windows refused to bring the window to the front")
