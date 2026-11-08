"""OS별 정리 후보 위치표: 키 > 경로·단계(tier 3개: safe, decide, keep)·정리 방식(kind 4개: tool, aged, browser, info)
목록 밖 큰 폴더는 discovery.py 가 크기로 찾음 (단계 뜻: references/categories.md)
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


def _env_path(variable: str, *parts: str) -> Path | None:
    base = os.environ.get(variable)
    return Path(base).joinpath(*parts) if base else None


def _first_existing(*candidates: Path | None) -> Path | None:
    """사람마다 설치 위치가 다른 도구: 실제로 있는 첫 경로 (없으면 첫 후보)"""
    present = [candidate for candidate in candidates if candidate is not None]
    return next((candidate for candidate in present if candidate.exists()), present[0] if present else None)


def os_cache_base() -> Path:
    """OS 사용자 캐시 폴더: macOS ~/Library/Caches, Windows %LOCALAPPDATA%, Linux $XDG_CACHE_HOME 또는 ~/.cache"""
    if shell.IS_WINDOWS:
        return _env_path("LOCALAPPDATA") or _home("AppData", "Local")
    if shell.IS_MAC:
        return _home("Library", "Caches")
    return _env_path("XDG_CACHE_HOME") or _home(".cache")


def os_settings_base() -> Path:
    """앱 설정 폴더: macOS ~/Library/Application Support, Windows %APPDATA%, Linux ~/.config"""
    if shell.IS_WINDOWS:
        return _env_path("APPDATA") or _home("AppData", "Roaming")
    if shell.IS_MAC:
        return _home("Library", "Application Support")
    return _env_path("XDG_CONFIG_HOME") or _home(".config")


def _android_sdk() -> Path:
    if shell.IS_WINDOWS:
        default = os_cache_base() / "Android" / "Sdk"
    elif shell.IS_MAC:
        default = _home("Library", "Android", "sdk")
    else:
        default = _home("Android", "Sdk")
    return _first_existing(_env_path("ANDROID_HOME"), _env_path("ANDROID_SDK_ROOT"), default)


def _package_caches() -> list[Location]:
    # 언어·패키지 도구 (세 OS 공통, 위치만 OS별)
    cache = os_cache_base()
    npm_cache = cache / "npm-cache" if shell.IS_WINDOWS else _home(".npm")
    pip_cache = cache / "pip" / "Cache" if shell.IS_WINDOWS else cache / "pip"
    pnpm_store = _first_existing(cache / "pnpm" / "store", _home("Library", "pnpm", "store"),
                                 _home(".local", "share", "pnpm", "store"))
    conda_packages = _first_existing(*(_home(name, "pkgs") for name in ("miniconda3", "anaconda3", "miniforge3", "mambaforge")))
    go_modules = _first_existing(_env_path("GOMODCACHE"), _env_path("GOPATH", "pkg", "mod"), _home("go", "pkg", "mod"))
    python_command = ("python", "-m", "pip") if shell.IS_WINDOWS else ("pip3",)
    # yarn: macOS ~/Library/Caches/Yarn, Windows %LOCALAPPDATA%\Yarn\Cache, Linux ~/.cache/yarn
    yarn_cache = cache / "Yarn" / "Cache" if shell.IS_WINDOWS else cache / ("Yarn" if shell.IS_MAC else "yarn")
    # uv: Windows %LOCALAPPDATA%\uv\cache, macOS·Linux ~/.cache/uv (macOS 도 XDG 위치)
    uv_cache = cache / "uv" / "cache" if shell.IS_WINDOWS else (_env_path("XDG_CACHE_HOME") or _home(".cache")) / "uv"
    return [
        Location("npm", "npm cache", npm_cache, TIER_SAFE, "tool", ("npm", "cache", "clean", "--force")),
        Location("pnpm", "pnpm store (unreferenced packages)", pnpm_store, TIER_SAFE, "tool", ("pnpm", "store", "prune"),
                 is_whole_folder_reclaimable=False),
        Location("yarn", "Yarn cache", yarn_cache, TIER_SAFE, "tool", ("yarn", "cache", "clean")),
        Location("bun", "Bun install cache", _home(".bun", "install", "cache"), TIER_SAFE, "tool", ("bun", "pm", "cache", "rm")),
        Location("pip", "pip cache", pip_cache, TIER_SAFE, "tool", (*python_command, "cache", "purge")),
        Location("uv", "uv cache (unused entries)", uv_cache, TIER_SAFE, "tool",
                 ("uv", "cache", "prune"), is_whole_folder_reclaimable=False),
        Location("conda", "conda package cache", conda_packages, TIER_SAFE, "tool", ("conda", "clean", "--all", "-y"))
        if conda_packages else None,
        Location("go-build", "Go build cache", _first_existing(_env_path("GOCACHE"), cache / "go-build"), TIER_SAFE, "tool",
                 ("go", "clean", "-cache")),
        Location("go-modules", "Go module cache", go_modules, TIER_DECIDE, "tool", ("go", "clean", "-modcache"))
        if go_modules else None,
        Location("cargo-registry", "Rust crates download cache", _home(".cargo", "registry"), TIER_DECIDE, "aged"),
        Location("maven", "Maven local repository", _home(".m2", "repository"), TIER_DECIDE, "aged",
                 note="Builds download every dependency again"),
        Location("gradle-caches", "Gradle dependency and transform cache", _home(".gradle", "caches"), TIER_DECIDE, "aged",
                 note="Builds download everything again; never on a blanket clean-up"),
        Location("gradle-wrapper", "Gradle wrapper distributions (old versions)", _home(".gradle", "wrapper", "dists"),
                 TIER_DECIDE, "aged"),
        Location("pub-cache", "Dart/Flutter package cache",
                 cache / "Pub" / "Cache" if shell.IS_WINDOWS else _home(".pub-cache"), TIER_DECIDE, "info",
                 note="`flutter pub cache clean` empties it; every project runs pub get again"),
    ]


def _editor_and_device_caches() -> list[Location]:
    # IDE·에뮬레이터·projectops 자체 (세 OS 공통)
    cache, settings = os_cache_base(), os_settings_base()
    jetbrains = cache / "JetBrains"
    return [
        Location("jetbrains-caches", "JetBrains IDE caches (one folder per IDE version)", jetbrains, TIER_SAFE, "aged",
                 note="Old IDE versions; the current one re-indexes"),
        Location("vscode-cached-data", "VS Code cached data", settings / "Code" / "CachedData", TIER_SAFE, "aged"),
        Location("vscode-extension-downloads", "VS Code downloaded extension packages",
                 settings / "Code" / "CachedExtensionVSIXs", TIER_SAFE, "aged"),
        Location("dart-analysis-server", "Dart analysis server cache",
                 os_cache_base() / ".dartServer" if shell.IS_WINDOWS else _home(".dartServer"), TIER_SAFE, "aged",
                 note="Rebuilt when an editor opens a Dart project"),
        Location("android-system-images", "Android SDK system images", _android_sdk() / "system-images", TIER_DECIDE, "info",
                 note="Emulators need the image they were made from; remove with the SDK Manager"),
        Location("android-avd", "Android emulator devices", _home(".android", "avd"), TIER_DECIDE, "info",
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
        Location("xcode-previews", "SwiftUI preview data", developer / "Xcode" / "UserData" / "Previews", TIER_SAFE, "aged"),
        Location("simulators-unavailable", "Simulators for runtimes that are no longer installed",
                 developer / "CoreSimulator" / "Devices", TIER_SAFE, "tool",
                 ("xcrun", "simctl", "delete", "unavailable"), "Size is every simulator; only unavailable ones go",
                 is_whole_folder_reclaimable=False),
        Location("simulator-caches", "Simulator dyld caches", developer / "CoreSimulator" / "Caches", TIER_SAFE, "aged"),
        Location("core-device-fs", "Connected device mount (not local disk)", developer / "CoreDevice" / "DeviceFS",
                 TIER_KEEP, "info", note="Virtual mount; the size is not on this disk"),
        Location("cocoapods", "CocoaPods cache", _home("Library", "Caches", "CocoaPods"), TIER_SAFE, "tool",
                 ("pod", "cache", "clean", "--all")),
        Location("homebrew", "Homebrew downloads", _home("Library", "Caches", "Homebrew"), TIER_SAFE, "tool",
                 ("brew", "cleanup", "--prune=all")),
        Location("docker-desktop-disk", "Docker Desktop disk image", _home("Library", "Containers", "com.docker.docker"),
                 TIER_KEEP, "info", note="Shrinks only after `docker` clean-up and Docker Desktop reclaims space"),
        Location("trash", "Trash", _home(".Trash"), TIER_DECIDE, "info", note="Your own deleted files"),
    ]


def _windows() -> list[Location]:
    local = os_cache_base()
    return [
        Location("temp", "User temp folder (items older than the threshold)", _env_path("TEMP") or local / "Temp",
                 TIER_SAFE, "aged", is_whole_folder_reclaimable=False),
        Location("crash-dumps", "Crash dumps", local / "CrashDumps", TIER_SAFE, "aged"),
        Location("docker-desktop-disk", "Docker Desktop WSL disk", local / "Docker", TIER_KEEP, "info",
                 note="Shrinks only after `docker` clean-up and compacting the WSL disk"),
        Location("store-app-data", "Store app data, including WSL distributions", local / "Packages", TIER_KEEP, "info",
                 note="Linux installs with their own files; manage with `wsl --list`"),
    ]


def _linux() -> list[Location]:
    return [
        Location("thumbnails", "Thumbnail cache", os_cache_base() / "thumbnails", TIER_SAFE, "aged"),
        Location("trash", "Trash", _home(".local", "share", "Trash"), TIER_DECIDE, "info", note="Your own deleted files"),
    ]


def locations() -> list[Location]:
    if shell.IS_WINDOWS:
        specific = _windows()
    elif shell.IS_MAC:
        specific = _mac()
    else:
        specific = _linux()
    return [location for location in specific + _package_caches() + _editor_and_device_caches()
            if location is not None and location.path is not None]


def find(key: str) -> Location | None:
    return next((location for location in locations() if location.key == key), None)
