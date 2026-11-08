"""OS별 정리 후보 위치표: 키 > 경로·단계(tier)·정리 방식

tier 3개: safe (다시 받거나 만들어짐, 한 번 확인 후 정리), decide (사용자가 이름을 대야 정리), keep (보고만)
kind 4개: tool (도구 자체 정리 명령), aged (하위 폴더를 N일 기준으로), browser (로그인 빼고 캐시만), info (보고만)
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from . import shell

TIER_SAFE, TIER_DECIDE, TIER_KEEP = "safe", "decide", "keep"


@dataclass(frozen=True)
class Location:
    key: str
    label: str
    path: Path
    tier: str
    kind: str
    tool_command: tuple[str, ...] = field(default=())
    note: str = ""
    # 폴더 전체가 정리 대상인지 (False: 일부만 정리 > 합계에서 제외, 실제 값은 해당 명령의 dry-run)
    is_whole_folder_reclaimable: bool = True


def _home(*parts: str) -> Path:
    return Path.home().joinpath(*parts)


def _env_path(variable: str, *parts: str) -> Path:
    base = os.environ.get(variable)
    return Path(base).joinpath(*parts) if base else Path.home().joinpath("__missing__", variable)


def _common() -> list[Location]:
    # 세 OS 공통 (홈 기준 경로)
    return [
        Location("gradle-caches", "Gradle dependency and transform cache", _home(".gradle", "caches"), TIER_DECIDE, "aged",
                 note="Builds download everything again; never on a blanket clean-up"),
        Location("gradle-wrapper", "Gradle wrapper distributions (old versions)", _home(".gradle", "wrapper", "dists"),
                 TIER_DECIDE, "aged"),
        Location("android-avd", "Android emulator images", _home(".android", "avd"), TIER_DECIDE, "info",
                 note="App data and logins live inside; temporary devices go with pro-launch `device gc`"),
        Location("projectops-browser", "pro-launch browser caches (logins kept)", _home(".projectops", "launch"),
                 TIER_SAFE, "browser", note="Size includes login profiles; `browser` shows the cache part",
                 is_whole_folder_reclaimable=False),
        Location("projectops-backups", "Backups made by this skill", _home(".projectops", "backups", "disk-cleanup"),
                 TIER_KEEP, "info", note="Delete by hand once you no longer need them"),
    ]


def _mac() -> list[Location]:
    developer = _home("Library", "Developer")
    return [
        Location("derived-data", "Xcode DerivedData", developer / "Xcode" / "DerivedData", TIER_DECIDE, "aged",
                 note="Next build of each project compiles from scratch"),
        Location("ios-device-support", "Xcode iOS DeviceSupport (one per iOS version)",
                 developer / "Xcode" / "iOS DeviceSupport", TIER_DECIDE, "aged"),
        Location("xcode-archives", "Xcode archives (needed to symbolicate old crashes)",
                 developer / "Xcode" / "Archives", TIER_DECIDE, "aged"),
        Location("simulators-unavailable", "Simulators for runtimes that are no longer installed",
                 developer / "CoreSimulator" / "Devices", TIER_SAFE, "tool",
                 ("xcrun", "simctl", "delete", "unavailable"), "Size is every simulator; only unavailable ones go",
                 is_whole_folder_reclaimable=False),
        Location("simulator-caches", "Simulator dyld caches", developer / "CoreSimulator" / "Caches", TIER_SAFE, "aged"),
        Location("core-device-fs", "Connected device mount (not local disk)", developer / "CoreDevice" / "DeviceFS",
                 TIER_KEEP, "info", note="Virtual mount; the size is not on this disk"),
        Location("npm", "npm cache", _home(".npm"), TIER_SAFE, "tool", ("npm", "cache", "clean", "--force")),
        Location("uv", "uv cache", _home(".cache", "uv"), TIER_SAFE, "tool", ("uv", "cache", "prune")),
        Location("pip", "pip cache", _home("Library", "Caches", "pip"), TIER_SAFE, "tool", ("pip3", "cache", "purge")),
        Location("yarn", "Yarn cache", _home("Library", "Caches", "Yarn"), TIER_SAFE, "tool", ("yarn", "cache", "clean")),
        Location("cocoapods", "CocoaPods cache", _home("Library", "Caches", "CocoaPods"), TIER_SAFE, "tool",
                 ("pod", "cache", "clean", "--all")),
        Location("homebrew", "Homebrew downloads", _home("Library", "Caches", "Homebrew"), TIER_SAFE, "tool",
                 ("brew", "cleanup", "--prune=all")),
        Location("pub-cache", "Dart/Flutter package cache", _home(".pub-cache"), TIER_DECIDE, "info",
                 note="`flutter pub cache clean` empties it; every project runs pub get again"),
        Location("trash", "Trash", _home(".Trash"), TIER_DECIDE, "info", note="Your own deleted files"),
    ]


def _windows() -> list[Location]:
    return [
        Location("npm", "npm cache", _env_path("LOCALAPPDATA", "npm-cache"), TIER_SAFE, "tool",
                 ("npm", "cache", "clean", "--force")),
        Location("uv", "uv cache", _env_path("LOCALAPPDATA", "uv", "cache"), TIER_SAFE, "tool", ("uv", "cache", "prune")),
        Location("pip", "pip cache", _env_path("LOCALAPPDATA", "pip", "Cache"), TIER_SAFE, "tool",
                 ("python", "-m", "pip", "cache", "purge")),
        Location("yarn", "Yarn cache", _env_path("LOCALAPPDATA", "Yarn", "Cache"), TIER_SAFE, "tool",
                 ("yarn", "cache", "clean")),
        Location("temp", "User temp folder (items older than the threshold)", _env_path("TEMP"), TIER_SAFE, "aged",
                 is_whole_folder_reclaimable=False),
        Location("pub-cache", "Dart/Flutter package cache", _env_path("LOCALAPPDATA", "Pub", "Cache"), TIER_DECIDE, "info",
                 note="`flutter pub cache clean` empties it; every project runs pub get again"),
    ]


def _linux() -> list[Location]:
    return [
        Location("npm", "npm cache", _home(".npm"), TIER_SAFE, "tool", ("npm", "cache", "clean", "--force")),
        Location("uv", "uv cache", _home(".cache", "uv"), TIER_SAFE, "tool", ("uv", "cache", "prune")),
        Location("pip", "pip cache", _home(".cache", "pip"), TIER_SAFE, "tool", ("pip3", "cache", "purge")),
        Location("yarn", "Yarn cache", _home(".cache", "yarn"), TIER_SAFE, "tool", ("yarn", "cache", "clean")),
        Location("pub-cache", "Dart/Flutter package cache", _home(".pub-cache"), TIER_DECIDE, "info"),
    ]


def locations() -> list[Location]:
    if shell.IS_WINDOWS:
        specific = _windows()
    elif shell.IS_MAC:
        specific = _mac()
    else:
        specific = _linux()
    return specific + _common()


def find(key: str) -> Location | None:
    return next((location for location in locations() if location.key == key), None)
