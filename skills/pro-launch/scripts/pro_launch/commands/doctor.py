"""`doctor` — what works and what does not."""
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
    """What works and what does not. A capability skill has no required tools — only what you plan to use."""
    checks = []
    for name, required, why, how in _TOOLS:
        path = sdk_tool(name) if name in ("adb", "emulator") else shutil.which(name)
        checks.append({"tool": name, "found": bool(path), "path": path, "why": why,
                       **({} if path else {"install": how})})
    root = project_root(args)
    home = state_home(root)
    shrink_by = resize_tool()
    pw = playwright_state()
    # Playwright is needed to know the bundled path. Without it, env vars and installed browsers are still visible
    chosen = browser_choice()
    open_browser = open_browser_status(browser_profiles.web_state_path(root))
    memory = _memory_counts(root)
    payload = {
        "plugin_version": plugin_version(),
        # SKILL.md · references location of the running script version — check you are not reading another version's docs (#920)
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
    """Memory count and last-used date per area — shows memory exists even for work outside launch_cli (adb, Maestro directly) (#863)."""
    scopes = ("machine",) if repo_unknown(root) else ("repo", "machine")
    return knowledge.area_summary({scope: knowledge.store_path(scope, root) for scope in scopes})


def _attach_resources(payload: dict) -> None:
    """--resources: memory pressure level · large processes · running virtual devices and their bound repos (#883). Report only."""
    report = host_resources.resource_report(list_devices())
    payload["resources"] = report
    # Device boot budget (#964) — before measuring, the default and a recommendation to measure
    capacity = device_capacity.capacity_view()
    payload["capacity"] = capacity
    payload["summary"] += f" · memory pressure {report['pressure']} · device budget {capacity['memory_budget_mb']}MB"
    advice = host_resources.pressure_advice(report["pressure"])
    if report["pressure"] == "critical":
        # Do not poll waiting for pressure to ease — show consumers outside devices and ask the user (#972)
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
