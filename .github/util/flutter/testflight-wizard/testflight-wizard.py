#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ===================================================================
# Flutter iOS TestFlight initialization script
# ===================================================================
#
# This script automatically configures the build environment
# for iOS TestFlight deploys in a Flutter project.
#
# ★ Wizard-first architecture ★
# - This wizard generates every config file
# - GitHub Actions workflows use the generated files as is
# - No edits needed after the initial setup (one-time setup)
#
# Build pipeline:
#   1. flutter build ios --no-codesign (Flutter build)
#   2. xcodebuild archive (create the Xcode archive)
#   3. xcodebuild -exportArchive (create the IPA)
#   4. fastlane upload_testflight (TestFlight upload)
#
# Usage:
#   python3 testflight-wizard.py setup PROJECT_PATH BUNDLE_ID TEAM_ID PROFILE_NAME [USES_ENCRYPTION]
#
# Examples:
#   python3 testflight-wizard.py setup /path/to/project com.example.myapp ABC1234DEF "MyApp Distribution"
#   python3 testflight-wizard.py setup /path/to/project com.example.myapp ABC1234DEF "MyApp Distribution" false
#
# Files created/modified:
#   - ios/Gemfile                    (Fastlane dependencies)
#   - ios/fastlane/Fastfile          (TestFlight upload settings) ★ core
#   - ios/ExportOptions.plist        (IPA export settings) ★ core
#   - ios/Runner.xcodeproj           (Manual Signing patch) ★ core
#   - ios/Runner/Info.plist          (encryption setting)
#
# Note: a 1:1 Python port of the old bash script (logic/text/exit codes preserved).
#       sed-based substitutions became string/regex substitutions, and patterns that sed
#       ran line by line ([^"]* etc.) were kept equivalent as newline-free patterns.
# ===================================================================

import argparse
import os
import re
import shutil
import sys

# Force UTF-8 so Korean/emoji output does not break on cp949 consoles, etc.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

# Color definitions (same palette as the old sh)
RED = "\033[0;31m"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
BLUE = "\033[0;34m"
CYAN = "\033[0;36m"
NC = "\033[0m"  # No Color


def _enable_ansi():
    """Try enabling ANSI on the Windows console. Prints without color on failure."""
    global RED, GREEN, YELLOW, BLUE, CYAN, NC
    if os.name != "nt":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        ok = False
        for std_handle in (-11, -12):  # STD_OUTPUT_HANDLE, STD_ERROR_HANDLE
            handle = kernel32.GetStdHandle(std_handle)
            mode = ctypes.c_uint32()
            if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                if kernel32.SetConsoleMode(handle, mode.value | 0x0004):
                    ok = True
        if not ok:
            raise OSError("SetConsoleMode failed")
    except Exception:
        RED = GREEN = YELLOW = BLUE = CYAN = NC = ""


_enable_ansi()

# Global settings (same role as the sh global variables)
PROJECT_PATH = ""
BUNDLE_ID = ""
TEAM_ID = ""
PROFILE_NAME = ""
USES_NON_EXEMPT_ENCRYPTION = "false"
TEMPLATE_DIR = ""

# File IO: surrogateescape + no newline conversion (newline="") to preserve bytes
_READ_KWARGS = _WRITE_KWARGS = dict(encoding="utf-8", errors="surrogateescape", newline="")

# >>> 공통 블록: 쓰기 게이트 (identical in testflight/playstore — compared by _shared/check-consistency.py)
# Every primitive that changes files (write, copy, move, delete, mkdir) goes through the gates below.
# With DRY_RUN the disk is untouched and only "what would happen" is printed.
#
# ⚠️ Why the overlay is needed
#   Some steps "write → read back to verify"; skipping only the write makes later steps read stale content,
#   take a different path than a real run and fail falsely. So in dry-run the content that
#   would have been written is kept in memory and read_text checks it first.
# Encoding/newline handling differs per wizard, so _READ_KWARGS/_WRITE_KWARGS outside the block are used.
DRY_RUN = False
NO_BACKUP = False
_DRY_FS = {}          # path -> content (virtual file content in dry-run)
_DRY_DELETED = set()  # paths treated as deleted in dry-run


def _dry(msg):
    print(f"{YELLOW}[dry-run]{NC} {msg}")


def copy_file(src, dst):
    """Replacement for shutil.copyfile — in dry-run, only prints the plan and updates the overlay."""
    if DRY_RUN:
        _dry(f"copy: {src} → {dst}")
        try:
            _DRY_FS[dst] = read_text(src)
            _DRY_DELETED.discard(dst)
        except OSError:
            pass
        return
    shutil.copyfile(src, dst)


def backup_file(path, suffix=".bak"):
    """Create a backup. Skipped with --no-backup."""
    if NO_BACKUP:
        return
    copy_file(path, f"{path}{suffix}")


def remove_file(path):
    """Delete — plan only in dry-run. Passes quietly if missing."""
    if DRY_RUN:
        _dry(f"delete: {path}")
        _DRY_FS.pop(path, None)
        _DRY_DELETED.add(path)
        return
    if os.path.exists(path):
        os.remove(path)


def move_file(src, dst):
    """Move (mainly backup restore) — plan only in dry-run."""
    if DRY_RUN:
        _dry(f"move: {src} → {dst}")
        try:
            _DRY_FS[dst] = read_text(src)
            _DRY_DELETED.discard(dst)
        except OSError:
            pass
        _DRY_FS.pop(src, None)
        _DRY_DELETED.add(src)
        return
    shutil.move(src, dst)


def make_dirs(path):
    if DRY_RUN:
        _dry(f"create directory: {path}")
        return
    os.makedirs(path, exist_ok=True)


def path_exists(path):
    """Existence check — honors the dry-run overlay."""
    if DRY_RUN:
        if path in _DRY_FS:
            return True
        if path in _DRY_DELETED:
            return False
    return os.path.exists(path)


def read_text(path):
    if DRY_RUN:
        if path in _DRY_FS:
            return _DRY_FS[path]
        if path in _DRY_DELETED:
            raise FileNotFoundError(path)
    with open(path, "r", **_READ_KWARGS) as f:
        return f.read()


def write_text(path, content):
    if DRY_RUN:
        _dry(f"write: {path} ({len(content)} bytes)")
        _DRY_FS[path] = content
        _DRY_DELETED.discard(path)
        return
    with open(path, "w", **_WRITE_KWARGS) as f:
        f.write(content)


def append_text(path, content):
    if DRY_RUN:
        _dry(f"append: {path}")
        base = read_text(path) if (path in _DRY_FS or path_exists(path)) else ""
        _DRY_FS[path] = base + content
        _DRY_DELETED.discard(path)
        return
    with open(path, "a", **_WRITE_KWARGS) as f:
        f.write(content)
# <<< 공통 블록: 쓰기 게이트


# Output functions
def print_step(msg):
    print(f"{CYAN}▶{NC} {msg}")


def print_info(msg):
    print(f"  {BLUE}→{NC} {msg}")


def print_success(msg):
    print(f"{GREEN}✓{NC} {msg}")


def print_warning(msg):
    print(f"{YELLOW}⚠{NC} {msg}")


def print_error(msg):
    print(f"{RED}✗{NC} {msg}")


# Help
def show_help():
    print(f"""{CYAN}Flutter iOS TestFlight setup script{NC}

{YELLOW}★ Wizard-first architecture ★{NC}
  This wizard generates every config file,
  and the GitHub Actions workflows use the generated files as they are.

{BLUE}Build pipeline:{NC}
  1. flutter build ios --no-codesign (Flutter build)
  2. xcodebuild archive (create the Xcode archive)
  3. xcodebuild -exportArchive (create the IPA)
  4. fastlane upload_testflight (upload to TestFlight)

{BLUE}Usage (recommended — named flags):{NC}
  python3 testflight-wizard.py setup \\
    --project-path /path/to/project \\
    --bundle-id com.example.myapp \\
    --team-id ABC1234DEF \\
    --profile-name "MyApp Distribution"

{BLUE}Usage (legacy — positional arguments, still supported):{NC}
  python3 testflight-wizard.py setup PROJECT_PATH BUNDLE_ID TEAM_ID PROFILE_NAME [USES_ENCRYPTION]

{BLUE}Parameters:{NC}
  --project-path      Flutter project root path
  --bundle-id         iOS app Bundle ID (e.g. com.example.myapp)
  --team-id           Apple Developer Team ID (10 characters)
  --profile-name      Provisioning Profile name
  --uses-encryption   Whether the app uses encryption (true/false, default: false)

{BLUE}Common options (same in all three wizards):{NC}
  --dry-run           Print what would change without touching any file
  --no-backup         Do not create backups (.bak) of existing files
  --non-interactive   Run without confirmation prompts (for CI)

{BLUE}Examples:{NC}
  python3 testflight-wizard.py setup --project-path . --bundle-id com.example.myapp \\
    --team-id ABC1234DEF --profile-name "MyApp Distribution" --dry-run
  python3 testflight-wizard.py setup /path/to/project com.example.myapp ABC1234DEF "MyApp Distribution"

{BLUE}Files created or modified:{NC}
  - ios/Gemfile                    Fastlane dependencies
  - ios/fastlane/Fastfile          TestFlight upload setup ★
  - ios/ExportOptions.plist        IPA export settings ★
  - ios/Runner.xcodeproj           Manual Signing patch ★
  - ios/Runner/Info.plist          Encryption setting (ITSAppUsesNonExemptEncryption)
""")


# Validate parameters
def validate_params(params):
    global PROJECT_PATH, BUNDLE_ID, TEAM_ID, PROFILE_NAME, USES_NON_EXEMPT_ENCRYPTION

    if len(params) < 4:
        print_error("Not enough parameters.")
        print("")
        show_help()
        sys.exit(1)

    PROJECT_PATH = params[0]
    BUNDLE_ID = params[1]
    TEAM_ID = params[2]
    PROFILE_NAME = params[3]
    # 5th parameter: whether encryption is used (default: false)
    USES_NON_EXEMPT_ENCRYPTION = params[4] if len(params) >= 5 and params[4] else "false"

    # Check the project path
    if not os.path.isdir(PROJECT_PATH):
        print_error(f"Project path does not exist: {PROJECT_PATH}")
        sys.exit(1)

    # Check pubspec.yaml (Flutter project)
    if not path_exists(f"{PROJECT_PATH}/pubspec.yaml"):
        print_error("Not a Flutter project (no pubspec.yaml)")
        sys.exit(1)

    # Check the ios folder
    if not os.path.isdir(f"{PROJECT_PATH}/ios"):
        print_error("No ios folder. Run 'flutter create .' first.")
        sys.exit(1)

    # Check the Bundle ID format
    if "." not in BUNDLE_ID:
        print_error(f"Invalid Bundle ID format: {BUNDLE_ID}")
        print_error("Example: com.example.myapp")
        sys.exit(1)

    # Check the Team ID length
    if len(TEAM_ID) != 10:
        print_error(f"Team ID must be 10 characters: {TEAM_ID}")
        sys.exit(1)

    # Validate the encryption setting (only true/false allowed)
    if USES_NON_EXEMPT_ENCRYPTION not in ("true", "false"):
        print_warning(f"Invalid encryption value: {USES_NON_EXEMPT_ENCRYPTION}")
        print_warning("Using the default 'false'.")
        USES_NON_EXEMPT_ENCRYPTION = "false"


# Find the template directory
def find_template_dir():
    global TEMPLATE_DIR
    # Relative to the script location
    script_dir = os.path.dirname(os.path.abspath(__file__))
    TEMPLATE_DIR = f"{script_dir}/templates"

    if not os.path.isdir(TEMPLATE_DIR):
        print_error(f"Template directory not found: {TEMPLATE_DIR}")
        sys.exit(1)

    print_info(f"Template directory: {TEMPLATE_DIR}")


# Create the Gemfile
def create_gemfile():
    print_step("Creating Gemfile...")

    gemfile_path = f"{PROJECT_PATH}/ios/Gemfile"

    # Back up the existing file
    if path_exists(gemfile_path):
        print_warning(f"Backing up existing Gemfile: {gemfile_path}.bak")
        backup_file(gemfile_path)

    write_text(gemfile_path, """# frozen_string_literal: true

source "https://rubygems.org"

# Fastlane - iOS 빌드 자동화
# Ruby 3.4+ 공식 지원 버전 (2.228+)
gem "fastlane", "~> 2.228"

# multi_json - google-apis transitive 의존성이 gemspec에 선언 누락한 upstream 버그 회피 (Gem::LoadError 방지)
gem "multi_json"

# CocoaPods - iOS 의존성 관리
gem "cocoapods", "~> 1.15"
""")

    print_success(f"Gemfile created: {gemfile_path}")


# Create the Fastfile (copied from the template)
# ★ This file is used directly by the GitHub Actions workflow ★
def create_fastfile():
    print_step("Creating Fastfile...")

    fastlane_dir = f"{PROJECT_PATH}/ios/fastlane"
    fastfile_path = f"{fastlane_dir}/Fastfile"
    template_fastfile = f"{TEMPLATE_DIR}/Fastfile.ios.template"

    # Create the fastlane directory
    make_dirs(fastlane_dir)

    # Back up the existing file
    if path_exists(fastfile_path):
        print_warning(f"Backing up existing Fastfile: {fastfile_path}.bak")
        backup_file(fastfile_path)

    # Check the template file exists
    if not path_exists(template_fastfile):
        print_error(f"Fastfile template not found: {template_fastfile}")
        sys.exit(1)

    # Copy from the template
    copy_file(template_fastfile, fastfile_path)

    print_success(f"Fastfile created: {fastfile_path}")
    print_info("  → The GitHub Actions workflow uses this file directly")


# Create ExportOptions.plist (needed for xcodebuild -exportArchive)
def create_export_options_plist():
    print_step("Creating ExportOptions.plist...")

    export_options_path = f"{PROJECT_PATH}/ios/ExportOptions.plist"
    template_export_options = f"{TEMPLATE_DIR}/ExportOptions.plist"

    # Back up the existing file
    if path_exists(export_options_path):
        print_warning(f"Backing up existing ExportOptions.plist: {export_options_path}.bak")
        backup_file(export_options_path)

    # Check the template file exists
    if path_exists(template_export_options):
        # Copy from the template and substitute placeholders
        content = read_text(template_export_options)
        content = content.replace("{{TEAM_ID}}", TEAM_ID)
        content = content.replace("{{BUNDLE_ID}}", BUNDLE_ID)
        content = content.replace("{{PROFILE_NAME}}", PROFILE_NAME)
        write_text(export_options_path, content)
        print_info("  → Created from the template")
    else:
        # No template: create it directly
        write_text(export_options_path, f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>method</key>
    <string>app-store</string>
    <key>teamID</key>
    <string>{TEAM_ID}</string>
    <key>provisioningProfiles</key>
    <dict>
        <key>{BUNDLE_ID}</key>
        <string>{PROFILE_NAME}</string>
    </dict>
    <key>signingStyle</key>
    <string>manual</string>
    <key>signingCertificate</key>
    <string>Apple Distribution</string>
    <key>manageAppVersionAndBuildNumber</key>
    <false/>
    <key>stripSwiftSymbols</key>
    <true/>
    <key>uploadBitcode</key>
    <false/>
    <key>uploadSymbols</key>
    <true/>
</dict>
</plist>
""")

    print_success(f"ExportOptions.plist created: {export_options_path}")
    print_info(f"  • Team ID: {TEAM_ID}")
    print_info(f"  • Bundle ID: {BUNDLE_ID}")
    print_info(f"  • Profile Name: {PROFILE_NAME}")


# Update .gitignore (optional)
def update_gitignore():
    print_step("Checking .gitignore...")

    gitignore_path = f"{PROJECT_PATH}/ios/.gitignore"

    # Gemfile.lock is usually not committed
    if path_exists(gitignore_path):
        if not re.search("Gemfile.lock", read_text(gitignore_path)):
            # Through the gate — in dry-run nothing is actually added
            append_text(gitignore_path, "\n# Fastlane\nGemfile.lock\n")
            print_info("Added Gemfile.lock to .gitignore")

    print_success(".gitignore checked")


# Add the encryption setting to Info.plist (Export Compliance)
def update_info_plist_encryption():
    print_step("Adding the encryption setting to Info.plist...")

    info_plist_path = f"{PROJECT_PATH}/ios/Runner/Info.plist"

    if not path_exists(info_plist_path):
        print_error(f"Info.plist not found: {info_plist_path}")
        return 1

    content = read_text(info_plist_path)

    # Check whether the ITSAppUsesNonExemptEncryption key already exists
    if "ITSAppUsesNonExemptEncryption" in content:
        print_info("ITSAppUsesNonExemptEncryption is already set")
        # Update the existing value (like sed, matches only when key and value are on the same line)
        if USES_NON_EXEMPT_ENCRYPTION == "true":
            content = re.sub(
                r"<key>ITSAppUsesNonExemptEncryption</key>[ \t\v\f\r]*<false/>",
                "<key>ITSAppUsesNonExemptEncryption</key>\n\t<true/>",
                content,
            )
        else:
            content = re.sub(
                r"<key>ITSAppUsesNonExemptEncryption</key>[ \t\v\f\r]*<true/>",
                "<key>ITSAppUsesNonExemptEncryption</key>\n\t<false/>",
                content,
            )
        write_text(info_plist_path, content)
        print_success("ITSAppUsesNonExemptEncryption value updated")
        return 0

    # Create a backup
    backup_file(info_plist_path)
    print_info(f"Backup created: {info_plist_path}.bak")

    # Add ITSAppUsesNonExemptEncryption right before </dict>
    encryption_value = "true" if USES_NON_EXEMPT_ENCRYPTION == "true" else "false"

    content = content.replace(
        "</dict>",
        f"<key>ITSAppUsesNonExemptEncryption</key>\n\t<{encryption_value}/>\n</dict>",
    )
    write_text(info_plist_path, content)

    # Verify the change
    if "ITSAppUsesNonExemptEncryption" in read_text(info_plist_path):
        print_success(f"ITSAppUsesNonExemptEncryption added: <{encryption_value}/>")
        remove_file(f"{info_plist_path}.bak")
    else:
        print_error("Failed to add ITSAppUsesNonExemptEncryption!")
        move_file(f"{info_plist_path}.bak", info_plist_path)
        return 1

    return 0


# Change the Bundle ID in the Xcode project (to match the Apple Developer settings)
def update_bundle_id():
    print_step("Checking and updating the Bundle ID...")

    pbxproj_path = f"{PROJECT_PATH}/ios/Runner.xcodeproj/project.pbxproj"

    if not path_exists(pbxproj_path):
        print_error(f"project.pbxproj not found: {pbxproj_path}")
        return 1

    content = read_text(pbxproj_path)

    # Skip if the entered Bundle ID already exists
    if f"PRODUCT_BUNDLE_IDENTIFIER = {BUNDLE_ID};" in content:
        print_info(f"Bundle ID is already set correctly: {BUNDLE_ID}")
        return 0

    # Extract the Runner app's Bundle ID from project.pbxproj (excluding RunnerTests)
    current_bundle_id = ""
    for line in content.splitlines():
        if "PRODUCT_BUNDLE_IDENTIFIER = " in line and "RunnerTests" not in line:
            value = re.sub(r".*= ", "", line)          # sed 's/.*= //'
            value = re.sub(r";$", "", value)           # sed 's/;$//'
            current_bundle_id = re.sub(r"\s", "", value)  # tr -d '[:space:]'
            break

    if not current_bundle_id:
        print_error("Could not find the current Bundle ID")
        return 1

    print_info(f"Current Bundle ID: {current_bundle_id}")
    print_info(f"New Bundle ID: {BUNDLE_ID}")

    # Change it if the Bundle ID differs
    if current_bundle_id != BUNDLE_ID:
        print_warning("The Bundle ID differs. Changing it automatically...")

        # Create a backup
        backup_file(pbxproj_path, ".bundleid.bak")

        # Change the Runner app's Bundle ID (exact match)
        content = content.replace(
            f"PRODUCT_BUNDLE_IDENTIFIER = {current_bundle_id};",
            f"PRODUCT_BUNDLE_IDENTIFIER = {BUNDLE_ID};",
        )

        # Also change the RunnerTests Bundle ID (Runner app Bundle ID + .RunnerTests)
        content = content.replace(
            f"PRODUCT_BUNDLE_IDENTIFIER = {current_bundle_id}.RunnerTests;",
            f"PRODUCT_BUNDLE_IDENTIFIER = {BUNDLE_ID}.RunnerTests;",
        )
        write_text(pbxproj_path, content)

        # Verify the change
        if f"PRODUCT_BUNDLE_IDENTIFIER = {BUNDLE_ID};" in read_text(pbxproj_path):
            print_success(f"Bundle ID changed: {current_bundle_id} → {BUNDLE_ID}")
            remove_file(f"{pbxproj_path}.bundleid.bak")
        else:
            print_error("Failed to change the Bundle ID!")
            move_file(f"{pbxproj_path}.bundleid.bak", pbxproj_path)
            return 1

    return 0


def _replace_profile_specifier(content):
    """"PROVISIONING_PROFILE_SPECIFIER" = "..."; value updated to PROFILE_NAME."""
    return re.sub(
        r'"PROVISIONING_PROFILE_SPECIFIER" = "[^"\n]*";',
        lambda m: f'"PROVISIONING_PROFILE_SPECIFIER" = "{PROFILE_NAME}";',
        content,
    )


# Add DEVELOPMENT_TEAM and Manual Signing to the Xcode project (required for CI builds)
def patch_xcode_project():
    print_step("Setting DEVELOPMENT_TEAM and Manual Signing in the Xcode project...")

    pbxproj_path = f"{PROJECT_PATH}/ios/Runner.xcodeproj/project.pbxproj"

    if not path_exists(pbxproj_path):
        print_error(f"project.pbxproj not found: {pbxproj_path}")
        return 1

    # Update the Bundle ID first
    # (in sh, set -e ended the script at once if update_bundle_id failed — handled the same way)
    rc = update_bundle_id()
    if rc != 0:
        sys.exit(rc)

    # Create a backup
    backup_file(pbxproj_path)
    print_info(f"Backup created: {pbxproj_path}.bak")

    content = read_text(pbxproj_path)

    # Check whether DEVELOPMENT_TEAM already exists
    if f"DEVELOPMENT_TEAM = {TEAM_ID}" in content:
        print_info("DEVELOPMENT_TEAM is already set")
        # Check CODE_SIGN_STYLE too and add it if needed
        if "CODE_SIGN_STYLE = Manual" not in content:
            print_info("Adding CODE_SIGN_STYLE = Manual...")
            # Change Automatic to Manual or add it
            if "CODE_SIGN_STYLE = Automatic" in content:
                content = content.replace("CODE_SIGN_STYLE = Automatic;", "CODE_SIGN_STYLE = Manual;")
            else:
                # Add CODE_SIGN_STYLE after the DEVELOPMENT_TEAM line
                content = content.replace(
                    f"DEVELOPMENT_TEAM = {TEAM_ID};",
                    f"DEVELOPMENT_TEAM = {TEAM_ID};\n\t\t\t\tCODE_SIGN_STYLE = Manual;",
                )
            print_success("CODE_SIGN_STYLE = Manual set")

        # Update PROVISIONING_PROFILE_SPECIFIER
        if "PROVISIONING_PROFILE_SPECIFIER" in content:
            content = _replace_profile_specifier(content)
            print_success("PROVISIONING_PROFILE_SPECIFIER updated")

        write_text(pbxproj_path, content)
        remove_file(f"{pbxproj_path}.bak")
        print_success("Xcode project checked")
        return 0

    # Replace DEVELOPMENT_TEAM if it exists with a different value
    if "DEVELOPMENT_TEAM = " in content:
        print_info("Updating the existing DEVELOPMENT_TEAM value")
        content = re.sub(r"DEVELOPMENT_TEAM = [^;\n]*;", f"DEVELOPMENT_TEAM = {TEAM_ID};", content)
        print_success("DEVELOPMENT_TEAM updated")

        # Set CODE_SIGN_STYLE = Manual
        if "CODE_SIGN_STYLE = Automatic" in content:
            content = content.replace("CODE_SIGN_STYLE = Automatic;", "CODE_SIGN_STYLE = Manual;")
            print_success("CODE_SIGN_STYLE = Manual set")
        elif "CODE_SIGN_STYLE = Manual" not in content:
            content = content.replace(
                f"DEVELOPMENT_TEAM = {TEAM_ID};",
                f"DEVELOPMENT_TEAM = {TEAM_ID};\n\t\t\t\tCODE_SIGN_STYLE = Manual;",
            )
            print_success("CODE_SIGN_STYLE = Manual added")

        # Set CODE_SIGN_IDENTITY
        if 'CODE_SIGN_IDENTITY = "Apple Distribution"' not in content:
            content = content.replace(
                "CODE_SIGN_STYLE = Manual;",
                'CODE_SIGN_STYLE = Manual;\n\t\t\t\tCODE_SIGN_IDENTITY = "Apple Distribution";',
            )
            print_success("CODE_SIGN_IDENTITY = Apple Distribution added")

        # Set PROVISIONING_PROFILE_SPECIFIER (core!)
        if "PROVISIONING_PROFILE_SPECIFIER" not in content:
            content = content.replace(
                'CODE_SIGN_IDENTITY = "Apple Distribution";',
                'CODE_SIGN_IDENTITY = "Apple Distribution";\n\t\t\t\t'
                f'"PROVISIONING_PROFILE_SPECIFIER" = "{PROFILE_NAME}";',
            )
            print_success(f"PROVISIONING_PROFILE_SPECIFIER = {PROFILE_NAME} added")
        else:
            # Update an existing value
            content = _replace_profile_specifier(content)
            print_success("PROVISIONING_PROFILE_SPECIFIER updated")

        # Update the old CODE_SIGN_IDENTITY setting
        if '"CODE_SIGN_IDENTITY[sdk=iphoneos*]" = "iPhone Developer"' in content:
            content = content.replace(
                '"CODE_SIGN_IDENTITY[sdk=iphoneos*]" = "iPhone Developer"',
                '"CODE_SIGN_IDENTITY[sdk=iphoneos*]" = "Apple Distribution"',
            )
            print_success("CODE_SIGN_IDENTITY[sdk=iphoneos*] updated")

        write_text(pbxproj_path, content)
        remove_file(f"{pbxproj_path}.bak")
        return 0

    # Add DEVELOPMENT_TEAM to the Runner target's buildSettings
    # Add after the PRODUCT_BUNDLE_IDENTIFIER line
    print_info("Adding DEVELOPMENT_TEAM...")

    # Check the Bundle ID exists (update_bundle_id already handled it, so it must exist)
    if f"PRODUCT_BUNDLE_IDENTIFIER = {BUNDLE_ID};" not in content:
        print_error("Bundle ID not found in project.pbxproj!")
        print("")
        print_error("┌─────────────────────────────────────────────────────────────────┐")
        print_error(f"│ Bundle ID you entered: {BUNDLE_ID}")
        print_error("├─────────────────────────────────────────────────────────────────┤")
        print_error("│ Bundle IDs found in project.pbxproj:")
        # Print the Bundle IDs that actually exist
        found_ids = []
        for line in content.splitlines():
            if "PRODUCT_BUNDLE_IDENTIFIER = " in line:
                value = re.sub(r".*= ", "  • ", line)
                value = re.sub(r";$", "", value)
                found_ids.append(value)
        for entry in sorted(set(found_ids)):
            # sh's `while read line` strips surrounding spaces, so strip the same way
            print_error(f"│ {entry.strip()}")
        print_error("└─────────────────────────────────────────────────────────────────┘")
        print("")
        print_error("How to fix:")
        print_info("1. Find the exact Bundle ID in the list above (case-sensitive!)")
        print_info("2. Run the script again with the correct Bundle ID")
        print_info(f'   e.g. python3 testflight-wizard.py setup "{PROJECT_PATH}" "exact.bundle.id" "{TEAM_ID}" "{PROFILE_NAME}"')
        move_file(f"{pbxproj_path}.bak", pbxproj_path)
        return 1

    # Add all Manual Signing settings after the Runner app's Bundle ID line
    # - DEVELOPMENT_TEAM: Apple team ID
    # - CODE_SIGN_STYLE: Manual (disables automatic signing)
    # - CODE_SIGN_IDENTITY: Apple Distribution (distribution certificate)
    # - PROVISIONING_PROFILE_SPECIFIER: provisioning profile name
    content = content.replace(
        f"PRODUCT_BUNDLE_IDENTIFIER = {BUNDLE_ID};",
        f"PRODUCT_BUNDLE_IDENTIFIER = {BUNDLE_ID};\n"
        f"\t\t\t\tDEVELOPMENT_TEAM = {TEAM_ID};\n"
        "\t\t\t\tCODE_SIGN_STYLE = Manual;\n"
        '\t\t\t\tCODE_SIGN_IDENTITY = "Apple Distribution";\n'
        f'\t\t\t\t"PROVISIONING_PROFILE_SPECIFIER" = "{PROFILE_NAME}";',
    )

    # Change an old CODE_SIGN_IDENTITY setting to Apple Distribution
    if '"CODE_SIGN_IDENTITY[sdk=iphoneos*]" = "iPhone Developer"' in content:
        content = content.replace(
            '"CODE_SIGN_IDENTITY[sdk=iphoneos*]" = "iPhone Developer"',
            '"CODE_SIGN_IDENTITY[sdk=iphoneos*]" = "Apple Distribution"',
        )
        print_success("CODE_SIGN_IDENTITY[sdk=iphoneos*] updated")

    write_text(pbxproj_path, content)

    # Verify the change
    if f"DEVELOPMENT_TEAM = {TEAM_ID}" in content and "CODE_SIGN_STYLE = Manual" in content:
        print_success(f"DEVELOPMENT_TEAM added: {TEAM_ID}")
        print_success("CODE_SIGN_STYLE = Manual set")
        remove_file(f"{pbxproj_path}.bak")
    else:
        print_error("Failed to add DEVELOPMENT_TEAM or CODE_SIGN_STYLE!")
        print("")
        print_error("Debug info:")
        print_info(f"  • Bundle ID you entered: {BUNDLE_ID}")
        print_info(f"  • Team ID you entered: {TEAM_ID}")
        print_info(f"  • project.pbxproj path: {pbxproj_path}")
        print("")
        print_error("Possible causes:")
        print_info("  1. The text replacement failed")
        print_info("  2. No write permission for the file")
        print("")
        print_warning("To set it manually:")
        print_info("  Open Xcode → Runner target → Signing & Capabilities → choose the Team")
        move_file(f"{pbxproj_path}.bak", pbxproj_path)
        return 1

    print_success("Xcode project configured (Manual Signing applied)")
    return 0


# Completion message
def print_completion():
    # Encryption setting display text
    if USES_NON_EXEMPT_ENCRYPTION == "true":
        encryption_display = "Standard encryption (true)"
    else:
        encryption_display = "None - HTTPS only (false)"

    print("")
    print(f"{GREEN}╔════════════════════════════════════════════════════════════════╗{NC}")
    print(f"{GREEN}║          🎉 iOS TestFlight deployment setup complete! 🎉       ║{NC}")
    print(f"{GREEN}╚════════════════════════════════════════════════════════════════╝{NC}")
    print("")
    print(f"{YELLOW}★ Wizard-first architecture ★{NC}")
    print("  Setup is complete. The workflows use these files as they are.")
    print("")
    print(f"{CYAN}Files created or modified:{NC}")
    print("  ✅ ios/Gemfile                    (Fastlane dependencies)")
    print("  ✅ ios/fastlane/Fastfile          (TestFlight upload) ★ used directly by the workflow")
    print("  ✅ ios/ExportOptions.plist        (IPA export settings) ★ key file")
    print("  ✅ ios/Runner.xcodeproj           (Manual Signing patch) ★ key file")
    print("  ✅ ios/Runner/Info.plist          (encryption setting)")
    print("")
    print(f"{CYAN}Configured values:{NC}")
    print(f"  • Bundle ID: {BUNDLE_ID}")
    print(f"  • Team ID: {TEAM_ID}")
    print(f"  • Profile Name: {PROFILE_NAME}")
    print("  • Code Sign Style: Manual")
    print(f"  • Encryption: {encryption_display}")
    print("")
    print(f"{CYAN}Build pipeline:{NC}")
    print("  1. flutter build ios --no-codesign")
    print("  2. xcodebuild archive")
    print("  3. xcodebuild -exportArchive (uses ExportOptions.plist)")
    print("  4. fastlane upload_testflight (uses the lane in Fastfile)")
    print("")
    print(f"{YELLOW}Next steps:{NC}")
    print("  1. Set up GitHub Secrets:")
    print("     • APPLE_CERTIFICATE_BASE64")
    print("     • APPLE_CERTIFICATE_PASSWORD")
    print("     • APPLE_PROVISIONING_PROFILE_BASE64")
    print("     • IOS_PROVISIONING_PROFILE_NAME")
    print("     • APP_STORE_CONNECT_API_KEY_ID")
    print("     • APP_STORE_CONNECT_ISSUER_ID")
    print("     • APP_STORE_CONNECT_API_KEY_BASE64")
    print("")
    print("  2. Commit the changes:")
    print("     git add ios/")
    print('     git commit -m "chore: set up iOS TestFlight deployment"')
    print("")
    print("  3. Push to the deploy branch to test the build")
    print("")
    print("🎛️  Deploy mode (optional):")
    print("   Set IOS_DEPLOY_MODE in the GitHub repo Variables to choose the default deploy scope.")
    print("     store_only    : upload to TestFlight only (default)")
    print("     store_prepare : stop just before App Store submission (a person clicks Add for Review in ASC)")
    print("     store_submit  : submit for App Store review automatically (available after the first release is done by hand)")
    print("   When you run the workflow manually, the deploy_mode input overrides this variable.")


# ===================================================================
# Main
# ===================================================================

# >>> 공통 블록: 인자 계약 (identical in testflight/playstore — compared by _shared/check-consistency.py)
# ===================================================================
# Shared argument contract (named flags canonical + old positional compatibility)
# ===================================================================
# **Named flags** are canonical. As positional arguments grew to 10, order mistakes
# became common (especially the password slot), and the command alone did not show what was passed.
#
# Old positional calls are still accepted — commands the wizard HTML already generated and users
# copied are in positional form. Both work.
#
#   new:  setup --project-path /p --bundle-id com.x.y --team-id ABC123 ...
#   old:  setup /p com.x.y ABC123 "Profile Name"
#
# firebase has no history of positional calls, so it takes the same flags via argparse.
# ===================================================================

COMMON_FLAGS = ("--dry-run", "--non-interactive", "--no-backup")


def normalize_params(params, order):
    """Accept named flags and positional arguments together and normalize to (positional list, options dict).

    order: tuple of flag names matching the positional order
           e.g. ("project-path", "bundle-id", "team-id", "profile-name")
    Supported forms: --key value / --key=value / boolean flags (COMMON_FLAGS)
    """
    named, positional = {}, []
    opts = {"dry_run": False, "non_interactive": False, "backup": True}
    i = 0
    while i < len(params):
        tok = params[i]
        if tok in COMMON_FLAGS:
            if tok == "--dry-run":
                opts["dry_run"] = True
            elif tok == "--non-interactive":
                opts["non_interactive"] = True
            else:
                opts["backup"] = False
            i += 1
            continue
        if tok.startswith("--"):
            key, _, inline = tok[2:].partition("=")
            if inline:
                named[key] = inline
                i += 1
            else:
                if i + 1 >= len(params):
                    print_error(f"--{key} needs a value.")
                    sys.exit(1)
                named[key] = params[i + 1]
                i += 2
            if key not in order:
                print_error(f"Unknown option: --{key}")
                print(f"Available: {', '.join('--' + k for k in order)}")
                sys.exit(1)
            continue
        positional.append(tok)
        i += 1

    if named:
        # If any named flag is present, treat it as named style and reorder by order.
        # Missing slots are filled with empty strings so the existing validation catches them.
        merged = [named.get(k, "") for k in order]
        # With mixed positional arguments (partial migration), fill empty slots from the front
        for value in positional:
            for idx in range(len(merged)):
                if not merged[idx]:
                    merged[idx] = value
                    break
        return merged, opts

    return positional, opts
# <<< 공통 블록: 인자 계약


def cmd_setup(params):
    print("")
    print(f"{CYAN}╔════════════════════════════════════════════════════════════════╗{NC}")
    print(f"{CYAN}║       Flutter iOS TestFlight setup script                      ║{NC}")
    print(f"{CYAN}╚════════════════════════════════════════════════════════════════╝{NC}")
    print("")

    # Check help options
    if params and params[0] in ("-h", "--help"):
        show_help()
        sys.exit(0)

    # Normalize named flags → positional (both old and new call forms supported)
    global DRY_RUN, NO_BACKUP
    params, cli_opts = normalize_params(params, ("project-path", "bundle-id", "team-id", "profile-name", "uses-encryption"))
    DRY_RUN = cli_opts["dry_run"]
    NO_BACKUP = not cli_opts["backup"]
    if DRY_RUN:
        print(f"{YELLOW}⚠️  dry-run mode — no files are created or changed.{NC}")
        print("")

    # Validate parameters
    validate_params(params)

    print(f"{BLUE}Project path:{NC} {PROJECT_PATH}")
    print(f"{BLUE}Bundle ID:{NC} {BUNDLE_ID}")
    print(f"{BLUE}Team ID:{NC} {TEAM_ID}")
    print(f"{BLUE}Profile Name:{NC} {PROFILE_NAME}")
    print(f"{BLUE}Uses encryption:{NC} {USES_NON_EXEMPT_ENCRYPTION}")
    print("")

    # Find the template directory
    find_template_dir()

    # Create files
    create_gemfile()
    create_fastfile()
    create_export_options_plist()
    update_gitignore()
    # (same as sh's set -e: exit at once with that exit code on failure)
    rc = patch_xcode_project()
    if rc != 0:
        sys.exit(rc)
    rc = update_info_plist_encryption()
    if rc != 0:
        sys.exit(rc)

    # Done
    print_completion()


def main(argv=None):
    argv = list(sys.argv[1:]) if argv is None else list(argv)

    parser = argparse.ArgumentParser(
        prog="testflight-wizard.py",
        description="Flutter iOS TestFlight setup script",
    )
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser(
        "setup",
        add_help=False,
        help="Create the iOS TestFlight deployment setup (PROJECT_PATH BUNDLE_ID TEAM_ID PROFILE_NAME [USES_ENCRYPTION])",
    )

    # Arguments after setup are passed through positionally, like the old sh.
    # (argparse REMAINDER has a known problem swallowing a leading -h etc., so routing is manual)
    if argv and argv[0] == "setup":
        cmd_setup(argv[1:])
        return

    if argv:
        parser.parse_args(argv)  # -h/--help and unknown argument handling
    parser.print_help()
    sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
