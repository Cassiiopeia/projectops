"""Windows backend — reads via UI Automation (comtypes) and presses via patterns without the mouse (#985).

The structure is read in one go with a CacheRequest — a COM round-trip per element is several times slower.
"""
from __future__ import annotations

import importlib.util

import desktop_input
from desktop_backends import windows_input, windows_system

# UIA ControlType id → short name (matches desktop_input.CLICKABLE_ROLES)
CONTROL_TYPES = {
    50000: "button", 50001: "calendar", 50002: "checkbox", 50003: "combobox", 50004: "edit",
    50005: "hyperlink", 50006: "image", 50007: "listitem", 50008: "list", 50009: "menu",
    50010: "menubar", 50011: "menuitem", 50012: "progressbar", 50013: "radiobutton", 50014: "scrollbar",
    50015: "slider", 50016: "spinner", 50017: "statusbar", 50018: "tab", 50019: "tabitem",
    50020: "text", 50021: "toolbar", 50022: "tooltip", 50023: "tree", 50024: "treeitem",
    50025: "custom", 50026: "group", 50027: "thumb", 50028: "datagrid", 50029: "dataitem",
    50030: "document", 50031: "splitbutton", 50032: "window", 50033: "pane", 50034: "header",
    50035: "headeritem", 50036: "table", 50037: "titlebar", 50038: "separator",
}
# action name → (pattern id, availability property name, comtypes interface name)
PATTERNS = {
    "invoke": (10000, "UIA_IsInvokePatternAvailablePropertyId", "IUIAutomationInvokePattern"),
    "toggle": (10015, "UIA_IsTogglePatternAvailablePropertyId", "IUIAutomationTogglePattern"),
    "select": (10010, "UIA_IsSelectionItemPatternAvailablePropertyId", "IUIAutomationSelectionItemPattern"),
    "expand": (10005, "UIA_IsExpandCollapsePatternAvailablePropertyId", "IUIAutomationExpandCollapsePattern"),
    "set_value": (10002, "UIA_IsValuePatternAvailablePropertyId", "IUIAutomationValuePattern"),
}
BASE_PROPERTIES = ("UIA_NamePropertyId", "UIA_ControlTypePropertyId", "UIA_BoundingRectanglePropertyId",
                   "UIA_AutomationIdPropertyId", "UIA_IsEnabledPropertyId", "UIA_IsPasswordPropertyId",
                   "UIA_HelpTextPropertyId", "UIA_IsOffscreenPropertyId")


class WindowsBackend(desktop_input.DesktopBackend):
    name = "windows"
    packages = ("mss", "comtypes")
    install_hint = "launch_cli.py desktop setup  # installs mss · comtypes into the shared venv"

    def __init__(self) -> None:
        windows_system.enable_dpi_awareness()
        self._uia = None
        self._dll = None

    # ── Readiness ──
    def missing_modules(self) -> list[str]:
        return [m for m in ("mss", "comtypes") if importlib.util.find_spec(m) is None]

    def _automation(self):
        """Create one IUIAutomation. comtypes generates the type library wrapper once on first use."""
        if self._uia is None:
            import comtypes.client
            self._dll = comtypes.client.GetModule("UIAutomationCore.dll")
            self._uia = comtypes.client.CreateObject(self._dll.CUIAutomation, interface=self._dll.IUIAutomation)
        return self._uia, self._dll

    def readiness(self) -> dict:
        return windows_system.readiness()

    def windows(self) -> list[dict]:
        return windows_system.list_windows()

    # ── Reading ──
    def _cache_request(self):
        uia, dll = self._automation()
        req = uia.CreateCacheRequest()
        for prop in BASE_PROPERTIES + tuple(p[1] for p in PATTERNS.values()):
            req.AddProperty(getattr(dll, prop))
        req.TreeScope = dll.TreeScope_Subtree
        req.TreeFilter = uia.ControlViewCondition
        return req

    def _root(self, window: dict):
        uia, _ = self._automation()
        return uia.ElementFromHandle(window["handle"]).BuildUpdatedCache(self._cache_request())

    def _node(self, el, window_title: str) -> dict | None:
        _, dll = self._automation()
        rect = el.CachedBoundingRectangle
        if el.GetCachedPropertyValue(dll.UIA_IsOffscreenPropertyId):
            return None
        actions = [name for name, (_, prop, _) in PATTERNS.items()
                   if el.GetCachedPropertyValue(getattr(dll, prop))]
        return desktop_input.make_desktop_node(
            text=el.CachedName or "", id_=el.CachedAutomationId or "", desc=el.CachedHelpText or "",
            role=CONTROL_TYPES.get(el.CachedControlType, "custom"), enabled=bool(el.CachedIsEnabled),
            secret=bool(el.CachedIsPassword), actions=actions,
            bounds=(rect.left, rect.top, rect.right, rect.bottom), window=window_title)

    def _walk(self, root, window_title: str, max_nodes: int, max_depth: int):
        """(node, path, element) depth-first. The path is a list of child indexes — the key for finding it again right before pressing."""
        stack = [(root, [], 0)]
        produced = 0
        while stack and produced < max_nodes:
            el, path, depth = stack.pop()
            if path:
                node = self._node(el, window_title)
                if node is not None:
                    produced += 1
                    yield node, path, el
            if depth >= max_depth:
                continue
            children = el.GetCachedChildren()
            if not children:
                continue
            for i in reversed(range(children.Length)):
                stack.append((children.GetElement(i), path + [i], depth + 1))

    def nodes(self, window: dict, max_nodes: int, max_depth: int) -> list[dict] | None:
        try:
            root = self._root(window)
        except Exception:   # noqa: BLE001 — the window disappeared or UIA refused
            return None
        return [{**node, "path": path} for node, path, _ in
                self._walk(root, window.get("title") or "", max_nodes, max_depth)]

    def _element_at(self, window: dict, path: list[int]):
        """Find the element again by path. None if missing."""
        el = self._root(window)
        for i in path:
            children = el.GetCachedChildren()
            if not children or i >= children.Length:
                return None
            el = children.GetElement(i)
        return el

    # ── Actions ──
    def focus(self, window: dict) -> tuple[bool, str]:
        return windows_system.bring_to_front(window["handle"])

    def perform(self, window: dict, node: dict, action: str, value: str | None = None) -> tuple[bool, str]:
        if action not in PATTERNS:
            return False, f"unknown action {action!r}"
        el = self._element_at(window, node.get("path") or [])
        if el is None:
            return False, "element is gone"
        current = self._node(el, window.get("title") or "")
        if current is None or not desktop_input.locator_matches(node, current):
            return False, "element changed"
        pattern_id, _, iface_name = PATTERNS[action]
        _, dll = self._automation()
        raw = el.GetCurrentPattern(pattern_id)
        if not raw:
            return False, f"element does not support {action}"
        pattern = raw.QueryInterface(getattr(dll, iface_name))
        if action == "invoke":
            pattern.Invoke()
        elif action == "toggle":
            pattern.Toggle()
        elif action == "select":
            pattern.Select()
        elif action == "expand":
            pattern.Expand()
        else:
            pattern.SetValue(value or "")
        return True, f"{action} via UI Automation"

    def cursor(self) -> tuple[int, int] | None:
        return windows_input.cursor()

    # GetLastInputInfo counts keyboard and mouse together
    user_input_kind = "keyboard_or_mouse"

    def seconds_since_user_input(self) -> float | None:
        return windows_system.seconds_since_last_input()

    def parent_by_pid(self) -> dict[int, int]:
        return windows_system.parent_by_pid()

    def mouse_click(self, x: int, y: int, button: str = "left", is_double: bool = False) -> tuple[bool, str]:
        return windows_input.click(x, y, button, is_double)

    def type_text(self, text: str) -> tuple[bool, str]:
        return windows_input.type_text(text)

    def press(self, key: str, mods: list[str]) -> tuple[bool, str]:
        return windows_input.press(key, mods)

    def grab(self, region: list[int] | None = None) -> bytes | None:
        import mss
        import mss.tools
        with mss.mss() as sct:
            if region:
                x1, y1, x2, y2 = region
                area = {"left": x1, "top": y1, "width": max(1, x2 - x1), "height": max(1, y2 - y1)}
            else:
                area = sct.monitors[1]
            shot = sct.grab(area)
            return mss.tools.to_png(shot.rgb, shot.size)
