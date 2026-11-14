#!/usr/bin/env python3
"""
firebase_config_files.py

Restore Firebase config files and diagnose missing ones (#785). The only place for per-platform file locations and Secret names.

  android: Secret GOOGLE_SERVICES_JSON      > {APP_ROOT}/android/app/google-services.json
  ios:     Secret GOOGLE_SERVICE_INFO_PLIST > {APP_ROOT}/ios/Runner/GoogleService-Info.plist (raw or base64)

  - With the Secret, write the file (the Secret wins even if the repo has a committed file)
  - Without the Secret, write nothing (so a committed file is not overwritten with an empty one)
  - If the file is still missing but the project references the Firebase config, leave the cause and fix as ::error
    (the build fails on that file anyway — this script does not fail, it only explains why)
  - File contents are never printed

Usage:
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

# platform > (Secret name, file path relative to APP_ROOT)
PLATFORMS = {
    "android": ("GOOGLE_SERVICES_JSON", "android/app/google-services.json"),
    "ios": ("GOOGLE_SERVICE_INFO_PLIST", "ios/Runner/GoogleService-Info.plist"),
}
# Evidence that the project needs the Firebase config file (file > pattern)
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
    """Places in the project that require the Firebase config file (empty list if none)"""
    references = _ANDROID_REFERENCES if platform == "android" else _IOS_REFERENCES
    return [name for name, pattern in references if pattern.search(_read(app_root / name))]


def decode_plist(value: str) -> str:
    """plist Secret > raw (XML as is, otherwise try base64 decoding)"""
    stripped = value.strip()
    if stripped.startswith("<"):
        return value
    try:
        decoded = base64.b64decode(stripped, validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return value
    return decoded if decoded.lstrip().startswith("<") else value


def restore(platform: str, app_root: Path, secret_value: str) -> dict:
    """Secret > file (skipped if missing) > result {action: written|skipped, missing_but_referenced}"""
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
    """Result > (annotation kind, user text)"""
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
    # Diagnosis only: 0 even when missing (the build step fails with the real error)
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
