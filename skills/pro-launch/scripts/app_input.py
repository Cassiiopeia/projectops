"""앱 화면을 누르고·밀고·읽는 플랫폼 백엔드 (#826).

launch_cli.py 의 `app tap|swipe|tree` 가 이 모듈만 부른다. 플랫폼 차이는 전부 여기 있다.

설계
- **화면 요소로 찾는 것이 기본**이다(문구·id·접근성 설명). agent 는 축소된 캡처를 보고 좌표를
  읽기 때문에 픽셀 좌표는 기기 해상도와 어긋난다. 좌표는 0~1 비율로만 받는다.
- 모든 백엔드는 **같은 모양의 노드**를 돌려준다 — {text, id, desc, clickable, bounds, center}.
  그래서 launch_cli 와 agent 는 플랫폼을 몰라도 된다.

새 플랫폼 추가 (예: 실기기 iOS 를 idb 로)
1. `Backend` 를 상속한 클래스를 만들고 필요한 메서드를 채운다.
2. 아래 `BACKENDS` 에 플랫폼 이름으로 등록한다 (`_pick_device` 가 돌려주는 이름과 같아야 한다).
3. tests/test_launch_cli.py 에 기기 없이 도는 단위 테스트를 넣는다. 실기기가 필요하면 local_only.
자세한 계약은 references/extending.md.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from common.proc import sdk_tool

BOUNDS = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")
# (시작, 끝) 비율 — 화면 가장자리 제스처(뒤로가기·알림 끌어내리기)를 피해 15% 안쪽에서 움직인다
SWIPE_DIRS = {
    "up": ((0.5, 0.75), (0.5, 0.25)), "down": ((0.5, 0.25), (0.5, 0.75)),
    "left": ((0.85, 0.5), (0.15, 0.5)), "right": ((0.15, 0.5), (0.85, 0.5)),
}
SELECTOR_FIELDS = ("text", "id", "desc")


# ── 공통 순수 함수 (기기 없이 테스트된다) ─────────────────────────────────

def parse_ratio(raw: str | None) -> tuple[float, float] | None:
    """'0.5,0.8' → (0.5, 0.8). 범위 밖이면 None — 픽셀을 비율 자리에 넣은 호출을 막는다."""
    if not raw:
        return None
    try:
        x, y = (float(v) for v in raw.split(","))
    except ValueError:
        return None
    return (x, y) if 0 <= x <= 1 and 0 <= y <= 1 else None


def make_node(text: str, id_: str, desc: str, clickable: bool, bounds: str) -> dict | None:
    m = BOUNDS.match(bounds or "")
    if not m:
        return None
    x1, y1, x2, y2 = map(int, m.groups())
    if x2 <= x1 or y2 <= y1:   # 크기 0 = 화면에 안 보이는 노드
        return None
    return {"text": text, "id": id_, "desc": desc, "clickable": clickable,
            "bounds": [x1, y1, x2, y2], "center": [(x1 + x2) // 2, (y1 + y2) // 2]}


def ui_nodes(xml_text: str) -> list[dict]:
    """Android uiautomator dump XML → 노드 목록."""
    import xml.etree.ElementTree as ET
    # dump 를 /dev/tty 로 받으면 XML 뒤에 'UI hierchary dumped to' 안내가 붙는다
    body = xml_text[xml_text.find("<"):xml_text.rfind(">") + 1]
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return []
    nodes = []
    for el in root.iter("node"):
        n = make_node(el.get("text", ""), el.get("resource-id", ""), el.get("content-desc", ""),
                      el.get("clickable") == "true", el.get("bounds", ""))
        if n:
            nodes.append(n)
    return nodes


def maestro_nodes(json_text: str) -> list[dict]:
    """`maestro hierarchy` JSON → 노드 목록. iOS 는 보이는 문구가 accessibilityText 에 오는 일이 많다."""
    try:
        tree = json.loads(json_text[json_text.find("{"):])
    except ValueError:
        return []
    nodes: list[dict] = []

    def walk(n):
        a = n.get("attributes") or {}
        label = a.get("text") or a.get("accessibilityText") or ""
        if label or a.get("resource-id"):
            node = make_node(label, a.get("resource-id", ""), a.get("accessibilityText", ""),
                             True, a.get("bounds", ""))
            if node:
                nodes.append(node)
        for c in n.get("children") or []:
            walk(c)
    walk(tree)
    return nodes


def match_nodes(nodes: list[dict], field: str, value: str) -> list[dict]:
    """정확히 같은 것 → 포함하는 것 순. id 는 `pkg:id/name` 과 `name` 둘 다 받는다."""
    exact = [n for n in nodes if n[field] == value
             or (field == "id" and n[field].endswith(":id/" + value))]
    if exact:
        return exact
    return [n for n in nodes if value and value in n[field]]


def slim(nodes: list[dict], limit: int = 80) -> list[dict]:
    """agent 에게 넘길 요소 목록 — 부모·자식 중복과 빈 값을 걷어 토큰을 아낀다."""
    seen, outl = set(), []
    for n in nodes:
        key = (n["text"], n["id"], n["desc"])
        if key in seen:
            continue
        seen.add(key)
        outl.append({k: v for k, v in n.items() if v not in ("", None) and k != "bounds"})
    return outl[:limit]


def maestro_flow(command: dict, app_id: str | None) -> str:
    """한 동작짜리 Maestro flow. 헤더 appId 는 필수라 모르면 자리표시값을 둔다(앱을 띄우지 않으므로 무관)."""
    lines = [f"appId: {app_id or 'any.app'}", "---"]
    (name, params), = command.items()
    if isinstance(params, dict):
        lines.append(f"- {name}:")
        lines += [f"    {k}: {json.dumps(v, ensure_ascii=False)}" for k, v in params.items()]
    else:
        lines.append(f"- {name}: {json.dumps(params, ensure_ascii=False)}")
    return "\n".join(lines) + "\n"


def pct(p: tuple[float, float]) -> str:
    return f"{round(p[0] * 100)}%,{round(p[1] * 100)}%"


# ── 백엔드 ─────────────────────────────────────────────────────────────────

class Backend:
    """플랫폼 백엔드 계약. 모든 동작은 (성공 여부, 사람이 읽을 사유) 를 돌려준다."""
    name = "base"
    # 백엔드가 요소를 직접 찾아 누르면 True (예: Maestro). False 면 nodes() 로 찾아 tap_xy 로 누른다
    selects_itself = False
    install_hint: str | None = None

    def available(self) -> bool:
        return True

    def locale(self, dev: str) -> str | None:
        return None

    def nodes(self, dev: str) -> list[dict] | None:
        """화면 요소. 읽을 수 없는 플랫폼이면 None."""
        return None

    def tap_xy(self, dev: str, x: int, y: int) -> tuple[bool, str]:
        raise NotImplementedError

    def tap_ratio(self, dev: str, rx: float, ry: float) -> tuple[bool, str]:
        raise NotImplementedError

    def tap_selector(self, dev: str, field: str, value: str) -> tuple[bool, str]:
        raise NotImplementedError

    def swipe_ratio(self, dev: str, start, end, ms: int) -> tuple[bool, str]:
        raise NotImplementedError

    def grab(self, dev: str) -> bytes | None:
        """현재 화면 PNG — --shot 이 '바뀐 뒤 멈춘 화면'을 고를 때 쓴다."""
        return None


class AndroidBackend(Backend):
    """adb + uiautomator. 기기 내장이라 추가 설치가 없다."""
    name = "android"
    install_hint = "Android SDK platform-tools(adb)를 설치하거나 ANDROID_HOME 을 맞춘다"

    def _adb(self, dev: str, *args: str, timeout: int = 15, binary: bool = False):
        adb = sdk_tool("adb")
        return subprocess.run([adb, "-s", dev, *args], capture_output=True,
                              text=not binary, timeout=timeout)

    def available(self) -> bool:
        return bool(sdk_tool("adb"))

    def locale(self, dev: str) -> str | None:
        # 사용자가 언어를 바꾼 적이 없으면 persist 값이 비어 있다 — 그때는 공장 기본값을 본다
        for prop in ("persist.sys.locale", "ro.product.locale"):
            v = (self._adb(dev, "shell", "getprop", prop).stdout or "").strip()
            if v:
                return v
        return None

    def nodes(self, dev: str) -> list[dict]:
        # 파일을 기기에 남기지 않도록 표준출력으로 받는다
        r = self._adb(dev, "exec-out", "uiautomator", "dump", "/dev/tty", timeout=30)
        return ui_nodes(r.stdout or "")

    def _size(self, dev: str) -> tuple[int, int] | None:
        """화면 크기. Override 가 있으면 그것이 실제 입력 좌표계라 마지막 값을 쓴다."""
        sizes = re.findall(r"(\d+)x(\d+)", self._adb(dev, "shell", "wm", "size").stdout or "")
        return (int(sizes[-1][0]), int(sizes[-1][1])) if sizes else None

    def tap_xy(self, dev, x, y):
        r = self._adb(dev, "shell", "input", "tap", str(x), str(y))
        return r.returncode == 0, (r.stderr or "").strip()

    def tap_ratio(self, dev, rx, ry):
        size = self._size(dev)
        if not size:
            return False, "wm size 를 읽지 못했다"
        return self.tap_xy(dev, round(rx * size[0]), round(ry * size[1]))

    def swipe_ratio(self, dev, start, end, ms):
        size = self._size(dev)
        if not size:
            return False, "wm size 를 읽지 못했다"
        pts = [round(start[0] * size[0]), round(start[1] * size[1]),
               round(end[0] * size[0]), round(end[1] * size[1])]
        r = self._adb(dev, "shell", "input", "swipe", *map(str, pts), str(ms))
        return r.returncode == 0, (r.stderr or "").strip()

    def grab(self, dev):
        # exec-out 은 바이너리를 그대로 준다. shell 로 받으면 줄바꿈이 바뀌어 PNG 가 깨진다
        r = self._adb(dev, "exec-out", "screencap", "-p", timeout=30, binary=True)
        return r.stdout if r.stdout.startswith(b"\x89PNG") else None


class IOSMaestroBackend(Backend):
    """iOS 시뮬레이터. simctl 에는 탭·화면구조 명령이 없어 Maestro(오픈소스 E2E)에 맡긴다.

    호출마다 Maestro(JVM)가 새로 떠서 10~40초 걸린다. 긴 시나리오는 프로젝트의 Maestro flow 로 돌린다.
    """
    name = "ios"
    selects_itself = True
    install_hint = 'curl -fsSL "https://get.maestro.mobile.dev" | bash'

    def __init__(self, app_id: str | None = None, timeout: int = 90):
        self.app_id, self.timeout = app_id, timeout

    @staticmethod
    def _maestro() -> str | None:
        p = shutil.which("maestro") or str(Path.home() / ".maestro" / "bin" / "maestro")
        return p if Path(p).exists() else None

    def available(self) -> bool:
        return bool(self._maestro())

    def _base(self, dev: str) -> list[str]:
        return [self._maestro()] + (["--device", dev] if dev != "booted" else [])

    def locale(self, dev):
        r = subprocess.run(["xcrun", "simctl", "spawn", dev, "defaults", "read", "-g", "AppleLanguages"],
                           capture_output=True, text=True, timeout=15)
        m = re.search(r'"?([A-Za-z]{2}(?:-[A-Za-z]+)?)"?', r.stdout or "")
        return m.group(1) if m else None

    def nodes(self, dev):
        try:
            r = subprocess.run(self._base(dev) + ["hierarchy"], capture_output=True, text=True,
                               timeout=self.timeout)
        except subprocess.TimeoutExpired:
            return []
        return maestro_nodes(r.stdout or "")

    def _run(self, dev: str, command: dict) -> tuple[bool, str]:
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "step.yaml"
            f.write_text(maestro_flow(command, self.app_id), encoding="utf-8")
            try:
                r = subprocess.run(self._base(dev) + ["test", str(f)], capture_output=True,
                                   text=True, timeout=self.timeout)
            except subprocess.TimeoutExpired:
                return False, f"maestro 응답 없음 ({self.timeout}초)"
        # Maestro 는 끝에 광고 상자(│ ╭ ╰)를 찍는다. 걷어내야 실패 원인 줄이 보인다
        lines = [l for l in ((r.stdout or "") + (r.stderr or "")).splitlines()
                 if l.strip() and not l.lstrip().startswith(("│", "╭", "╰"))]
        reason = [l for l in lines if "FAILED" in l or "not found" in l.lower() or "Error" in l]
        return r.returncode == 0, "\n".join((reason or lines)[-6:])

    def tap_selector(self, dev, field, value):
        # Maestro 의 text·id 는 정규식이다. 괄호·물음표가 든 문구가 엉뚱하게 맞지 않도록 그대로 맞춘다
        key = "id" if field == "id" else "text"
        return self._run(dev, {"tapOn": {key: re.escape(value)}})

    def tap_ratio(self, dev, rx, ry):
        return self._run(dev, {"tapOn": {"point": pct((rx, ry))}})

    def swipe_ratio(self, dev, start, end, ms):
        return self._run(dev, {"swipe": {"start": pct(start), "end": pct(end), "duration": ms}})

    def grab(self, dev):
        r = subprocess.run(["xcrun", "simctl", "io", dev, "screenshot", "--type=png", "-"],
                           capture_output=True, timeout=30)
        return r.stdout if r.stdout.startswith(b"\x89PNG") else None


# 플랫폼 이름 → 백엔드 생성기. launch_cli._pick_device 가 돌려주는 이름과 같아야 한다
BACKENDS = {
    "android": lambda app_id=None: AndroidBackend(),
    "ios": lambda app_id=None: IOSMaestroBackend(app_id=app_id),
}


def get_backend(platform: str, app_id: str | None = None) -> Backend | None:
    make = BACKENDS.get(platform)
    return make(app_id) if make else None
