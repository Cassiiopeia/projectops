"""`doctor` — 무엇이 되고 무엇이 안 되는지."""
from __future__ import annotations

import shutil
import sys

from common.image import has_pillow, resize_tool
from common.proc import sdk_tool
from common.state import repo_unknown, venv_dir

import knowledge

from pro_launch.registry import Command
from pro_launch.runtime.browser import browser_choice, open_browser_status, playwright_state, state_path
from pro_launch.runtime import host_resources
from pro_launch.runtime.context import project_root, state_home
from pro_launch.runtime.devices import list_devices
from pro_launch.runtime.output import out


_TOOLS = [
    ("adb", False, "Android 기기 제어",
     "Android Studio → SDK Manager → SDK Tools → Android SDK Platform-Tools"),
    ("emulator", False, "AVD 부팅 (이미 켜져 있으면 불필요)",
     "Android Studio → SDK Manager → SDK Tools → Android Emulator"),
    ("xcrun", False, "iOS 시뮬레이터 (macOS 전용)",
     "Xcode 설치 후 xcode-select --install"),
    ("cwebp", False, "캡처를 WebP 로 줄이기 (Pillow 가 없을 때)",
     "brew install webp / apt install webp"),
    ("ffmpeg", False, "녹화에서 프레임 추출 · 축소 폴백",
     "brew install ffmpeg / apt install ffmpeg / winget install ffmpeg"),
]


def cmd_doctor(args) -> int:
    """무엇이 되고 무엇이 안 되는지. 능력 스킬이라 필수 도구는 없다 — 쓰려는 것만 있으면 된다."""
    checks = []
    for name, required, why, how in _TOOLS:
        path = sdk_tool(name) if name in ("adb", "emulator") else shutil.which(name)
        checks.append({"tool": name, "found": bool(path), "path": path, "why": why,
                       **({} if path else {"install": how})})
    root = project_root(args)
    home = state_home(root)
    shrink_by = resize_tool()
    pw = playwright_state()
    # Playwright 가 있어야 번들 경로를 알 수 있다. 없어도 환경변수·설치된 브라우저는 보인다
    chosen = browser_choice()
    open_browser = open_browser_status(state_path(root))
    memory = _memory_counts(root)
    payload = {
        "checks": checks,
        "browser": pw,
        "browser_choice": {k: chosen.get(k) for k in ("exe", "source", "label", "reason", "error")},
        "open_browser": open_browser,
        "image_resize": shrink_by or "없음 — 캡처가 원본 크기로 남아 토큰·전송량이 커진다",
        "image_hint": None if shrink_by else
            "web setup 을 돌리면 전용 venv 에 Pillow 가 함께 깔립니다 (시스템은 건드리지 않습니다)",
        "pillow": has_pillow(),
        "state_dir": str(home),
        "venv": str(venv_dir()),
        "platform": sys.platform,
        "memory": memory,
        "summary": (f"{sys.platform}: "
                    + (", ".join(c["tool"] for c in checks if c["found"]) or "도구 없음"))
                   + f" · 브라우저 {'준비' if pw['ready'] else '없음'}"
                   + (f" ({chosen['label']})" if chosen.get("exe") else "")
                   + f" · 이미지 축소 {shrink_by or '불가'}"
                   + " · 기억 " + ", ".join(f"{area} {row['count']}" for area, row in memory.items()),
    }
    if args.resources:
        _attach_resources(payload)
    return out(payload)


def _memory_counts(root) -> dict:
    """영역별 기억 건수·마지막 사용일 — launch_cli 를 안 거치는 작업(adb·Maestro 직접)에도 기억이 있음을 보이게 (#863)."""
    scopes = ("machine",) if repo_unknown(root) else ("repo", "machine")
    return knowledge.area_summary({scope: knowledge.store_path(scope, root) for scope in scopes})


def _attach_resources(payload: dict) -> None:
    """--resources: 메모리 압박 단계 · 큰 프로세스 · 켜진 가상 기기와 묶은 레포 (#883). 보고만 한다."""
    report = host_resources.resource_report(list_devices())
    payload["resources"] = report
    payload["summary"] += f" · 메모리 압박 {report['pressure']}"
    advice = host_resources.pressure_advice(report["pressure"])
    if advice:
        payload["next"] = advice


def configure_doctor(p) -> None:
    p.add_argument("--resources", action="store_true",
                   help="메모리·스왑 압박, 큰 프로세스, 켜진 에뮬레이터·시뮬레이터와 묶은 레포 (보고만, 끄지 않는다)")
    p.add_argument("--root", default=".")


COMMANDS = [
    Command(name="doctor", help="도구 설치 여부 · 저장 위치 · 기억 건수 (--resources 로 호스트 메모리 압박)", run=cmd_doctor,
            configure=configure_doctor),
]
