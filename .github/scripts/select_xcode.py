#!/usr/bin/env python3
"""
select_xcode.py

iOS 빌드용 Xcode 선택과 SDK 누락 진단 (#758). Xcode 선택 규칙의 유일한 위치다.

  기본: 러너에 설치된 /Applications/Xcode_*.app 중 가장 높은 정식 버전 (beta 등 제외)
  고정: XCODE_VERSION 값이 있으면 그 버전만 허용, 없으면 설치 목록을 찍고 실패

고정값(26.0)이 낡아 새 SDK 심볼을 쓰는 의존성이 컴파일 오류로 깨진 사고가 원인이다.

  - 커맨드: select | hint
  - 결과: GITHUB_ENV 에 XCODE_SELECTED_VERSION · XCODE_APP_PATH · XCODE_DEVELOPER_DIR · XCODE_LATEST_INSTALLED
  - 출력: 사람용 줄 + 마지막 줄 JSON

사용 예:
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
# Xcode_26.6.app, Xcode_26.0.1.app — 숫자만 있는 이름이 정식 버전 (Xcode_26.1_beta_2.app 은 자동 선택 제외)
_APP_NAME_RE = re.compile(r"^Xcode_(?P<version>.+)\.app$")
_STABLE_VERSION_RE = re.compile(r"^\d+(\.\d+)*$")

# 현재 SDK 에 선언이 없는 심볼을 쓸 때 나는 컴파일 오류 (새 SDK 를 요구하는 의존성)
SDK_MISSING_PATTERNS = [
    re.compile(r"No visible @interface for '[^']+' declares the selector '[^']+'"),
    re.compile(r"Property '[^']+' not found on object of type '[^']+'"),
    re.compile(r"[Vv]alue of type '[^']+' has no member '[^']+'"),
]


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def _scan_apps(applications_dir: str) -> tuple[dict[str, str], dict[str, str]]:
    """Xcode_*.app 스캔 > (실제 앱 {버전: 경로}, 별칭 링크 {버전: 실제 앱 경로})"""
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
        # 러너 이미지의 Xcode_26.6.0.app -> Xcode_26.6.app 같은 링크는 같은 Xcode 라 목록·최신 판정에서 뺀다
        if entry.is_symlink() and target.parent == base.resolve() and _APP_NAME_RE.match(target.name):
            aliases[version] = str(target)
        else:
            real[version] = str(entry)
    # 링크 대상이 목록에 없으면(다른 위치를 가리킴) 별칭이 아니라 설치본으로 취급
    for version, target in list(aliases.items()):
        if target not in real.values():
            real[version] = aliases.pop(version)
    return real, aliases


def list_installed(applications_dir: str) -> dict[str, str]:
    """설치된 Xcode > {버전: 앱 경로} (정식·beta 모두, 별칭 링크 제외)"""
    return _scan_apps(applications_dir)[0]


def sorted_stable_versions(installed: dict[str, str]) -> list[str]:
    """정식 버전만 오름차순 (문자열 정렬이면 26.10 < 26.6 이 되므로 숫자 비교)"""
    stable = [v for v in installed if _STABLE_VERSION_RE.match(v)]
    return sorted(stable, key=_version_key)


def choose_xcode(installed: dict[str, str], pinned: str, aliases: dict[str, str] | None = None) -> dict:
    """고정값 있으면 그 버전, 없으면 최신 정식 버전 > 선택 결과 (실패 시 ok False + 사유)
    aliases: 별칭 링크 이름으로 고정한 경우(XCODE_VERSION=26.6.0)도 받아 주기 위한 {버전: 실제 앱 경로}"""
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

    # 이후 step 이 같은 Xcode 를 보도록 job 환경에 기록 (xcode-select 만으로는 서브프로세스에 전파되지 않음)
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
    """빌드 로그 > SDK 심볼 누락 오류 줄 (없으면 빈 문자열)"""
    for line in log_text.splitlines():
        if any(pattern.search(line) for pattern in SDK_MISSING_PATTERNS):
            return line.strip()
    return ""


def build_hint(error_line: str, selected: str, latest: str) -> str:
    """오류 줄 + 선택·최신 버전 > 사용자용 힌트"""
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
    # 진단 전용이라 종료 코드는 항상 0 (실패 판정은 빌드 step 이 이미 했다)
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
