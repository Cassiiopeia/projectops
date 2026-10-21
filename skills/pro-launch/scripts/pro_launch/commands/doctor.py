"""`doctor` — 무엇이 되고 무엇이 안 되는지."""
from __future__ import annotations

import shutil
import sys

from common.image import has_pillow, resize_tool
from common.proc import sdk_tool
from common.state import repo_unknown, venv_dir

import knowledge

from pro_launch.registry import Command
from pro_launch.runtime import browser_profiles
from pro_launch.runtime.browser import browser_choice, open_browser_status, playwright_state
from pro_launch.runtime import device_capacity, host_resources
from pro_launch.runtime.context import project_root, state_home
from pro_launch.runtime.devices import list_devices
from pro_launch.runtime.output import SKILL_DIR, out
from pro_launch.runtime.plugin_version import plugin_version


_TOOLS = [
    ("adb", False, "Android device control",
     "Android Studio → SDK Manager → SDK Tools → Android SDK Platform-Tools"),
    ("emulator", False, "AVD boot (not needed if already running)",
     "Android Studio → SDK Manager → SDK Tools → Android Emulator"),
    ("xcrun", False, "iOS simulator (macOS only)",
     "Install Xcode, then xcode-select --install"),
    ("cwebp", False, "Shrink captures to WebP (when Pillow is missing)",
     "brew install webp / apt install webp"),
    ("ffmpeg", False, "Frame extraction from recordings · shrink fallback",
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
    open_browser = open_browser_status(browser_profiles.web_state_path(root))
    memory = _memory_counts(root)
    payload = {
        "plugin_version": plugin_version(),
        # 지금 도는 스크립트 버전의 SKILL.md · references 자리 — 다른 버전 문서를 읽고 있지 않은지 대조 (#920)
        "docs_dir": str(SKILL_DIR),
        "checks": checks,
        "browser": pw,
        "browser_choice": {k: chosen.get(k) for k in ("exe", "source", "label", "reason", "error")},
        "open_browser": open_browser,
        "image_resize": shrink_by or "none — captures stay full size, costing more tokens and transfer",
        "image_hint": None if shrink_by else
            "web setup installs Pillow into a dedicated venv (the system is not touched)",
        "pillow": has_pillow(),
        "state_dir": str(home),
        "venv": str(venv_dir()),
        "platform": sys.platform,
        "memory": memory,
        "summary": (f"projectops {plugin_version()} · {sys.platform}: "
                    + (", ".join(c["tool"] for c in checks if c["found"]) or "no tools"))
                   + f" · browser {'ready' if pw['ready'] else 'missing'}"
                   + (f" ({chosen['label']})" if chosen.get("exe") else "")
                   + f" · image shrink {shrink_by or 'unavailable'}"
                   + " · memory " + ", ".join(f"{area} {row['count']}" for area, row in memory.items()),
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
    # 기기 켜기 예산 (#964) — 측정 전이면 기본값과 측정 권고
    capacity = device_capacity.capacity_view()
    payload["capacity"] = capacity
    payload["summary"] += f" · memory pressure {report['pressure']} · device budget {capacity['memory_budget_mb']}MB"
    advice = host_resources.pressure_advice(report["pressure"])
    if report["pressure"] == "critical":
        # 압박이 풀리기를 폴링하며 기다리지 않게 — 기기 밖 소비자를 보여 주고 사용자에게 묻는다 (#972)
        payload.update(host_resources.memory_risk_fields())
        payload["next"] = f"{advice} {host_resources.MEMORY_RISK_ASK_NEXT}"
    elif advice:
        payload["next"] = advice
    elif capacity["should_benchmark"]:
        payload["next"] = "device benchmark  # measure how many devices this computer can handle and save it to the settings"


def configure_doctor(p) -> None:
    p.add_argument("--resources", action="store_true",
                   help="Memory and swap pressure, large processes, running emulators and simulators with their bound repos (report only, nothing is stopped)")
    p.add_argument("--root", default=".")


COMMANDS = [
    Command(name="doctor", help="Installed tools · storage locations · memory counts (--resources for host memory pressure)", run=cmd_doctor,
            configure=configure_doctor),
]
