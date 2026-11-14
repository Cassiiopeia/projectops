"""Pure rules of the macOS backend (#985) — AX value parsing · coordinate conversion · key codes · window picking.

Does not import pyobjc, so it is tested as is on CI (ubuntu·macOS, no pyobjc).
"""
from __future__ import annotations

# Processes that show notification banners (observed on macOS 14·15)
NOTIFICATION_CENTER_BUNDLE = "com.apple.notificationcenterui"
# Window subroles treated as system dialogs — the 2FA popup's owning process is unknown, so it is picked by this instead of name
DIALOG_SUBROLES = ("AXSystemDialog", "AXDialog")
# Banner subrole — Banner on 15.1, reported as Alert on 15.2+
NOTIFICATION_SUBROLES = ("AXNotificationCenterBanner", "AXNotificationCenterAlert")
# Menu bar row height (points) — floating windows in this row are menu bar icons
MENU_BAR_HEIGHT_POINTS = 40
# Owners of windows only a person can answer when on screen (password · admin rights · login screen)
SECURE_OWNERS = ("SecurityAgent", "loginwindow")

# AX role → short names matching desktop_input.CLICKABLE_ROLES
ROLE_MAP = {
    "AXButton": "button", "AXCheckBox": "checkbox", "AXRadioButton": "radiobutton",
    "AXMenuItem": "menuitem", "AXMenuBarItem": "menuitem", "AXLink": "link",
    "AXTextField": "textfield", "AXTextArea": "textfield", "AXSearchField": "textfield",
    "AXSecureTextField": "textfield", "AXPopUpButton": "combobox", "AXComboBox": "combobox",
    "AXRow": "row", "AXTab": "tabitem", "AXStaticText": "text", "AXCell": "cell",
}
SECRET_ROLES = ("AXSecureTextField",)

# AX action → contract action name (AXShowMenu opens a menu, so it is not used as a press)
AX_ACTIONS = {"AXPress": "invoke", "AXPick": "select"}
NAMED_ACTION_PREFIX = "Name:"

# Virtual key codes (Carbon kVK_*) — same names as Windows VIRTUAL_KEYS
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
# CGEventFlags — modifiers (win is the Windows key slot, treated as cmd)
MODIFIER_FLAGS = {"shift": 1 << 17, "ctrl": 1 << 18, "control": 1 << 18, "alt": 1 << 19, "option": 1 << 19,
                  "cmd": 1 << 20, "command": 1 << 20, "win": 1 << 20}

Rect = tuple[float, float, float, float]
# ((x, y, w, h) AX-space points, backingScaleFactor)
Screen = tuple[Rect, float]


# ── AX values ──

def pick_text(title, description, value) -> str:
    """Name to show — the first non-empty of AXTitle > AXDescription > string AXValue."""
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
    """Password field — usually arrives as role AXTextField + subrole AXSecureTextField (observed)."""
    return role in SECRET_ROLES or subrole in SECRET_ROLES


def parse_named_action(raw: str) -> str | None:
    """`Name:Close\\nTarget:0x0\\nSelector:(null)` > `Close`. None for standard AX actions."""
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
    """Is there a web area that is empty inside — Chrome does not build the page tree without an accessibility client."""
    areas = [r["path"] for r in rows if r.get("role") == "webarea"]
    if not areas:
        return False
    return not any(len(r["path"]) > len(a) and r["path"][:len(a)] == a for a in areas for r in rows)


# ── Coordinates (AX·CGEvent = points with origin at main screen top-left, contract = physical pixels) ──

def flip_ns_frame(ns_frame: Rect, main_height: float) -> Rect:
    """NSScreen frame (bottom-left origin) > AX space (top-left origin)."""
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
    """Screen top-left pixel coordinate = point origin × largest scale
    (with its own scale, a Retina main screen 0-3456px and a right-hand monitor at 1728pt would overlap)"""
    (sx, sy, _, _), _ = screen
    top = _top_scale(screens)
    return sx * top, sy * top


def points_to_pixels(frame: tuple[float, float, float, float], screens: list[Screen]) -> tuple[int, int, int, int]:
    """(x1, y1, x2, y2) points > physical pixels. Uses the scale of the screen containing the element center."""
    x1, y1, x2, y2 = frame
    screen = screen_for_point((x1 + x2) / 2, (y1 + y2) / 2, screens)
    (sx, sy, _, _), scale = screen
    scale = scale or 1.0
    ox, oy = _pixel_origin(screen, screens)
    return (int(round(ox + (x1 - sx) * scale)), int(round(oy + (y1 - sy) * scale)),
            int(round(ox + (x2 - sx) * scale)), int(round(oy + (y2 - sy) * scale)))


def pixels_to_points(x: int, y: int, screens: list[Screen]) -> tuple[float, float]:
    """Physical pixels > points. Finds the screen whose pixel area contains the point."""
    for screen in screens:
        (sx, sy, sw, sh), scale = screen
        scale = scale or 1.0
        ox, oy = _pixel_origin(screen, screens)
        if ox <= x < ox + sw * scale and oy <= y < oy + sh * scale:
            return sx + (x - ox) / scale, sy + (y - oy) / scale
    top = _top_scale(screens)
    return x / top, y / top


# ── Keys ──

def key_code(name: str) -> int | None:
    key = KEY_ALIASES.get(name.lower(), name.lower())
    if key in KEY_CODES:
        return KEY_CODES[key]
    return LETTER_CODES.get(key)


def modifier_flags(mods: list[str]) -> tuple[int, str | None]:
    """(combined flags, unknown names)."""
    flags = 0
    for m in mods:
        flag = MODIFIER_FLAGS.get(m.lower())
        if flag is None:
            return 0, m
        flags |= flag
    return flags, None


# ── Windows · readiness ──

def is_floating_panel(layer: int, frame: Rect) -> bool:
    """Floating windows with layer above 0 — menu bar row icons (y 0, height up to MENU_BAR_HEIGHT) are excluded."""
    _, y, _, h = frame
    return layer > 0 and not (y <= 0 and h <= MENU_BAR_HEIGHT_POINTS)


def is_listed_overlay(owner_bundle: str, subroles: list[str], banner_count: int,
                      is_floating_panel: bool = False) -> bool:
    """Whether to list a non-regular-app window. Notification Center only when a banner exists (otherwise it is a full-screen transparent window).

    The 2FA code window (FollowUpUI) has subrole AXStandardWindow, so it is picked by being a floating window (observed).
    """
    if owner_bundle == NOTIFICATION_CENTER_BUNDLE:
        return banner_count > 0
    return is_floating_panel or any(s in DIALOG_SUBROLES for s in subroles)


def readiness_from(session: dict | None, owners_on_screen: list[str], is_ax_trusted: bool,
                   is_capture_allowed: bool) -> dict:
    """CGSessionCopyCurrentDictionary · on-screen window owners · two permissions > the contract's readiness shape."""
    session = session or {}
    return {"locked": bool(session.get("CGSSessionScreenIsLocked")),
            "secure_desktop": any(o in SECURE_OWNERS for o in owners_on_screen),
            "permissions": {"accessibility": bool(is_ax_trusted), "screen_recording": bool(is_capture_allowed)}}
