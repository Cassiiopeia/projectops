#!/usr/bin/env python3
"""React Native Expo build helpers shared by the PROJECT-REACT-NATIVE-EXPO-* workflows (#1240).

Commands (stdlib only, results go to $GITHUB_OUTPUT and stdout as JSON):
  detect           package manager, install command, lockfile and check tools of the app folder
  read-config      resolved app config (expo config, else app.json): Android package, iOS bundle ID, name
  set-version      version values > app.json (expo.version, android.versionCode, ios.appleTeamId)
  ios-prepare      after prebuild: workspace and scheme, Info.plist numbers to build variables
  ios-signing      provisioning profile facts > ExportOptions.plist + Fastfile (deploy lane) + Gemfile
"""
from __future__ import annotations

import argparse
import json
import os
import plistlib
import subprocess
import sys
from pathlib import Path

# Lockfile > package manager (first match wins, same order as Expo CLI detection)
LOCKFILE_MANAGERS = (
    ("bun.lockb", "bun"), ("bun.lock", "bun"),
    ("pnpm-lock.yaml", "pnpm"), ("yarn.lock", "yarn"), ("package-lock.json", "npm"),
)
INSTALL_COMMANDS = {
    "npm": "npm ci",
    "yarn": "corepack enable && yarn install --immutable || yarn install --frozen-lockfile",
    "pnpm": "corepack enable && pnpm install --frozen-lockfile",
    "bun": "npm install -g bun && bun install --frozen-lockfile",
}
# setup-node cache supports these three only
SETUP_NODE_CACHE_MANAGERS = ("npm", "yarn", "pnpm")
ESLINT_CONFIG_NAMES = (
    "eslint.config.js", "eslint.config.mjs", "eslint.config.cjs", "eslint.config.ts",
    ".eslintrc", ".eslintrc.js", ".eslintrc.cjs", ".eslintrc.json", ".eslintrc.yml", ".eslintrc.yaml",
)
# Info.plist search skips generated and dependency folders
IGNORED_IOS_DIRS = {"Pods", "build", "DerivedData", "node_modules"}
BUILD_NUMBER_VARIABLE = "$(CURRENT_PROJECT_VERSION)"
MARKETING_VERSION_VARIABLE = "$(MARKETING_VERSION)"


class ExpoAppError(Exception):
    """Failure with a reason line for ::error and the JSON result"""


def write_github_output(pairs: dict) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as handle:
        for key, value in pairs.items():
            handle.write(f"{key}={'' if value is None else value}\n")


def emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False))


def read_json_file(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as error:
        raise ExpoAppError(f"cannot read {path.as_posix()}: {error}") from error
    if not isinstance(data, dict):
        raise ExpoAppError(f"{path.as_posix()} is not a JSON object")
    return data


def write_json_file(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def detect_package_manager(app_root: Path, repo_root: Path) -> tuple[str, Path | None]:
    """Lockfile in the app folder, then up to the repo root (workspaces) > (manager, lockfile)"""
    folder = app_root.resolve()
    stop = repo_root.resolve()
    while True:
        for name, manager in LOCKFILE_MANAGERS:
            candidate = folder / name
            if candidate.is_file():
                return manager, candidate
        if folder == stop or folder.parent == folder:
            return "npm", None
        folder = folder.parent


def has_dependency(package: dict, name: str) -> bool:
    return any(name in (package.get(field) or {}) for field in ("dependencies", "devDependencies"))


def command_detect(args: argparse.Namespace) -> int:
    app_root = Path(args.app_root)
    package_path = app_root / "package.json"
    package = read_json_file(package_path)
    if not has_dependency(package, "expo"):
        print(f"::warning::{package_path.as_posix()} has no expo dependency. Check APP_ROOT in the workflow env.")
    manager, lockfile = detect_package_manager(app_root, Path(args.repo_root))
    scripts = package.get("scripts") or {}
    repo_root = Path(args.repo_root).resolve()
    result = {
        "package_manager": manager,
        "install_command": INSTALL_COMMANDS[manager] if lockfile else "npm install",
        "setup_node_cache": manager if lockfile and manager in SETUP_NODE_CACHE_MANAGERS else "",
        "lockfile": lockfile.resolve().relative_to(repo_root).as_posix() if lockfile else "",
        "has_typescript": str((app_root / "tsconfig.json").is_file()).lower(),
        "has_lint_script": str("lint" in scripts).lower(),
        "has_eslint_config": str(any((app_root / name).is_file() for name in ESLINT_CONFIG_NAMES)).lower(),
        "has_jest": str(has_dependency(package, "jest") or has_dependency(package, "jest-expo")).lower(),
    }
    if not lockfile:
        print("::warning::No lockfile found, installing with npm install (commit a lockfile for repeatable builds).")
    write_github_output(result)
    emit({"ok": True, **result})
    return 0


def resolve_app_config(app_root: Path) -> dict:
    """`expo config` (covers app.config.js) > fallback app.json"""
    try:
        completed = subprocess.run(
            ["npx", "--no-install", "expo", "config", "--json", "--type", "public"],
            cwd=app_root, capture_output=True, encoding="utf-8", errors="replace", timeout=180,
        )
        if completed.returncode == 0:
            data = json.loads(completed.stdout[completed.stdout.find("{"):])
            if isinstance(data, dict):
                return data
        print(f"::warning::expo config failed ({completed.returncode}), reading app.json instead: "
              f"{(completed.stderr or '').strip().splitlines()[-1:] or ''}")
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        print(f"::warning::expo config failed, reading app.json instead: {error}")
    app_json = app_root / "app.json"
    if not app_json.is_file():
        raise ExpoAppError(f"no app config: {app_json.as_posix()} is missing and expo config failed")
    data = read_json_file(app_json)
    return data.get("expo") if isinstance(data.get("expo"), dict) else data


def command_read_config(args: argparse.Namespace) -> int:
    config = resolve_app_config(Path(args.app_root))
    android = config.get("android") or {}
    ios = config.get("ios") or {}
    result = {
        "app_name": config.get("name", ""),
        "app_slug": config.get("slug", ""),
        "android_package": android.get("package", ""),
        "ios_bundle_id": ios.get("bundleIdentifier", ""),
        "app_version": config.get("version", ""),
    }
    write_github_output(result)
    emit({"ok": True, **result})
    return 0


def command_set_version(args: argparse.Namespace) -> int:
    app_json = Path(args.app_root) / "app.json"
    if not app_json.is_file():
        # app.config.js only: values cannot be written, the build keeps the config's own values
        print(f"::warning::{app_json.as_posix()} is missing, so version values were not written. "
              "Read them from app.json in app.config.js, or add an app.json.")
        emit({"ok": True, "written": False})
        return 0
    data = read_json_file(app_json)
    expo = data.setdefault("expo", {})
    if not isinstance(expo, dict):
        raise ExpoAppError(f"'expo' in {app_json.as_posix()} is not an object")
    changes = {}
    if args.version:
        expo["version"] = args.version
        changes["version"] = args.version
    if args.android_version_code is not None:
        expo.setdefault("android", {})["versionCode"] = args.android_version_code
        changes["android.versionCode"] = args.android_version_code
    if args.apple_team_id:
        expo.setdefault("ios", {})["appleTeamId"] = args.apple_team_id
        changes["ios.appleTeamId"] = args.apple_team_id
    write_json_file(app_json, data)
    emit({"ok": True, "written": True, "changes": changes})
    return 0


def find_app_info_plists(ios_dir: Path, scheme: str) -> list[Path]:
    """Main app Info.plist (ios/<scheme>/Info.plist) first, then other target plists"""
    main = ios_dir / scheme / "Info.plist"
    found = [main] if main.is_file() else []
    for path in sorted(ios_dir.glob("*/Info.plist")):
        if path.parent.name in IGNORED_IOS_DIRS or path in found or path.parent.name.endswith("Tests"):
            continue
        found.append(path)
    return found


def command_ios_prepare(args: argparse.Namespace) -> int:
    ios_dir = Path(args.app_root) / "ios"
    workspaces = sorted(p for p in ios_dir.glob("*.xcworkspace") if p.is_dir())
    if not workspaces:
        raise ExpoAppError(f"no .xcworkspace in {ios_dir.as_posix()} — did expo prebuild and pod install run?")
    workspace = workspaces[0]
    scheme = workspace.stem
    # Numbers come from xcodebuild overrides (ios_release.py), so the plists must read the build variables
    plists = find_app_info_plists(ios_dir, scheme)
    if not plists:
        raise ExpoAppError(f"no Info.plist under {ios_dir.as_posix()}/{scheme}")
    for path in plists:
        with path.open("rb") as handle:
            info = plistlib.load(handle)
        info["CFBundleVersion"] = BUILD_NUMBER_VARIABLE
        info["CFBundleShortVersionString"] = MARKETING_VERSION_VARIABLE
        with path.open("wb") as handle:
            plistlib.dump(info, handle)
    result = {"ios_workspace": workspace.name, "ios_scheme": scheme,
              "info_plists": ",".join(p.relative_to(ios_dir).as_posix() for p in plists)}
    env_path = os.environ.get("GITHUB_ENV")
    if env_path:
        with open(env_path, "a", encoding="utf-8") as handle:
            handle.write(f"IOS_WORKSPACE={workspace.name}\nIOS_SCHEME={scheme}\n")
    write_github_output(result)
    emit({"ok": True, **result})
    return 0


def read_provisioning_profile(profile_path: Path) -> dict:
    """Signed .mobileprovision > plist dict (security cms on macOS, else the embedded XML)"""
    try:
        completed = subprocess.run(["security", "cms", "-D", "-i", str(profile_path)],
                                   capture_output=True, timeout=60)
        if completed.returncode == 0 and completed.stdout:
            return plistlib.loads(completed.stdout)
    except (OSError, subprocess.TimeoutExpired, ValueError):
        pass
    raw = profile_path.read_bytes()
    start, end = raw.find(b"<?xml"), raw.find(b"</plist>")
    if start < 0 or end < 0:
        raise ExpoAppError(f"cannot read provisioning profile {profile_path.as_posix()}")
    return plistlib.loads(raw[start:end + len(b"</plist>")])


FASTFILE = """default_platform(:ios)

# Generated by expo_app.py ios-signing (projectops). ios/ is regenerated by expo prebuild on every run.
platform :ios do
  desc "TestFlight upload of the IPA built by ios_release.py"
  lane :deploy do
    api_key = app_store_connect_api_key(
      key_id: ENV["APP_STORE_CONNECT_API_KEY_ID"],
      issuer_id: ENV["APP_STORE_CONNECT_ISSUER_ID"],
      key_filepath: ENV["API_KEY_PATH"]
    )
    pilot(
      api_key: api_key,
      app_identifier: ENV["APP_IDENTIFIER"],
      ipa: ENV["IPA_PATH"],
      changelog: ENV["RELEASE_NOTES"],
      skip_waiting_for_build_processing: true,
      distribute_external: false,
      notify_external_testers: false,
      uses_non_exempt_encryption: false
    )
  end
end
"""

# fastlane 2.240+ reads the Xcode 27 altool upload result correctly (fastlane#30586)
GEMFILE = 'source "https://rubygems.org"\ngem "fastlane", ">= 2.240"\ngem "multi_json"\ngem "cocoapods", "~> 1.15"\n'


def command_ios_signing(args: argparse.Namespace) -> int:
    profile = read_provisioning_profile(Path(args.profile))
    team_ids = profile.get("TeamIdentifier") or []
    team_id = team_ids[0] if team_ids else ""
    profile_name = profile.get("Name", "")
    profile_uuid = profile.get("UUID", "")
    if not (team_id and profile_name):
        raise ExpoAppError("provisioning profile has no TeamIdentifier or Name")
    entitlements = profile.get("Entitlements") or {}
    application_identifier = str(entitlements.get("application-identifier", ""))
    # Profile app ID (TEAMID.bundle.id) <-> app bundle ID
    profile_bundle = application_identifier.split(".", 1)[1] if "." in application_identifier else ""
    if profile_bundle and profile_bundle != "*" and args.bundle_id and profile_bundle != args.bundle_id:
        raise ExpoAppError(f"provisioning profile is for {profile_bundle}, but the app bundle ID is {args.bundle_id}")

    ios_dir = Path(args.app_root) / "ios"
    export_options = {
        "method": "app-store-connect",
        "teamID": team_id,
        "provisioningProfiles": {args.bundle_id: profile_name},
        "signingStyle": "manual",
        "signingCertificate": "Apple Distribution",
        "manageAppVersionAndBuildNumber": False,
        "stripSwiftSymbols": True,
        "uploadSymbols": True,
    }
    with (ios_dir / "ExportOptions.plist").open("wb") as handle:
        plistlib.dump(export_options, handle)
    (ios_dir / "fastlane").mkdir(parents=True, exist_ok=True)
    (ios_dir / "fastlane" / "Fastfile").write_text(FASTFILE, encoding="utf-8")
    (ios_dir / "Gemfile").write_text(GEMFILE, encoding="utf-8")
    result = {"team_id": team_id, "profile_name": profile_name, "profile_uuid": profile_uuid}
    write_github_output(result)
    emit({"ok": True, **result})
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="React Native Expo build helpers (projectops)")
    sub = parser.add_subparsers(dest="command", required=True)

    detect = sub.add_parser("detect", help="package manager, install command and check tools")
    detect.add_argument("--app-root", default=".")
    detect.add_argument("--repo-root", default=".")
    detect.set_defaults(handler=command_detect)

    read_config = sub.add_parser("read-config", help="resolved app config facts")
    read_config.add_argument("--app-root", default=".")
    read_config.set_defaults(handler=command_read_config)

    set_version = sub.add_parser("set-version", help="write version values into app.json")
    set_version.add_argument("--app-root", default=".")
    set_version.add_argument("--version", default="")
    set_version.add_argument("--android-version-code", type=int, default=None)
    set_version.add_argument("--apple-team-id", default="")
    set_version.set_defaults(handler=command_set_version)

    ios_prepare = sub.add_parser("ios-prepare", help="workspace, scheme and Info.plist build variables after prebuild")
    ios_prepare.add_argument("--app-root", default=".")
    ios_prepare.set_defaults(handler=command_ios_prepare)

    ios_signing = sub.add_parser("ios-signing", help="ExportOptions.plist, Fastfile and Gemfile from the profile")
    ios_signing.add_argument("--app-root", default=".")
    ios_signing.add_argument("--profile", required=True, help="path of the .mobileprovision file")
    ios_signing.add_argument("--bundle-id", required=True)
    ios_signing.set_defaults(handler=command_ios_signing)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.handler(args)
    except ExpoAppError as error:
        print(f"::error::[expo app] {args.command} failed : {error}")
        emit({"ok": False, "command": args.command, "reason": str(error)})
        return 1


if __name__ == "__main__":
    sys.exit(main())
