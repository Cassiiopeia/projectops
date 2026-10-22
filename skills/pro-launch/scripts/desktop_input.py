"""PC 화면(데스크톱)을 읽고 누르는 OS 백엔드 (#985).

launch_cli.py 의 `desktop …` 동작이 이 모듈만 부른다. OS 차이는 전부 `desktop_backends/` 에 있다.

설계
- **화면 구조(접근성 API)로 찾고, 마우스를 움직이지 않고 누르는 것이 기본**이다.
  Windows 는 UI Automation 의 Invoke·Value·Toggle 패턴, macOS 는 AXPress·AXValue.
  그래서 사용자 커서를 건드리지 않는다 (`transport: "invoke"`).
- 패턴이 없는 요소만 마우스로 누른다 (`transport: "mouse"`). 그 전에 사용자가 마우스를 움직였는지 본다.
- 모든 백엔드는 **같은 모양의 노드**를 돌려준다. `node_match.find_nodes` 가 그대로 쓰도록 text·id·desc 를 둔다.
- CLI 호출마다 새 프로세스라 접근성 객체를 넘겨받을 수 없다. 그래서 요소를 **위치 정보(locator)** 로 기억하고
  누르기 직전에 다시 찾는다 — 창 + 트리 속 경로 + 종류·이름. 어긋나면 `ref_stale`.

새 OS 추가
1. `DesktopBackend` 를 상속한 클래스를 `desktop_backends/` 에 만든다.
2. 아래 `BACKENDS` 에 등록한다 (키 = `platform_key()` 가 돌려주는 이름).
3. tests/test_desktop_input.py 의 계약 테스트가 빠진 메서드를 잡는다.
"""
from __future__ import annotations

import importlib
import sys

# 노드 하나에 남기는 필드 — 결과 JSON 의 elements 항목 모양
NODE_FIELDS = ("ref", "text", "id", "desc", "role", "clickable", "enabled", "secret",
               "actions", "named_actions", "bounds", "center", "window", "mutating")
# 누를 수 있다고 보는 종류 (UIA ControlType · AX role 을 소문자 짧은 이름으로 맞춘 값)
CLICKABLE_ROLES = {"button", "checkbox", "radiobutton", "menuitem", "hyperlink", "link", "tabitem",
                   "listitem", "treeitem", "combobox", "splitbutton", "edit", "textfield", "cell"}
# 마우스 없이 실행할 수 있는 동작 이름 (백엔드가 actions 에 넣는 값)
ACTION_NAMES = ("invoke", "toggle", "select", "expand", "set_value")
# 사용자가 마우스를 이만큼(픽셀) 넘게 움직였으면 입력하지 않는다 — 트랙패드 떨림은 넘긴다
CURSOR_DRIFT_PIXELS = 4
# tree 기본 노드 수 상한 — 큰 앱(IDE·브라우저) 전체를 다 읽으면 수 초가 걸린다
DEFAULT_MAX_NODES = 300
DEFAULT_MAX_DEPTH = 25


# ── 공통 순수 함수 (OS 없이 테스트된다) ─────────────────────────────────

def make_desktop_node(*, text: str, id_: str, desc: str, role: str, enabled: bool, secret: bool,
                      actions: list[str], bounds: tuple[int, int, int, int] | None, window: str,
                      named_actions: list[str] | None = None) -> dict | None:
    """원시 값 → 노드. 크기가 0 이거나 화면 밖이면 None (보이지 않는 요소는 누를 수 없다).

    named_actions: 이름으로만 부르는 숨은 버튼 (macOS 알림 배너의 닫기·보기 등). `click --action` 이 쓴다.
    """
    if not bounds:
        return None
    x1, y1, x2, y2 = (int(v) for v in bounds)
    if x2 <= x1 or y2 <= y1:
        return None
    role = (role or "").lower()
    clickable = bool(actions) or bool(named_actions) or role in CLICKABLE_ROLES
    return {"text": (text or "").strip(), "id": id_ or "", "desc": (desc or "").strip(), "role": role,
            "clickable": clickable, "enabled": bool(enabled), "secret": bool(secret),
            "actions": [a for a in actions if a in ACTION_NAMES], "named_actions": list(named_actions or []),
            "bounds": [x1, y1, x2, y2],
            "center": [(x1 + x2) // 2, (y1 + y2) // 2], "window": window or ""}


def is_worth_listing(node: dict) -> bool:
    """agent 에게 보여 줄 노드인가 — 글자가 있거나, 누를 수 있거나, 입력칸이다."""
    return bool(node["text"] or node["desc"] or node["clickable"] or node["role"] in ("edit", "textfield"))


def assign_refs(nodes: list[dict]) -> list[dict]:
    """1 부터 번호를 붙인다. `find`·`tree` 결과와 `click --ref` 가 같은 번호를 쓴다."""
    return [{**n, "ref": i} for i, n in enumerate(nodes, start=1)]


def public_node(node: dict) -> dict:
    """결과에 싣는 모양 — locator(경로·핸들)는 상태 파일에만 둔다. 빈 값은 뺀다."""
    return {k: node[k] for k in NODE_FIELDS if k in node and node[k] not in ("", None, [])}


def locator_matches(saved: dict, current: dict) -> bool:
    """ref 를 저장한 뒤 화면이 바뀌었는지 — 종류·이름이 같아야 같은 요소로 본다.

    위치는 창을 옮기면 바뀌므로 비교하지 않는다. 이름이 빈 요소는 id 로 비교한다.
    """
    if (saved.get("role") or "") != (current.get("role") or ""):
        return False
    if saved.get("text") or current.get("text"):
        return (saved.get("text") or "") == (current.get("text") or "")
    return (saved.get("id") or "") == (current.get("id") or "")


def ratio_point(bounds: list[int], rx: float, ry: float) -> tuple[int, int]:
    """창(또는 화면) 영역 안의 0~1 비율 → 물리 픽셀 좌표."""
    x1, y1, x2, y2 = bounds
    return int(round(x1 + (x2 - x1) * rx)), int(round(y1 + (y2 - y1) * ry))


def scale_point(x: float, y: float, scale: float) -> tuple[int, int]:
    """논리 좌표(macOS point 등) × 배율 → 물리 픽셀. 배율이 0 이하면 1 로 본다."""
    s = scale if scale and scale > 0 else 1.0
    return int(round(x * s)), int(round(y * s))


def cursor_moved_by_user(last: list[int] | None, now: tuple[int, int] | None,
                         threshold: int = CURSOR_DRIFT_PIXELS) -> bool:
    """마지막으로 우리가 둔 커서 위치에서 사용자가 움직였는가. 기록이 없으면 판단하지 않는다(False)."""
    if not last or now is None:
        return False
    return abs(now[0] - last[0]) > threshold or abs(now[1] - last[1]) > threshold


def platform_key(platform: str | None = None) -> str | None:
    """sys.platform → 백엔드 이름. 지원하지 않는 OS 는 None."""
    p = platform or sys.platform
    if p == "win32":
        return "windows"
    if p == "darwin":
        return "macos"
    return None


# ── 백엔드 계약 ──────────────────────────────────────────────────────────

class DesktopBackend:
    """OS 하나. 화면을 바꾸는 메서드는 (성공, 사람이 읽는 이유)를 돌려준다."""

    name = ""
    # venv 에 깔 패키지 · 설치 안내 (desktop setup 이 쓴다)
    packages: tuple[str, ...] = ()
    install_hint = ""

    def missing_modules(self) -> list[str]:
        """가져올 수 없는 모듈 이름 — 비어 있으면 쓸 수 있다."""
        raise NotImplementedError

    def readiness(self) -> dict:
        """권한·잠금화면·보안 화면 상태. {"locked": bool, "secure_desktop": bool, "permissions": {...}}"""
        raise NotImplementedError

    def windows(self) -> list[dict]:
        """열린 창: {handle, pid, app, title, bounds, foreground, elevated}."""
        raise NotImplementedError

    def nodes(self, window: dict, max_nodes: int, max_depth: int) -> list[dict] | None:
        """그 창의 노드 목록. 각 노드에 locator(`path`) 를 함께 둔다. 못 읽으면 None."""
        raise NotImplementedError

    def focus(self, window: dict) -> tuple[bool, str]:
        raise NotImplementedError

    def perform(self, window: dict, node: dict, action: str, value: str | None = None) -> tuple[bool, str]:
        """마우스 없이 실행 (invoke·toggle·select·expand·set_value)."""
        raise NotImplementedError

    def cursor(self) -> tuple[int, int] | None:
        raise NotImplementedError

    def mouse_click(self, x: int, y: int, button: str = "left", is_double: bool = False) -> tuple[bool, str]:
        raise NotImplementedError

    def type_text(self, text: str) -> tuple[bool, str]:
        raise NotImplementedError

    def press(self, key: str, mods: list[str]) -> tuple[bool, str]:
        raise NotImplementedError

    def grab(self, region: list[int] | None = None) -> bytes | None:
        """PNG bytes. region = [x1, y1, x2, y2] 물리 픽셀, None 이면 주 화면."""
        raise NotImplementedError


# 이름 → "모듈:클래스". 백엔드 모듈은 OS 전용 라이브러리를 가져오므로 쓸 때만 불러온다.
BACKENDS = {
    "windows": "desktop_backends.windows_uia:WindowsBackend",
    "macos": "desktop_backends.macos_ax:MacBackend",
}


def get_backend(name: str | None = None) -> DesktopBackend | None:
    key = name or platform_key()
    target = BACKENDS.get(key or "")
    if not target:
        return None
    module_name, class_name = target.split(":")
    return getattr(importlib.import_module(module_name), class_name)()
