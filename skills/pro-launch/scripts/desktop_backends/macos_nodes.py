"""macOS 백엔드의 순수 규칙 (#985) — AX 값 해석 · 좌표 변환 · 키 코드 · 창 고르기.

pyobjc 를 가져오지 않는다. 그래서 CI(ubuntu·macOS, pyobjc 없음)에서 그대로 테스트된다.
"""
from __future__ import annotations

# 알림 배너를 띄우는 프로세스 (macOS 14·15 실측)
NOTIFICATION_CENTER_BUNDLE = "com.apple.notificationcenterui"
# 시스템 대화상자로 보는 창 subrole — 2FA 팝업은 소유 프로세스를 몰라 이름 대신 이걸로 고른다
DIALOG_SUBROLES = ("AXSystemDialog", "AXDialog")
# 배너 subrole — 15.1 은 Banner, 15.2+ 보고는 Alert
NOTIFICATION_SUBROLES = ("AXNotificationCenterBanner", "AXNotificationCenterAlert")
# 메뉴바 줄 높이 (point) — 이 줄의 떠 있는 창은 메뉴바 아이콘이다
MENU_BAR_HEIGHT_POINTS = 40
# 화면에 떠 있으면 사람만 답할 수 있는 창의 소유자 (암호·관리자 권한 · 로그인 화면)
SECURE_OWNERS = ("SecurityAgent", "loginwindow")

# AX role → desktop_input.CLICKABLE_ROLES 와 같은 짧은 이름
ROLE_MAP = {
    "AXButton": "button", "AXCheckBox": "checkbox", "AXRadioButton": "radiobutton",
    "AXMenuItem": "menuitem", "AXMenuBarItem": "menuitem", "AXLink": "link",
    "AXTextField": "textfield", "AXTextArea": "textfield", "AXSearchField": "textfield",
    "AXSecureTextField": "textfield", "AXPopUpButton": "combobox", "AXComboBox": "combobox",
    "AXRow": "row", "AXTab": "tabitem", "AXStaticText": "text", "AXCell": "cell",
}
SECRET_ROLES = ("AXSecureTextField",)

# AX 동작 → 계약의 동작 이름 (AXShowMenu 는 메뉴를 여는 것이라 누르기로 쓰지 않는다)
AX_ACTIONS = {"AXPress": "invoke", "AXPick": "select"}
NAMED_ACTION_PREFIX = "Name:"

# 가상 키코드 (Carbon kVK_*) — Windows VIRTUAL_KEYS 와 같은 이름을 쓴다
KEY_CODES = {
    "enter": 36, "tab": 48, "space": 49, "backspace": 51, "escape": 53, "delete": 117,
    "left": 123, "right": 124, "down": 125, "up": 126,
    "home": 115, "end": 119, "pageup": 116, "pagedown": 121,
    "f1": 122, "f2": 120, "f3": 99, "f4": 118, "f5": 96, "f6": 97,
    "f7": 98, "f8": 100, "f9": 101, "f10": 109, "f11": 103, "f12": 111,
}
LETTER_CODES = {
    "a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7, "c": 8, "v": 9, "b": 11,
    "q": 12, "w": 13, "e": 14, "r": 15, "y": 16, "t": 17, "1": 18, "2": 19, "3": 20, "4": 21,
    "6": 22, "5": 23, "9": 25, "7": 26, "8": 28, "0": 29, "o": 31, "u": 32, "i": 34, "p": 35,
    "l": 37, "j": 38, "k": 40, "n": 45, "m": 46,
}
KEY_ALIASES = {"return": "enter", "esc": "escape", "del": "delete"}
# CGEventFlags — 수식키 (win 은 Windows 키 자리라 cmd 로 본다)
MODIFIER_FLAGS = {"shift": 1 << 17, "ctrl": 1 << 18, "control": 1 << 18, "alt": 1 << 19, "option": 1 << 19,
                  "cmd": 1 << 20, "command": 1 << 20, "win": 1 << 20}

Rect = tuple[float, float, float, float]
# ((x, y, w, h) AX 좌표계 point, backingScaleFactor)
Screen = tuple[Rect, float]


# ── AX 값 ──

def pick_text(title, description, value) -> str:
    """보여 줄 이름 — AXTitle > AXDescription > 문자열 AXValue 중 처음 비지 않은 값."""
    for candidate in (title, description, value):
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return ""


def role_name(role: str | None, subrole: str | None) -> str:
    if subrole in NOTIFICATION_SUBROLES:
        return "notification"
    if role in ROLE_MAP:
        return ROLE_MAP[role]
    name = role or ""
    return (name[2:] if name.startswith("AX") else name).lower()


def is_secret_role(role: str | None, subrole: str | None) -> bool:
    """비밀번호 칸 — 보통 role AXTextField + subrole AXSecureTextField 로 온다 (실측)."""
    return role in SECRET_ROLES or subrole in SECRET_ROLES


def parse_named_action(raw: str) -> str | None:
    """`Name:닫기\\nTarget:0x0\\nSelector:(null)` > `닫기`. 표준 AX 동작이면 None."""
    if not raw or not raw.startswith(NAMED_ACTION_PREFIX):
        return None
    name = raw[len(NAMED_ACTION_PREFIX):].split("\n", 1)[0].strip()
    return name or None


def action_names(raw_actions: list[str], is_value_settable: bool) -> list[str]:
    names = [AX_ACTIONS[a] for a in raw_actions if a in AX_ACTIONS]
    if is_value_settable:
        names.append("set_value")
    return names


def named_actions(raw_actions: list[str]) -> list[str]:
    return [n for n in (parse_named_action(a) for a in raw_actions) if n]


def has_empty_web_area(rows: list[dict]) -> bool:
    """웹 영역은 있는데 그 안이 비었는가 — Chrome 은 접근성 클라이언트가 없으면 페이지 트리를 만들지 않는다."""
    areas = [r["path"] for r in rows if r.get("role") == "webarea"]
    if not areas:
        return False
    return not any(len(r["path"]) > len(a) and r["path"][:len(a)] == a for a in areas for r in rows)


# ── 좌표 (AX·CGEvent = 주 화면 왼쪽 위 원점 point, 계약 = 물리 픽셀) ──

def flip_ns_frame(ns_frame: Rect, main_height: float) -> Rect:
    """NSScreen 프레임(왼쪽 아래 원점) > AX 좌표계(왼쪽 위 원점)."""
    x, y, w, h = ns_frame
    return (x, main_height - y - h, w, h)


def screen_for_point(x: float, y: float, screens: list[Screen]) -> Screen:
    for screen in screens:
        (sx, sy, sw, sh), _ = screen
        if sx <= x < sx + sw and sy <= y < sy + sh:
            return screen
    return screens[0] if screens else ((0, 0, 0, 0), 1.0)


def _top_scale(screens: list[Screen]) -> float:
    return max((s[1] or 1.0 for s in screens), default=1.0)


def _pixel_origin(screen: Screen, screens: list[Screen]) -> tuple[float, float]:
    """화면 왼쪽 위 픽셀 좌표 = point 원점 × 가장 큰 배율
    (자기 배율이면 Retina 주 화면 0~3456px 과 오른쪽 모니터 1728pt 가 겹침)"""
    (sx, sy, _, _), _ = screen
    top = _top_scale(screens)
    return sx * top, sy * top


def points_to_pixels(frame: tuple[float, float, float, float], screens: list[Screen]) -> tuple[int, int, int, int]:
    """(x1, y1, x2, y2) point > 물리 픽셀. 요소 중심이 속한 화면의 배율을 쓴다."""
    x1, y1, x2, y2 = frame
    screen = screen_for_point((x1 + x2) / 2, (y1 + y2) / 2, screens)
    (sx, sy, _, _), scale = screen
    scale = scale or 1.0
    ox, oy = _pixel_origin(screen, screens)
    return (int(round(ox + (x1 - sx) * scale)), int(round(oy + (y1 - sy) * scale)),
            int(round(ox + (x2 - sx) * scale)), int(round(oy + (y2 - sy) * scale)))


def pixels_to_points(x: int, y: int, screens: list[Screen]) -> tuple[float, float]:
    """물리 픽셀 > point. 픽셀 영역이 그 점을 품는 화면을 찾는다."""
    for screen in screens:
        (sx, sy, sw, sh), scale = screen
        scale = scale or 1.0
        ox, oy = _pixel_origin(screen, screens)
        if ox <= x < ox + sw * scale and oy <= y < oy + sh * scale:
            return sx + (x - ox) / scale, sy + (y - oy) / scale
    top = _top_scale(screens)
    return x / top, y / top


# ── 키 ──

def key_code(name: str) -> int | None:
    key = KEY_ALIASES.get(name.lower(), name.lower())
    if key in KEY_CODES:
        return KEY_CODES[key]
    return LETTER_CODES.get(key)


def modifier_flags(mods: list[str]) -> tuple[int, str | None]:
    """(합친 플래그, 모르는 이름)."""
    flags = 0
    for m in mods:
        flag = MODIFIER_FLAGS.get(m.lower())
        if flag is None:
            return 0, m
        flags |= flag
    return flags, None


# ── 창 · 준비 상태 ──

def is_floating_panel(layer: int, frame: Rect) -> bool:
    """layer 가 0 보다 위인 떠 있는 창 — 메뉴바 줄(y 0, 높이 MENU_BAR_HEIGHT 이하)의 아이콘은 뺀다."""
    _, y, _, h = frame
    return layer > 0 and not (y <= 0 and h <= MENU_BAR_HEIGHT_POINTS)


def is_listed_overlay(owner_bundle: str, subroles: list[str], banner_count: int,
                      is_floating_panel: bool = False) -> bool:
    """일반 앱이 아닌 창을 목록에 넣을지. 알림 센터는 배너가 있을 때만 (없으면 화면 전체 투명 창이다).

    2FA 코드 창(FollowUpUI)은 subrole 이 AXStandardWindow 라 떠 있는 창인지로 고른다 (실측).
    """
    if owner_bundle == NOTIFICATION_CENTER_BUNDLE:
        return banner_count > 0
    return is_floating_panel or any(s in DIALOG_SUBROLES for s in subroles)


def readiness_from(session: dict | None, owners_on_screen: list[str], is_ax_trusted: bool,
                   is_capture_allowed: bool) -> dict:
    """CGSessionCopyCurrentDictionary · 화면 위 창 소유자 · 권한 두 개 > 계약의 readiness 모양."""
    session = session or {}
    return {"locked": bool(session.get("CGSSessionScreenIsLocked")),
            "secure_desktop": any(o in SECURE_OWNERS for o in owners_on_screen),
            "permissions": {"accessibility": bool(is_ax_trusted), "screen_recording": bool(is_capture_allowed)}}
