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
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from common.proc import sdk_tool

import maestro_session

BOUNDS = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")
# (시작, 끝) 비율 — 화면 가장자리 제스처(뒤로가기·알림 끌어내리기)를 피해 15% 안쪽에서 움직인다
SWIPE_DIRS = {
    "up": ((0.5, 0.75), (0.5, 0.25)), "down": ((0.5, 0.25), (0.5, 0.75)),
    "left": ((0.85, 0.5), (0.15, 0.5)), "right": ((0.15, 0.5), (0.85, 0.5)),
}
SELECTOR_FIELDS = ("text", "id", "desc")
# Maestro 가 flow 의 ${...} 로 읽는 환경변수 (MAESTRO_ 접두만 셸에서 넘어간다)
INPUT_TEXT_ENV = "MAESTRO_PRO_LAUNCH_INPUT_TEXT"
# Android 화면 구조 읽기: 한 번의 최대 대기 (초) · 시도 횟수 · 다시 시도 전 쉼 (초)
UI_DUMP_TIMEOUT_SECONDS = 20
UI_DUMP_ATTEMPT_COUNT = 2
UI_DUMP_RETRY_DELAY_SECONDS = 1.5
# uiautomator 가 UiAutomation 에 못 붙었을 때의 출력 (다른 자동화 도구가 쥐고 있거나 시스템이 재시작 중)
UI_AUTOMATION_FAILURE_MARKERS = ("Killed", "UiAutomation", "TimeoutException", "already registered")


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


def maestro_inspect_nodes(json_text: str) -> list[dict]:
    """`maestro mcp` inspect_screen 응답 > 노드 목록 (hierarchy 모양으로 펼쳐 같은 길로 읽는다)."""
    return maestro_nodes(maestro_session.inspect_screen_to_hierarchy(json_text) or "{}")


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


def maestro_flow(command: dict | list[dict], app_id: str | None) -> str:
    """Maestro flow (단계 하나 또는 여러 개). 헤더 appId 는 필수라 모르면 자리표시값을 둔다(앱을 띄우지 않으므로 무관)."""
    lines = [f"appId: {app_id or 'any.app'}", "---"]
    for step in (command if isinstance(command, list) else [command]):
        (name, params), = step.items()
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
    # 뒤로 버튼이 있는 플랫폼만 True (Android). iOS 는 화면마다 뒤로가기 방식이 달라 단계로 받지 않는다
    has_back_button = False
    install_hint: str | None = None
    # 화면 구조를 못 읽었거나 시스템이 준비되지 않았을 때의 {code, reason} (Android) — tree·tap·run 응답의 code 가 된다
    device_failure: dict | None = None
    # 상주 세션을 탔는지 (iOS): {} 세션 없음 · {"transport": ...} — 응답에 그대로 붙는다
    session_report: dict = {}

    def available(self) -> bool:
        return True

    def locale(self, dev: str) -> str | None:
        return None

    def nodes(self, dev: str) -> list[dict] | None:
        """화면 요소. 읽을 수 없는 플랫폼이면 None."""
        return None

    def system_readiness_failure(self, dev: str) -> dict | None:
        """기기 시스템이 조작을 받을 상태가 아니면 {code, reason}. 모르면 None."""
        return None

    def tap_xy(self, dev: str, x: int, y: int) -> tuple[bool, str]:
        raise NotImplementedError

    def tap_ratio(self, dev: str, rx: float, ry: float) -> tuple[bool, str]:
        raise NotImplementedError

    def tap_selector(self, dev: str, field: str, value: str) -> tuple[bool, str]:
        raise NotImplementedError

    def swipe_ratio(self, dev: str, start, end, ms: int) -> tuple[bool, str]:
        raise NotImplementedError

    def input_text(self, dev: str, value: str, submit: bool = False) -> tuple[bool, str]:
        """포커스된 입력창에 글자 넣기. 값은 명령줄·파일에 남기지 않는다."""
        raise NotImplementedError

    def press_back(self, dev: str) -> tuple[bool, str]:
        """뒤로가기. 하드웨어 뒤로 버튼이 없는 플랫폼(iOS)은 구현하지 않는다."""
        raise NotImplementedError

    def grab(self, dev: str) -> bytes | None:
        """현재 화면 PNG — --shot 이 '바뀐 뒤 멈춘 화면'을 고를 때 쓴다."""
        return None


class AndroidBackend(Backend):
    """adb + uiautomator. 기기 내장이라 추가 설치가 없다."""
    name = "android"
    has_back_button = True
    install_hint = "Android SDK platform-tools(adb)를 설치하거나 ANDROID_HOME 을 맞춘다"

    def _adb(self, dev: str, *args: str, timeout: int = 15, binary: bool = False,
             input_text: str | None = None):
        adb = sdk_tool("adb")
        return subprocess.run([adb, "-s", dev, *args], capture_output=True,
                              text=not binary, timeout=timeout, input=input_text)

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
        """화면 구조: 시간 제한 + 한 번 더 시도. 못 읽으면 [] 와 함께 device_failure 에 code·사유를 남긴다."""
        self.device_failure = None
        for attempt in range(UI_DUMP_ATTEMPT_COUNT):
            try:
                # 파일을 기기에 남기지 않도록 표준출력으로 받는다
                r = self._adb(dev, "exec-out", "uiautomator", "dump", "/dev/tty", timeout=UI_DUMP_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                self.device_failure = {"code": "ui_dump_timeout",
                                        "reason": f"uiautomator dump 가 {UI_DUMP_TIMEOUT_SECONDS}초 안에 끝나지 않았다"}
            else:
                if "<hierarchy" in (r.stdout or ""):
                    return ui_nodes(r.stdout)
                self.device_failure = self._dump_failure(dev, (r.stdout or "") + (r.stderr or ""))
            if self.device_failure["code"] == "android_system_not_ready" or attempt + 1 == UI_DUMP_ATTEMPT_COUNT:
                break
            time.sleep(UI_DUMP_RETRY_DELAY_SECONDS)
        return []

    def system_readiness_failure(self, dev: str) -> dict | None:
        """부팅 애니메이션이 떠 있거나 window 서비스가 없으면 시스템이 (재)시작 중이다 (system_server 재시작 반복 실측)."""
        try:
            probe = self._adb(dev, "shell", "getprop init.svc.bootanim; service check window", timeout=10).stdout or ""
        except subprocess.TimeoutExpired:
            probe = ""
        if probe.startswith("running") or "window: not found" in probe:
            return {"code": "android_system_not_ready",
                    "reason": "Android 시스템이 (재)시작 중이다 — 부팅 애니메이션이 떠 있거나 window 서비스가 없다"}
        return None

    def _dump_failure(self, dev: str, output: str) -> dict:
        """dump 실패 원인 가르기: 시스템 재시작 중(부팅 애니메이션) > UiAutomation 연결 실패 > 그 밖."""
        not_ready = self.system_readiness_failure(dev)
        if not_ready:
            return not_ready
        if any(marker in output for marker in UI_AUTOMATION_FAILURE_MARKERS):
            return {"code": "ui_automation_unavailable",
                    "reason": "uiautomator 가 UiAutomation 에 붙지 못했다 (다른 자동화 도구가 쥐고 있거나 시스템이 불안정)"}
        return {"code": "ui_dump_failed", "reason": (output.strip()[-200:] or "빈 출력")}

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

    def input_text(self, dev, value, submit=False):
        # 공백은 `%s`. 값은 표준입력으로 읽어 따옴표 안에서만 쓴다 (명령줄·셸 메타문자에 안 실린다)
        r = self._adb(dev, "shell", 'IFS= read -r T; input text "$T"', timeout=30,
                      input_text=value.replace(" ", "%s") + "\n")
        if r.returncode == 0 and submit:
            r = self._adb(dev, "shell", "input", "keyevent", "66")   # 66 = Enter
        return r.returncode == 0, (r.stderr or "").strip()

    def press_back(self, dev):
        r = self._adb(dev, "shell", "input", "keyevent", "4")   # 4 = 뒤로
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
        # 상주 세션(app session start)을 탔나: {} 세션 없음 · {"transport": "session"} · 못 써서 내려감 + 사유
        self.session_report: dict = {}

    def has_session(self, dev: str) -> bool:
        """이 기기에 준비된 상주 세션이 있나 (중계가 살아 있는지는 호출해 봐야 안다)."""
        return maestro_session.is_ready(maestro_session.read_session(dev))

    def _session_call(self, dev: str, tool: str, arguments: dict) -> dict | None:
        """세션으로 부른다 > 결과. 세션이 없거나 못 쓰면 None (사유는 session_report 에)."""
        result, fallback_reason = maestro_session.call(dev, tool, arguments, self.timeout)
        if result is not None:
            self.session_report = {"transport": "session", **({"session_reconnected": True} if result["reconnected"] else {})}
        elif fallback_reason:
            self.session_report = {"transport": "per_call", "session_fallback": fallback_reason}
        return result

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
        result = self._session_call(dev, "inspect", {})
        if result is not None and not result["is_error"]:
            return maestro_inspect_nodes(result["text"])
        if result is not None:
            self.session_report = {"transport": "per_call", "session_fallback": "session_inspect_failed"}
        try:
            r = subprocess.run(self._base(dev) + ["hierarchy"], capture_output=True, text=True,
                               timeout=self.timeout)
        except subprocess.TimeoutExpired:
            return []
        return maestro_nodes(r.stdout or "")

    def run_flow(self, dev: str, command: dict | list[dict], env: dict | None = None) -> tuple[bool | None, list[str]]:
        """flow 한 번 실행 > (성공 여부, 출력 줄). 시간 초과면 (None, [사유]) — 단계별 결과를 읽는 쪽(app run)이 쓴다.

        상주 세션이 있으면 그것으로 (env 가 있는 flow 는 제외 — 비밀 값은 세션에 싣지 않는다, maestro_session.py 참고).
        """
        if not env:
            result = self._session_call(dev, "run", {"yaml": maestro_flow(command, self.app_id)})
            if result is not None:
                return maestro_session.flow_outcome(result)
        elif self.has_session(dev):
            # 호출마다 띄우는 maestro test 가 세션의 기기 연결을 끊는다 — 세션은 다음 호출에서 다시 붙는다
            self.session_report = {"transport": "per_call", "session_fallback": "secret_input_per_call"}
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "step.yaml"
            f.write_text(maestro_flow(command, self.app_id), encoding="utf-8")
            # 비밀 값이 있는 flow: Maestro 는 maestro.log 에 inputText 의 실제 값을 남긴다(실측) —
            # 기록을 이 임시 폴더로 돌려 함께 지운다 (기본 자리 ~/.maestro/tests 에 남지 않게)
            debug_output = ["--debug-output", str(Path(d) / "debug"), "--flatten-debug-output"] if env else []
            try:
                r = subprocess.run(self._base(dev) + ["test", *debug_output, str(f)], capture_output=True,
                                   text=True, timeout=self.timeout,
                                   env={**os.environ, **env} if env else None)
            except subprocess.TimeoutExpired:
                return None, [f"maestro 응답 없음 ({self.timeout}초)"]
        # Maestro 는 끝에 광고 상자(│ ╭ ╰)를 찍는다. 걷어내야 실패 원인 줄이 보인다
        lines = [l for l in ((r.stdout or "") + (r.stderr or "")).splitlines()
                 if l.strip() and not l.lstrip().startswith(("│", "╭", "╰"))]
        return r.returncode == 0, lines

    def _run(self, dev: str, command: dict | list[dict], env: dict | None = None) -> tuple[bool, str]:
        is_success, lines = self.run_flow(dev, command, env)
        if is_success is None:
            return False, lines[0]
        reason = [l for l in lines if "FAILED" in l or "not found" in l.lower() or "Error" in l]
        return is_success, "\n".join((reason or lines)[-6:])

    def tap_selector(self, dev, field, value):
        # Maestro 의 text·id 는 정규식이다. 괄호·물음표가 든 문구가 엉뚱하게 맞지 않도록 그대로 맞춘다
        key = "id" if field == "id" else "text"
        return self._run(dev, {"tapOn": {key: re.escape(value)}})

    def tap_ratio(self, dev, rx, ry):
        return self._run(dev, {"tapOn": {"point": pct((rx, ry))}})

    def swipe_ratio(self, dev, start, end, ms):
        return self._run(dev, {"swipe": {"start": pct(start), "end": pct(end), "duration": ms}})

    def input_text(self, dev, value, submit=False):
        # 값은 MAESTRO_ 접두 환경변수로만 넘긴다 — flow 파일·명령줄(-e)에 평문이 남지 않는다
        steps: list[dict] = [{"inputText": "${" + INPUT_TEXT_ENV + "}"}]
        if submit:
            steps.append({"pressKey": "Enter"})
        return self._run(dev, steps, env={INPUT_TEXT_ENV: value})

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
