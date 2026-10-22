"""Windows 창 목록 · 권한 · 보안 화면 · 창 앞으로 — 표준 라이브러리 ctypes 만 쓴다 (#985)."""
from __future__ import annotations

import ctypes
import os
from ctypes import wintypes

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
# 잠금화면·로그인 화면을 그리는 프로세스 — 이게 앞이면 사람이 풀어야 한다
LOCK_SCREEN_APPS = {"lockapp.exe", "logonui.exe"}
# UAC 동의 창 (보안 데스크톱에 뜨면 아예 보이지 않고, 일반 데스크톱에 뜨는 설정이면 이 이름이다)
CONSENT_APPS = {"consent.exe"}
# 창 목록에서 뺄 셸 창 — agent 가 고를 일이 없다
SHELL_CLASSES = {"Shell_TrayWnd", "Shell_SecondaryTrayWnd", "Progman", "WorkerW"}

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

# 핸들을 돌려주는 함수는 반환형을 적는다 — 기본값(int)이면 64비트에서 값이 잘린다
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
dwmapi.DwmGetWindowAttribute.argtypes = (wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD)


def enable_dpi_awareness() -> None:
    """Per-Monitor DPI Aware v2 — UIA 좌표·SendInput·캡처가 모두 물리 픽셀로 맞는다. 이미 켜져 있으면 무시된다."""
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
    """그림자를 뺀 실제 창 영역. DWM 이 없으면 GetWindowRect."""
    rect = wintypes.RECT()
    if dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(rect), ctypes.sizeof(rect)) != 0:
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return None
    return [rect.left, rect.top, rect.right, rect.bottom]


def _is_cloaked(hwnd) -> bool:
    """다른 가상 데스크톱·숨은 UWP 창은 보이는 것처럼 굴지만 화면에 없다."""
    cloaked = wintypes.DWORD()
    return dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked)) == 0 \
        and cloaked.value != 0


def process_image(pid: int) -> str:
    """실행 파일 이름 (소문자). 못 읽으면 빈 문자열."""
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
    """관리자 권한으로 도는가. 열어 볼 수 없으면 None (보호 프로세스 등)."""
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
    """보이는 최상위 창 (제목 있음, 소유자 없음, 숨김·다른 데스크톱 제외). 앞에 있는 것부터."""
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
    for hwnd in found:   # EnumWindows 는 Z 순서(앞 → 뒤)
        bounds = _bounds(hwnd)
        # 크기 0 창은 고를 수 없다 — 대화상자를 띄우는 자리표시 창(OpenWith 실측)이 이렇게 남는다
        if not bounds or bounds[2] <= bounds[0] or bounds[3] <= bounds[1]:
            if not user32.IsIconic(hwnd):
                continue
        pid = _pid(hwnd)
        elevated = is_elevated(pid)
        rows.append({"handle": int(hwnd), "pid": pid, "app": process_image(pid), "title": _text(hwnd),
                     "bounds": bounds, "foreground": int(hwnd) == front,
                     "minimized": bool(user32.IsIconic(hwnd)),
                     # 우리보다 높은 권한의 창에는 OS 가 입력을 막는다 (UIPI)
                     "elevated": bool(elevated) and not mine})
    return rows


def input_desktop_name() -> str | None:
    """입력을 받는 데스크톱 이름. 보안 데스크톱(UAC·Ctrl+Alt+Del·잠금)이면 열 수 없어 None."""
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


def bring_to_front(hwnd: int) -> tuple[bool, str]:
    """최소화를 풀고 앞으로. Windows 는 다른 프로세스가 앞을 뺏는 것을 막아서 입력 스레드를 잠시 붙인다."""
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
