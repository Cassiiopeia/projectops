"""macOS backend: read via the accessibility API (AX), press without the mouse via AXPress·AXValue (#985)
pyobjc is imported only inside methods — class import and macos_nodes work without pyobjc
"""
from __future__ import annotations

import importlib.util

import desktop_input
from desktop_backends import macos_input, macos_nodes, macos_system

# Max seconds an unresponsive app can hold an AX call — the default (~6 s) makes one tree take tens of seconds
AX_MESSAGING_TIMEOUT_SECONDS = 1.0
# At or below this many nodes, Electron is assumed to have its accessibility tree off (turned on via AXManualAccessibility)
ELECTRON_EMPTY_NODE_COUNT = 3
# Time for the browser to build the tree after turning on the page accessibility tree (s)
WEB_TREE_BUILD_SECONDS = 0.6
# Tolerance comparing CG window ↔ AX window frames (points)
FRAME_TOLERANCE_POINTS = 2
# Input field values are not used as names — typing changes the name and the next action becomes ref_stale
VALUE_ROLES = ("textfield", "combobox")
# First segment of a menu bar icon (AXExtrasMenuBar) path
EXTRAS_PATH_HEAD = -1


def _attr(element, name):
    from ApplicationServices import AXUIElementCopyAttributeValue
    err, value = AXUIElementCopyAttributeValue(element, name, None)
    return value if err == 0 else None


def _frame(element) -> tuple[float, float, float, float] | None:
    """(x1, y1, x2, y2) point."""
    from ApplicationServices import AXValueGetValue, kAXValueCGPointType, kAXValueCGSizeType
    pos, size = _attr(element, "AXPosition"), _attr(element, "AXSize")
    if pos is None or size is None:
        return None
    _, point = AXValueGetValue(pos, kAXValueCGPointType, None)
    _, extent = AXValueGetValue(size, kAXValueCGSizeType, None)
    return (point.x, point.y, point.x + extent.width, point.y + extent.height)


def _raw_actions(element) -> list[str]:
    from ApplicationServices import AXUIElementCopyActionNames
    err, names = AXUIElementCopyActionNames(element, None)
    return list(names or []) if err == 0 else []


def _is_settable(element, name: str) -> bool:
    from ApplicationServices import AXUIElementIsAttributeSettable
    err, settable = AXUIElementIsAttributeSettable(element, name, None)
    return err == 0 and bool(settable)


def _app_element(pid: int):
    from ApplicationServices import AXUIElementCreateApplication, AXUIElementSetMessagingTimeout
    app = AXUIElementCreateApplication(pid)
    AXUIElementSetMessagingTimeout(app, AX_MESSAGING_TIMEOUT_SECONDS)
    return app


def _ax_windows(app) -> list:
    """The app's AX windows. Notification Center has empty AXWindows and windows only in AXChildren (observed)."""
    wins = list(_attr(app, "AXWindows") or [])
    if wins:
        return wins
    return [c for c in (_attr(app, "AXChildren") or []) if _attr(c, "AXRole") == "AXWindow"]


def _xywh(frame) -> tuple[float, float, float, float]:
    x1, y1, x2, y2 = frame
    return (x1, y1, x2 - x1, y2 - y1)


def _frame_matches(a, b) -> bool:
    return all(abs(x - y) <= FRAME_TOLERANCE_POINTS for x, y in zip(a, b))


def _banner_count(window) -> int:
    """Number of banners in the Notification Center window — only within depth 6 (window > group > group > scroll > banner, observed 4 levels)."""
    stack, count = [(window, 0)], 0
    while stack:
        el, depth = stack.pop()
        if _attr(el, "AXSubrole") in macos_nodes.NOTIFICATION_SUBROLES:
            count += 1
            continue
        if depth < 6:
            stack.extend((c, depth + 1) for c in (_attr(el, "AXChildren") or []))
    return count


class MacBackend(desktop_input.DesktopBackend):
    name = "macos"
    packages = ("mss", "pyobjc-framework-ApplicationServices", "pyobjc-framework-Quartz")
    install_hint = "launch_cli.py desktop setup  # installs mss · pyobjc into the shared venv"

    def __init__(self) -> None:
        self._screens = None

    # ── Readiness ──
    def missing_modules(self) -> list[str]:
        return [m for m in ("mss", "ApplicationServices", "Quartz", "AppKit") if importlib.util.find_spec(m) is None]

    def readiness(self) -> dict:
        return macos_system.readiness()

    def screens(self) -> list[macos_nodes.Screen]:
        if self._screens is None:
            self._screens = macos_system.screens()
        return self._screens

    def _pixels(self, frame) -> list[int]:
        return list(macos_nodes.points_to_pixels(frame, self.screens()))

    # ── Windows ──
    def windows(self) -> list[dict]:
        """Regular apps' layer 0 windows + system dialogs·notification banners (overlay). Front to back."""
        rows = [r for r in macos_system.cg_windows()
                if r["owner"] not in macos_system.EXCLUDED_OWNERS and r["frame"][2] > 0 and r["frame"][3] > 0
                and r["alpha"] > 0]
        front_pid = macos_system.frontmost_pid()
        apps: dict[int, tuple[str, str, bool]] = {}
        result, has_front, overlay_pids = [], False, []
        for r in rows:
            if r["pid"] not in apps:
                apps[r["pid"]] = macos_system.app_info(r["pid"])
            app_name, bundle, is_regular = apps[r["pid"]]
            if r["layer"] == 0 and is_regular:
                is_front = not has_front and r["pid"] == front_pid
                has_front = has_front or is_front
                x, y, w, h = r["frame"]
                result.append({"handle": r["number"], "pid": r["pid"], "app": app_name or r["owner"],
                               "title": r["title"] or app_name or r["owner"], "foreground": is_front,
                               "elevated": False, "bounds": self._pixels((x, y, x + w, y + h)),
                               "_ax_frame": [x, y, x + w, y + h]})
            elif r["pid"] not in overlay_pids:
                overlay_pids.append(r["pid"])
        floating = {r["pid"] for r in rows if macos_nodes.is_floating_panel(r["layer"], r["frame"])}
        overlays = [o for pid in overlay_pids for o in self._overlays(pid, apps[pid], rows, pid in floating)]
        for o in overlays:
            # A dialog in front receives keys (keys_target_refusal checks this before key input)
            o["foreground"] = o["overlay_kind"] == "dialog" and o["pid"] == front_pid and not has_front
        return overlays + result

    def _overlays(self, pid: int, info: tuple[str, str, bool], rows: list[dict], has_panel: bool) -> list[dict]:
        """Windows of agent apps (Notification Center · auth popup · 2FA code window, etc.) that hold a dialog or banner."""
        app_name, bundle, _ = info
        app_name = app_name or next((r["owner"] for r in rows if r["pid"] == pid), "")
        found = []
        for index, win in enumerate(_ax_windows(_app_element(pid))):
            subrole = _attr(win, "AXSubrole") or ""
            is_center = bundle == macos_nodes.NOTIFICATION_CENTER_BUNDLE
            banners = _banner_count(win) if is_center else 0
            frame = _frame(win)
            is_panel = has_panel and frame is not None and macos_nodes.is_floating_panel(1, _xywh(frame))
            if frame is None or not macos_nodes.is_listed_overlay(bundle, [subrole], banners, is_panel):
                continue
            x1, y1, x2, y2 = frame
            number = next((r["number"] for r in rows if r["pid"] == pid
                           and _frame_matches(r["frame"], (x1, y1, x2 - x1, y2 - y1))), None)
            found.append({"handle": number if number is not None else -(pid * 100 + index), "pid": pid,
                          "app": app_name, "title": _attr(win, "AXTitle") or app_name, "foreground": False,
                          "elevated": False, "overlay": True,
                          "overlay_kind": "notification" if is_center else "dialog",
                          "bounds": self._pixels(frame), "_ax_frame": list(frame), "_ax_index": index})
        return found

    def _window_element(self, window: dict):
        """Window dict > AX window element. The one whose frame and title match, otherwise None."""
        app = _app_element(window["pid"])
        wins = _ax_windows(app)
        if window.get("overlay") and window.get("_ax_index", -1) < len(wins):
            return app, wins[window["_ax_index"]]
        target = window.get("_ax_frame")
        for win in wins:
            frame = _frame(win)
            if frame and target and _frame_matches(frame, target):
                return app, win
        return app, (wins[0] if len(wins) == 1 else None)

    # ── Reading ──
    def _node(self, element, window_title: str) -> dict | None:
        role, subrole = _attr(element, "AXRole") or "", _attr(element, "AXSubrole")
        short = macos_nodes.role_name(role, subrole)
        frame = _frame(element)
        raw = _raw_actions(element)
        value = None if short in VALUE_ROLES else _attr(element, "AXValue")
        enabled = _attr(element, "AXEnabled")
        return desktop_input.make_desktop_node(
            text=macos_nodes.pick_text(_attr(element, "AXTitle"), _attr(element, "AXDescription"), value),
            id_=_attr(element, "AXIdentifier") or "", desc=_attr(element, "AXHelp") or "", role=short,
            enabled=enabled is None or bool(enabled), secret=macos_nodes.is_secret_role(role, subrole),
            actions=macos_nodes.action_names(raw, short in VALUE_ROLES and _is_settable(element, "AXValue")),
            bounds=tuple(self._pixels(frame)) if frame else None, window=window_title,
            named_actions=macos_nodes.named_actions(raw))

    def _walk(self, roots: list[tuple[object, list[int]]], window_title: str, max_nodes: int, max_depth: int):
        """(node, path, element) depth-first. The path is a list of child indexes — the key for finding it again right before pressing."""
        stack = [(el, path, 0) for el, path in reversed(roots)]
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
            children = list(_attr(el, "AXChildren") or [])
            for i in reversed(range(len(children))):
                stack.append((children[i], path + [i], depth + 1))

    def _roots(self, app, win, window: dict) -> list[tuple[object, list[int]]]:
        roots = [(win, [])]
        extras = None if window.get("overlay") else _attr(app, "AXExtrasMenuBar")
        if extras is not None:
            roots.append((extras, [EXTRAS_PATH_HEAD]))
        return roots

    def nodes(self, window: dict, max_nodes: int, max_depth: int) -> list[dict] | None:
        try:
            app, win = self._window_element(window)
            if win is None:
                return None
            title = window.get("title") or ""
            rows = [{**n, "path": p} for n, p, _ in self._walk(self._roots(app, win, window), title,
                                                               max_nodes, max_depth)]
            if ((len(rows) <= ELECTRON_EMPTY_NODE_COUNT or macos_nodes.has_empty_web_area(rows))
                    and self._enable_web_tree(app)):
                rows = [{**n, "path": p} for n, p, _ in self._walk(self._roots(app, win, window), title,
                                                                   max_nodes, max_depth)]
            return rows
        except Exception:   # noqa: BLE001 — the app is unresponsive or the window disappeared
            return None

    def _enable_web_tree(self, app) -> bool:
        """Electron · Chrome keep the page accessibility tree off — turn it on, wait a moment and read again.

        Electron: AXManualAccessibility. Chrome: AXEnhancedUserInterface (Chrome turns it on even when returning -25208, observed).
        """
        import time

        from ApplicationServices import AXUIElementSetAttributeValue
        AXUIElementSetAttributeValue(app, "AXManualAccessibility", True)
        AXUIElementSetAttributeValue(app, "AXEnhancedUserInterface", True)
        time.sleep(WEB_TREE_BUILD_SECONDS)
        return True

    def _element_at(self, window: dict, path: list[int]):
        app, win = self._window_element(window)
        if win is None or not path:
            return None
        el = win
        if path[0] == EXTRAS_PATH_HEAD:
            el, path = _attr(app, "AXExtrasMenuBar"), path[1:]
        for i in path:
            children = list(_attr(el, "AXChildren") or []) if el is not None else []
            if i >= len(children):
                return None
            el = children[i]
        return el

    # ── Actions ──
    def focus(self, window: dict) -> tuple[bool, str]:
        """AX actions need no focus — overlays count as success even if they cannot come to front (keys are blocked by keys_target_refusal)."""
        if window.get("overlay_kind") == "notification":
            return True, "notification — no focus needed"
        from ApplicationServices import AXUIElementPerformAction, AXUIElementSetAttributeValue
        is_activated = macos_system.activate(window["pid"], _app_element(window["pid"]))
        _, win = self._window_element(window)
        if win is not None:
            AXUIElementPerformAction(win, "AXRaise")
            AXUIElementSetAttributeValue(win, "AXMain", True)
        if is_activated or macos_system.frontmost_pid() == window["pid"]:
            return True, "brought to front"
        if window.get("overlay"):
            return True, "system window stays behind — buttons still work"
        return False, "macOS refused to bring the app to the front"

    def perform(self, window: dict, node: dict, action: str, value: str | None = None) -> tuple[bool, str]:
        from ApplicationServices import AXUIElementPerformAction, AXUIElementSetAttributeValue
        el = self._element_at(window, node.get("path") or [])
        if el is None:
            return False, "element is gone"
        current = self._node(el, window.get("title") or "")
        if current is None or not desktop_input.locator_matches(node, current):
            return False, "element changed"
        if action.startswith(NAMED_PREFIX):
            name = action[len(NAMED_PREFIX):]
            raw = next((a for a in _raw_actions(el) if macos_nodes.parse_named_action(a) == name), None)
            if raw is None:
                return False, f"no action named {name!r}"
            err = AXUIElementPerformAction(el, raw)
        elif action == "set_value":
            err = AXUIElementSetAttributeValue(el, "AXValue", value or "")
        elif action == "focus":
            # Focus the input without the mouse — keys go to that field even if another window covers it
            err = AXUIElementSetAttributeValue(el, "AXFocused", True)
        elif action in AX_FOR_ACTION:
            err = AXUIElementPerformAction(el, AX_FOR_ACTION[action])
        else:
            return False, f"unknown action {action!r}"
        return (True, action) if err == 0 else (False, f"AX error {err} on {action}")

    def cursor(self) -> tuple[int, int] | None:
        x, y = macos_input.cursor_points()
        px = macos_nodes.points_to_pixels((x, y, x, y), self.screens())
        return px[0], px[1]

    user_input_kind = "keyboard"

    def seconds_since_user_input(self) -> float | None:
        return macos_system.seconds_since_key_input()

    def parent_by_pid(self) -> dict[int, int]:
        return macos_system.parent_by_pid()

    def mouse_click(self, x: int, y: int, button: str = "left", is_double: bool = False) -> tuple[bool, str]:
        px, py = macos_nodes.pixels_to_points(x, y, self.screens())
        return macos_input.click_points(px, py, button, is_double)

    def type_text(self, text: str) -> tuple[bool, str]:
        return macos_input.type_unicode(text)

    def press(self, key: str, mods: list[str]) -> tuple[bool, str]:
        code = macos_nodes.key_code(key)
        if code is None:
            return False, f"unknown key {key!r} (known: {', '.join(sorted(macos_nodes.KEY_CODES))}, or one letter/digit)"
        flags, unknown = macos_nodes.modifier_flags(mods)
        if unknown:
            return False, f"unknown modifier {unknown!r} (known: {', '.join(sorted(macos_nodes.MODIFIER_FLAGS))})"
        ok, _ = macos_input.press_key(code, flags)
        return ok, "+".join([*mods, key])

    def grab(self, region: list[int] | None = None) -> bytes | None:
        if region is None:
            return macos_input.grab_points(None)
        x1, y1 = macos_nodes.pixels_to_points(region[0], region[1], self.screens())
        x2, y2 = macos_nodes.pixels_to_points(region[2] - 1, region[3] - 1, self.screens())
        return macos_input.grab_points((x1, y1, x2 + 1, y2 + 1))


# Contract action name > AX action (set_value uses AXValue)
AX_FOR_ACTION = {"invoke": "AXPress", "select": "AXPick"}
# Prefix for named actions passed by click --action
NAMED_PREFIX = "named:"
