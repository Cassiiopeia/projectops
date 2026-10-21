#!/usr/bin/env python3
"""
firebase_config_files.py

Firebase 설정 파일 복원과 누락 진단 (#785). 플랫폼별 파일 위치·Secret 이름의 유일한 위치다.

  android: Secret GOOGLE_SERVICES_JSON      > {APP_ROOT}/android/app/google-services.json
  ios:     Secret GOOGLE_SERVICE_INFO_PLIST > {APP_ROOT}/ios/Runner/GoogleService-Info.plist (원문 또는 base64)

  - Secret 이 있으면 파일로 쓴다 (레포에 커밋된 파일이 있어도 Secret 이 이긴다)
  - Secret 이 없으면 아무것도 쓰지 않는다 (커밋된 파일을 빈 파일로 덮어쓰지 않게)
  - 그래도 파일이 없는데 프로젝트가 Firebase 설정을 참조하면 ::error 로 원인과 해결 방법을 남긴다
    (빌드는 어차피 그 파일에서 실패한다 — 이 스크립트는 실패시키지 않고 이유만 알린다)
  - 파일 내용은 어떤 경우에도 출력하지 않는다

사용 예:
  GOOGLE_SERVICES_JSON="$SECRET" python3 firebase_config_files.py restore --platform android --app-root .
"""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
import re
import sys
from pathlib import Path

# 플랫폼 > (Secret 이름, APP_ROOT 기준 파일 경로)
PLATFORMS = {
    "android": ("GOOGLE_SERVICES_JSON", "android/app/google-services.json"),
    "ios": ("GOOGLE_SERVICE_INFO_PLIST", "ios/Runner/GoogleService-Info.plist"),
}
# 프로젝트가 Firebase 설정 파일을 요구한다는 근거 (파일 > 패턴)
_ANDROID_REFERENCES = (
    ("android/app/build.gradle", re.compile(r"com\.google\.gms\.google-services")),
    ("android/app/build.gradle.kts", re.compile(r"com\.google\.gms\.google-services")),
    ("android/settings.gradle", re.compile(r"com\.google\.gms\.google-services")),
    ("android/settings.gradle.kts", re.compile(r"com\.google\.gms\.google-services")),
)
_IOS_REFERENCES = (
    ("ios/Runner.xcodeproj/project.pbxproj", re.compile(r"GoogleService-Info\.plist")),
)


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def referencing_files(platform: str, app_root: Path) -> list[str]:
    """프로젝트 안에서 Firebase 설정 파일을 요구하는 곳 (없으면 빈 목록)"""
    references = _ANDROID_REFERENCES if platform == "android" else _IOS_REFERENCES
    return [name for name, pattern in references if pattern.search(_read(app_root / name))]


def decode_plist(value: str) -> str:
    """plist Secret > 원문 (XML 이면 그대로, 아니면 base64 로 풀어 본다)"""
    stripped = value.strip()
    if stripped.startswith("<"):
        return value
    try:
        decoded = base64.b64decode(stripped, validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return value
    return decoded if decoded.lstrip().startswith("<") else value


def restore(platform: str, app_root: Path, secret_value: str) -> dict:
    """Secret > 파일 (없으면 건너뜀) > 결과 {action: written|skipped, missing_but_referenced}"""
    secret_name, relative = PLATFORMS[platform]
    target = app_root / relative
    if secret_value.strip():
        content = decode_plist(secret_value) if platform == "ios" else secret_value
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content if content.endswith("\n") else content + "\n", encoding="utf-8")
        action = "written"
    else:
        action = "skipped"
    references = [] if target.is_file() else referencing_files(platform, app_root)
    return {"ok": True, "platform": platform, "secret": secret_name, "path": relative, "action": action,
            "exists": target.is_file(), "referenced_by": references}


def message_for(result: dict) -> tuple[str, str]:
    """결과 > (annotation 종류, 사용자 문구)"""
    if result["action"] == "written":
        return "", f"{result['path']} restored from the {result['secret']} secret."
    if result["referenced_by"]:
        return "error", (
            f"{result['path']} is missing but {', '.join(result['referenced_by'])} needs it, so the build will fail. "
            f"Add the file's content as the repository secret {result['secret']} "
            "(Settings > Secrets and variables > Actions), or commit the file.")
    if result["exists"]:
        return "", f"{result['secret']} secret not set, using the committed {result['path']}."
    return "", f"{result['secret']} secret not set and the project does not need {result['path']}, skipping."


def command_restore(args: argparse.Namespace) -> int:
    secret_name = PLATFORMS[args.platform][0]
    result = restore(args.platform, Path(args.app_root), os.environ.get(secret_name, ""))
    level, text = message_for(result)
    print(f"::{level} title=Missing Firebase config::{text}" if level else text)
    print(json.dumps({**result, "summary": text}, ensure_ascii=False))
    # 진단 전용: 누락이어도 0 (빌드 step 이 실제 오류로 실패한다)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Restore Firebase config files from secrets and explain missing ones")
    sub = parser.add_subparsers(dest="command", required=True)
    restore_parser = sub.add_parser("restore", help="write the platform's Firebase config file when its secret is set")
    restore_parser.add_argument("--platform", choices=sorted(PLATFORMS), required=True)
    restore_parser.add_argument("--app-root", default=".", help="Flutter project root (APP_ROOT)")
    restore_parser.set_defaults(handler=command_restore)
    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
