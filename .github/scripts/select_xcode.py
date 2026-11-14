#!/usr/bin/env python3
"""
select_xcode.py

Xcode selection for iOS builds and missing-SDK diagnosis (#758). The only place for Xcode selection rules.

  Default: the highest stable version among /Applications/Xcode_*.app on the runner (beta etc. excluded)
  Pinned: with XCODE_VERSION set, only that version is allowed; if missing, print the installed list and fail

Caused by an incident where a stale pinned value (26.0) broke dependencies using new SDK symbols with compile errors.

  - Commands: select | hint
  - Result: XCODE_SELECTED_VERSION, XCODE_APP_PATH, XCODE_DEVELOPER_DIR, XCODE_LATEST_INSTALLED in GITHUB_ENV
  - Output: human-readable lines + JSON on the last line

Usage:
  XCODE_VERSION="" python3 select_xcode.py select --apply
  python3 select_xcode.py hint --log "$RUNNER_TEMP/flutter-ios-build.log"
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

DEFAULT_APPLICATIONS_DIR = "/Applications"
# Xcode_26.6.app, Xcode_26.0.1.app — names with only digits are stable versions (Xcode_26.1_beta_2.app is excluded from auto-selection)
_APP_NAME_RE = re.compile(r"^Xcode_(?P<version>.+)\.app$")
_STABLE_VERSION_RE = re.compile(r"^\d+(\.\d+)*$")

# Compile error raised when using a symbol not declared in the current SDK (a dependency needing a newer SDK)
SDK_MISSING_PATTERNS = [
    re.compile(r"No visible @interface for '[^']+' declares the selector '[^']+'"),
    re.compile(r"Property '[^']+' not found on object of type '[^']+'"),
    re.compile(r"[Vv]alue of type '[^']+' has no member '[^']+'"),
]


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def _scan_apps(applications_dir: str) -> tuple[dict[str, str], dict[str, str]]:
    """Scan Xcode_*.app > (real apps {version: path}, alias links {version: real app path})"""
    real: dict[str, str] = {}
    aliases: dict[str, str] = {}
    base = Path(applications_dir)
    if not base.is_dir():
        return real, aliases
    for entry in base.iterdir():
        match = _APP_NAME_RE.match(entry.name)
        if not match:
            continue
        version = match.group("version")
        target = entry.resolve()
        # Links such as Xcode_26.6.0.app -> Xcode_26.6.app on the runner image are the same Xcode, so drop them from the list and the latest check
        if entry.is_symlink() and target.parent == base.resolve() and _APP_NAME_RE.match(target.name):
            aliases[version] = str(target)
        else:
            real[version] = str(entry)
    # If the link target is not in the list (points elsewhere), treat it as an install, not an alias
    for version, target in list(aliases.items()):
        if target not in real.values():
            real[version] = aliases.pop(version)
    return real, aliases


def list_installed(applications_dir: str) -> dict[str, str]:
    """Installed Xcode > {version: app path} (stable and beta, alias links excluded)"""
    return _scan_apps(applications_dir)[0]


def sorted_stable_versions(installed: dict[str, str]) -> list[str]:
    """Stable versions only, ascending (numeric compare; string sort would put 26.10 < 26.6)"""
    stable = [v for v in installed if _STABLE_VERSION_RE.match(v)]
    return sorted(stable, key=_version_key)


def choose_xcode(installed: dict[str, str], pinned: str, aliases: dict[str, str] | None = None) -> dict:
    """Pinned version if set, else the latest stable > selection result (on failure ok False + reason)
    aliases: {version: real app path} so a pin using an alias link name (XCODE_VERSION=26.6.0) is accepted too"""
    aliases = aliases or {}
    stable = sorted_stable_versions(installed)
    latest = stable[-1] if stable else ""
    all_versions = sorted(installed, key=lambda v: (_version_key(v) if _STABLE_VERSION_RE.match(v) else (), v))
    base = {"pinned": pinned, "latest_installed": latest, "installed": all_versions}

    if pinned:
        if pinned not in installed and pinned in aliases:
            installed = {**installed, pinned: aliases[pinned]}
        if pinned not in installed:
            return {**base, "ok": False, "reason": "pinned_not_installed",
                    "summary": f"Xcode {pinned} (XCODE_VERSION) is not installed on this runner. "
                               f"Installed: {', '.join(all_versions) or 'none'}. "
                               "Set XCODE_VERSION to one of these, or leave it empty to use the latest."}
        version, source = pinned, "pinned"
    else:
        if not latest:
            return {**base, "ok": False, "reason": "none_installed",
                    "summary": f"No Xcode_<version>.app found in {DEFAULT_APPLICATIONS_DIR}. "
                               "Use a macOS runner image that ships Xcode."}
        version, source = latest, "latest"

    app_path = installed[version]
    return {**base, "ok": True, "version": version, "source": source, "app_path": app_path,
            "developer_dir": f"{app_path}/Contents/Developer",
            "summary": f"Using Xcode {version} ({'pinned by XCODE_VERSION' if source == 'pinned' else 'latest installed'})."}


def _append(path_env: str, lines: list[str]) -> None:
    path = os.environ.get(path_env)
    if not path:
        return
    with open(path, "a", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def command_select(args: argparse.Namespace) -> int:
    pinned = (args.pinned if args.pinned is not None else os.environ.get("XCODE_VERSION", "")).strip()
    real, aliases = _scan_apps(args.applications_dir)
    result = choose_xcode(real, pinned, aliases)
    if not result["ok"]:
        print(f"::error title=Xcode selection failed::{result['summary']}")
        print(json.dumps(result, ensure_ascii=False))
        return 1

    # Record in the job env so later steps see the same Xcode (xcode-select alone does not propagate to subprocesses)
    _append("GITHUB_ENV", [
        f"XCODE_SELECTED_VERSION={result['version']}",
        f"XCODE_APP_PATH={result['app_path']}",
        f"XCODE_DEVELOPER_DIR={result['developer_dir']}",
        f"XCODE_LATEST_INSTALLED={result['latest_installed']}",
    ])
    if args.apply:
        subprocess.run(["sudo", "xcode-select", "-s", result["developer_dir"]], check=True)
    print(f"::notice title=Xcode {result['version']}::{result['summary']} Installed: {', '.join(result['installed'])}")
    print(json.dumps(result, ensure_ascii=False))
    return 0


def find_sdk_missing_error(log_text: str) -> str:
    """Build log > missing-SDK-symbol error line (empty string if none)"""
    for line in log_text.splitlines():
        if any(pattern.search(line) for pattern in SDK_MISSING_PATTERNS):
            return line.strip()
    return ""


def build_hint(error_line: str, selected: str, latest: str) -> str:
    """Error line + selected/latest version > user hint"""
    head = f"The iOS build failed on an SDK symbol this Xcode does not declare: {error_line[:300]}"
    if selected and latest and selected != latest:
        return (f"{head} Xcode may be too old: this run used Xcode {selected}, "
                f"the latest installed on the runner is {latest}. "
                "Clear XCODE_VERSION (empty = latest) or raise it.")
    if selected:
        return (f"{head} Xcode may be too old: this run used Xcode {selected}, "
                "which is already the latest installed on this runner. "
                "A newer macOS runner image (runs-on) may be needed.")
    return f"{head} Xcode may be too old for a dependency. Check the Xcode version used by this job."


def command_hint(args: argparse.Namespace) -> int:
    log_path = Path(args.log)
    log_text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.is_file() else ""
    error_line = find_sdk_missing_error(log_text)
    if not error_line:
        print(json.dumps({"ok": True, "matched": False, "summary": "No SDK-missing error found."}))
        return 0
    selected = os.environ.get("XCODE_SELECTED_VERSION", "")
    latest = os.environ.get("XCODE_LATEST_INSTALLED", "")
    hint = build_hint(error_line, selected, latest)
    # Diagnosis only, so the exit code is always 0 (the build step already decided failure)
    print(f"::warning title=Xcode may be too old::{hint}")
    _append("GITHUB_STEP_SUMMARY", ["### Xcode may be too old", "", hint])
    print(json.dumps({"ok": True, "matched": True, "error_line": error_line,
                      "selected": selected, "latest_installed": latest, "summary": hint}, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Select Xcode for iOS builds and diagnose SDK-missing errors")
    sub = parser.add_subparsers(dest="command", required=True)

    select = sub.add_parser("select", help="pick the Xcode to use (XCODE_VERSION env pins, empty = latest)")
    select.add_argument("--applications-dir", default=DEFAULT_APPLICATIONS_DIR)
    select.add_argument("--pinned", default=None, help="overrides the XCODE_VERSION env")
    select.add_argument("--apply", action="store_true", help="run sudo xcode-select -s on the result")
    select.set_defaults(handler=command_select)

    hint = sub.add_parser("hint", help="print a hint when a build log shows SDK-missing errors")
    hint.add_argument("--log", required=True)
    hint.set_defaults(handler=command_hint)

    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
