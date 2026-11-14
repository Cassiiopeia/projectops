#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ===================================================================
# Flutter Android Play Store wizard local runner script (single Python file)
# ===================================================================
#
# Merges the old 3 sh/ps1 script pairs + 1 patch py into argparse subcommands.
#   setup         : initial Play Store deploy setup (old setup script, sh 829 lines canonical)
#   apply         : apply the generated settings to the Flutter project (old apply script)
#   detect-app-id : environment check + applicationId auto-detection (old detect script, JSON output)
#
# ★ Logic preservation rule ★
# - The old .sh is canonical. Same input → same output (file paths/contents), same validation order,
#   same error messages (Korean text as it was), same exit codes.
# - Where .sh and .ps1 differed, .sh wins, and each spot is recorded with a "sh/ps1 branch:" comment.
#   Windows-only behavior (killing processes, SDK path, user env registration)
#   adopts the .ps1 behavior as the Windows branch.
# - The old gradle patch py logic was absorbed into patch_build_gradle() as inner functions without
#   changing a single character of strings/regexes (the standalone file was deleted).
#
# Usage:
#   python playstore-wizard.py setup PROJECT_PATH APPLICATION_ID KEY_ALIAS STORE_PASSWORD KEY_PASSWORD VALIDITY_DAYS CERT_CN CERT_O CERT_L CERT_C
#   python playstore-wizard.py apply [config_json_file]
#   python playstore-wizard.py detect-app-id PROJECT_PATH
#
# stdlib only (no external packages) — aims to work offline on both OSes.
# ===================================================================

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time

# Korean Windows cp949 console support
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ===================================================================
# Color definitions (same palette as the old sh)
# On Windows try enabling VT mode via ctypes; on failure print without color codes
# ===================================================================


def _ansi_enabled():
    if os.name != "nt":
        return True
    # For pipes/redirects, emit codes as is, same as sh
    if not sys.stdout.isatty():
        return True
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        ok = False
        for handle_id in (-11, -12):  # STD_OUTPUT_HANDLE, STD_ERROR_HANDLE
            handle = kernel32.GetStdHandle(handle_id)
            mode = ctypes.c_uint32()
            if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                if kernel32.SetConsoleMode(handle, mode.value | 0x0004):
                    ok = True
        return ok
    except Exception:
        return False


if _ansi_enabled():
    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    YELLOW = "\033[1;33m"
    BLUE = "\033[0;34m"
    CYAN = "\033[0;36m"
    NC = "\033[0m"  # No Color
else:
    RED = GREEN = YELLOW = BLUE = CYAN = NC = ""


# Output functions (setup: same as the old sh)
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


# ===================================================================
# build.gradle.kts auto patch (absorbed as is from the old standalone patch py — logic/text unchanged)
# - add key.properties loading code
# - add/update the signingConfigs block
# - set signingConfig in buildTypes.release
# ===================================================================


def patch_build_gradle(gradle_file_path):
    """Patch build.gradle.kts automatically."""

    # 1. Read the file
    try:
        with open(gradle_file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        print(f"❌ File not found: {gradle_file_path}")
        return False
    except Exception as e:
        print(f"❌ Could not read the file: {e}")
        return False

    # Create a backup (through the gate — honors dry-run/--no-backup)
    backup_path = f"{gradle_file_path}.bak"
    if NO_BACKUP:
        print("ℹ️  --no-backup: skipping the backup")
    else:
        try:
            write_text(backup_path, content)
            print(f"✅ Backup created: {backup_path}")
        except Exception as e:
            print(f"⚠️  Backup failed (continuing): {e}")

    original_content = content

    # 2. Add key.properties loading code (if missing)
    if 'keystorePropertiesFile' not in content:
        key_properties_code = '''
// Load key.properties file
import java.util.Properties
import java.io.FileInputStream
val keystorePropertiesFile = rootProject.file("key.properties")
val keystoreProperties = Properties()
if (keystorePropertiesFile.exists()) {
    keystoreProperties.load(FileInputStream(keystorePropertiesFile))
}
'''
        # Add after plugins { ... }
        pattern = r'(plugins\s*\{[^}]*\})'
        replacement = r'\1\n' + key_properties_code
        content = re.sub(pattern, replacement, content, count=1, flags=re.DOTALL)
        print("✅ Added the key.properties loading code")
    else:
        print("ℹ️  key.properties loading code already present")

    # 3. Add/update the signingConfigs block
    if 'signingConfigs {' not in content and 'signingConfigs{' not in content:
        # Add the signingConfigs block
        signing_configs_code = '''
    // Signing Configurations
    signingConfigs {
        create("release") {
            keyAlias = keystoreProperties["keyAlias"] as String? ?: ""
            keyPassword = keystoreProperties["keyPassword"] as String? ?: ""
            storeFile = keystoreProperties["storeFile"]?.let { rootProject.file(it) }
            storePassword = keystoreProperties["storePassword"] as String? ?: ""
        }
    }
'''
        # Add after android {
        pattern = r'(android\s*\{)'
        replacement = r'\1\n' + signing_configs_code
        content = re.sub(pattern, replacement, content, count=1)
        print("✅ Added the signingConfigs block")
    else:
        print("ℹ️  signingConfigs block already present")
        # Fix the existing storeFile path (file(it) → rootProject.file(it))
        if 'storeFile = keystoreProperties["storeFile"]?.let { file(it) }' in content:
            content = content.replace(
                'storeFile = keystoreProperties["storeFile"]?.let { file(it) }',
                'storeFile = keystoreProperties["storeFile"]?.let { rootProject.file(it) }'
            )
            print("✅ Fixed the existing storeFile path (file(it) → rootProject.file(it))")

    # 4. Set signingConfig in buildTypes.release
    # Remove the existing debug signingConfig
    content = re.sub(
        r'\s*signingConfig\s*=\s*signingConfigs\.getByName\(["\']debug["\']\)',
        '',
        content
    )

    # Add signingConfig to the release { } block (if missing)
    if 'signingConfig = signingConfigs.getByName("release")' not in content and \
       "signingConfig = signingConfigs.getByName('release')" not in content:
        # Add after release { (avoid duplicates)
        # Find the release block inside the buildTypes block
        pattern = r'(buildTypes\s*\{[^}]*release\s*\{)'
        if re.search(pattern, content, re.DOTALL):
            replacement = r'\1\n            signingConfig = signingConfigs.getByName("release")'
            content = re.sub(pattern, replacement, content, count=1, flags=re.DOTALL)
            print("✅ Added signingConfig to the release buildType")
        else:
            print("⚠️  Could not find the release buildType block")
    else:
        print("ℹ️  The release buildType already has signingConfig")

    # 5. Add/fix the flutter.source setting
    if 'flutter {' in content or 'flutter{' in content:
        # Check source = "../.."
        if not re.search(r'flutter\s*\{[^}]*source\s*=\s*"\.\.\/\.\."', content, re.DOTALL):
            # Change source = "." → "../.."
            if re.search(r'flutter\s*\{[^}]*source\s*=\s*"\."', content, re.DOTALL):
                content = re.sub(
                    r'(flutter\s*\{[^}]*source\s*=\s*)"\."',
                    r'\1"../.."',
                    content,
                    count=1,
                    flags=re.DOTALL
                )
                print("✅ flutter.source updated to '../..' (project root)")
            # flutter block exists but has no source
            elif re.search(r'flutter\s*\{', content):
                content = re.sub(
                    r'(flutter\s*\{)',
                    r'\1\n    source = "../.."',
                    content,
                    count=1
                )
                print("✅ flutter.source added as '../..' (project root)")
        else:
            print("ℹ️  flutter.source already set to '../..'")
    else:
        print("ℹ️  No flutter block (add it by hand if you need it)")

    # 6. Save the file (only if changed)
    if content != original_content:
        try:
            write_text(gradle_file_path, content)
            print("✅ build.gradle.kts patched!")
            return True
        except Exception as e:
            print(f"❌ Could not save the file: {e}")
            # Try restoring from the backup
            if path_exists(backup_path):
                try:
                    write_text(gradle_file_path, read_text(backup_path))
                    print("✅ Restored from the backup")
                except Exception as restore_error:
                    print(f"⚠️ Could not restore from the backup: {restore_error}")
            return False
    else:
        print("ℹ️  No changes (already configured)")
        return True


# ===================================================================
# Shared: find and kill processes using a file (setup-only helper)
# sh/ps1 branch: sh used lsof + pgrep, ps1 killed all java/gradle via Get-Process.
#   POSIX keeps the sh logic as is; Windows uses a taskkill approach equivalent to ps1.
# ===================================================================


def stop_processes_using_file(file_path):
    if not os.path.isfile(file_path):
        return False

    print_info(f"Looking for processes using the file: {file_path}")

    processes_killed = False

    if os.name != "nt":
        # Use the lsof command (Linux/macOS)
        if shutil.which("lsof"):
            try:
                out = subprocess.run(
                    ["lsof", "-t", file_path],
                    capture_output=True, text=True, encoding="utf-8", errors="replace"
                ).stdout
            except OSError:
                out = ""
            for pid_s in out.split():
                try:
                    pid = int(pid_s)
                except ValueError:
                    continue
                try:
                    os.kill(pid, 0)  # kill -0: check it is alive
                except OSError:
                    continue
                try:
                    proc_name = subprocess.run(
                        ["ps", "-p", str(pid), "-o", "comm="],
                        capture_output=True, text=True, encoding="utf-8", errors="replace"
                    ).stdout.strip() or "unknown"
                except OSError:
                    proc_name = "unknown"
                print_warning(f"Stopping process: {proc_name} (PID: {pid})")
                try:
                    os.kill(pid, 9)
                    processes_killed = True
                except OSError:
                    pass
                time.sleep(0.5)

        # Kill all Java/Gradle processes (when the file is locked)
        if not processes_killed:
            print_warning("No process using the file was found. Trying to stop all Java/Gradle processes...")
            for proc_name in ("java", "javaw", "gradle", "gradlew"):
                try:
                    out = subprocess.run(
                        ["pgrep", "-f", proc_name],
                        capture_output=True, text=True, encoding="utf-8", errors="replace"
                    ).stdout
                except OSError:
                    out = ""
                for pid_s in out.split():
                    try:
                        pid = int(pid_s)
                    except ValueError:
                        continue
                    print_warning(f"Stopping process: {proc_name} (PID: {pid})")
                    try:
                        os.kill(pid, 9)
                        processes_killed = True
                    except OSError:
                        pass
                    time.sleep(0.5)
    else:
        # Windows (ps1 style): force-kill java/gradle processes
        print_warning("No process using the file was found. Trying to stop all Java/Gradle processes...")
        for proc_name in ("java", "javaw", "gradle", "gradlew"):
            try:
                rc = subprocess.run(
                    ["taskkill", "/F", "/IM", proc_name + ".exe"],
                    capture_output=True
                ).returncode
            except OSError:
                rc = 1
            if rc == 0:
                print_warning(f"Stopping process: {proc_name}")
                processes_killed = True
                time.sleep(0.5)

    if processes_killed:
        print_info("Processes stopped. Waiting 5 seconds for file handles to be released...")
        time.sleep(5)
        return True

    return False


# ===================================================================
# setup subcommand (old setup script — sh canonical)
# ===================================================================

# Whether to skip keystore creation (same as sh — sh had no path setting it to 1 either; kept for behavior)
KEYSTORE_SKIPPED = False


def show_help():
    print(f"""{CYAN}Flutter Android Play Store setup script{NC}

{YELLOW}★ Wizard-first architecture ★{NC}
  This wizard generates every config file,
  and the GitHub Actions workflows use the generated files as they are.

{BLUE}Build pipeline:{NC}
  1. flutter build appbundle (create the AAB)
  2. fastlane deploy_internal (upload to the Play Store)

{BLUE}Usage (recommended — named flags):{NC}
  python playstore-wizard.py setup \\
    --project-path /path/to/project \\
    --application-id com.example.app \\
    --key-alias my-release-key \\
    --store-password MyPass123 --key-password MyPass123 \\
    --validity-days 99999 \\
    --cert-cn "My Name" --cert-o "My Company" --cert-l "Seoul" --cert-c "KR"

{BLUE}Usage (legacy — 10 positional arguments, still supported):{NC}
  python playstore-wizard.py setup PROJECT_PATH APPLICATION_ID KEY_ALIAS STORE_PASSWORD KEY_PASSWORD VALIDITY_DAYS CERT_CN CERT_O CERT_L CERT_C
  ⚠️ If a single argument is out of order, a password is saved wrong. Named flags are recommended.

{BLUE}Parameters:{NC}
  --project-path      Flutter project root path
  --application-id    Android Application ID (e.g. com.example.app)
  --key-alias         Keystore alias name
  --store-password    Keystore password
  --key-password      Key password
  --validity-days     Validity in days (e.g. 99999)
  --cert-cn           Certificate Common Name (e.g. "My Name")
  --cert-o            Certificate Organization (e.g. "My Company")
  --cert-l            Certificate Locality (e.g. "Seoul")
  --cert-c            Certificate Country Code (e.g. "KR")

{BLUE}Common options (same in all three wizards):{NC}
  --dry-run           Print what would change without creating files or the keystore
  --no-backup         Do not create backups (.bak) of existing files
  --non-interactive   Run without confirmation prompts (for CI)

{BLUE}Examples:{NC}
  python playstore-wizard.py setup --project-path . --application-id com.example.app \\
    --key-alias my-release-key --store-password MyPass123 --key-password MyPass123 \\
    --validity-days 99999 --cert-cn "My Name" --cert-o "My Company" --cert-l "Seoul" --cert-c "KR" --dry-run

{BLUE}Files created or modified:{NC}
  - android/.gitignore                    .gitignore update ★ runs first
  - android/app/keystore/key.jks         Keystore ★
  - android/key.properties               Signing info ★
  - android/app/build.gradle.kts         Signing config patch ★
  - android/fastlane/Fastfile.playstore  Play Store upload setup ★
  - android/Gemfile                      Fastlane dependencies
""")


def validate_params(params):
    # sh/ps1 branch: ps1 had mandatory param() binding + an Application ID regex check,
    #   unified to the sh rule (count check + contains '.' only).
    if len(params) < 10:
        print_error("Not enough parameters.")
        print("")
        show_help()
        sys.exit(1)

    ctx = {
        "PROJECT_PATH": params[0],
        "APPLICATION_ID": params[1],
        "KEY_ALIAS": params[2],
        "STORE_PASSWORD": params[3],
        "KEY_PASSWORD": params[4],
        "VALIDITY_DAYS": params[5],
        "CERT_CN": params[6],
        "CERT_O": params[7],
        "CERT_L": params[8],
        "CERT_C": params[9],
    }

    # Check the project path
    if not os.path.isdir(ctx["PROJECT_PATH"]):
        print_error(f"Project path does not exist: {ctx['PROJECT_PATH']}")
        sys.exit(1)

    # Check pubspec.yaml (Flutter project)
    if not os.path.isfile(os.path.join(ctx["PROJECT_PATH"], "pubspec.yaml")):
        print_error("Not a Flutter project (no pubspec.yaml)")
        sys.exit(1)

    # Check the android folder
    if not os.path.isdir(os.path.join(ctx["PROJECT_PATH"], "android")):
        print_error("No android folder. Run 'flutter create .' first.")
        sys.exit(1)

    # Check the Application ID format
    if "." not in ctx["APPLICATION_ID"]:
        print_error(f"Invalid Application ID format: {ctx['APPLICATION_ID']}")
        print_error("Example: com.example.app")
        sys.exit(1)

    # Check the password
    if not ctx["STORE_PASSWORD"] or not ctx["KEY_PASSWORD"]:
        print_error("The keystore password and key password are required.")
        sys.exit(1)

    # Check the validity period
    if not re.match(r"^[0-9]+$", ctx["VALIDITY_DAYS"]):
        print_error(f"Validity must be a number: {ctx['VALIDITY_DAYS']}")
        sys.exit(1)

    # Check the certificate info
    if not ctx["CERT_CN"] or not ctx["CERT_O"] or not ctx["CERT_L"] or not ctx["CERT_C"]:
        print_error("All certificate fields (CN, O, L, C) are required.")
        sys.exit(1)

    # Check the country code length
    if len(ctx["CERT_C"]) != 2:
        print_error(f"Country Code must be 2 letters: {ctx['CERT_C']}")
        sys.exit(1)

    return ctx


def find_template_dir():
    # Relative to the script location
    script_dir = os.path.dirname(os.path.abspath(__file__))
    template_dir = os.path.join(script_dir, "templates")

    if not os.path.isdir(template_dir):
        print_error(f"Template directory not found: {template_dir}")
        sys.exit(1)

    print_info(f"Template directory: {template_dir}")
    return template_dir


# File IO: reads replace broken bytes, writes always use LF regardless of OS
_READ_KWARGS = dict(encoding="utf-8", errors="replace")
_WRITE_KWARGS = dict(encoding="utf-8", newline="\n")

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


# Accept only the same values as the workflow's store_deploy_config.py. Silently passing a typo
# would deploy in a different mode while believing the setting applied — this setting even decides automatic production review submission.
DEPLOY_MODES = ("store_only", "store_prepare", "store_submit")


def validate_deploy_config(ctx):
    mode, rollout = ctx.get("DEPLOY_MODE", ""), ctx.get("PRODUCTION_ROLLOUT", "")
    if mode and mode not in DEPLOY_MODES:
        print_error(f"Invalid --deploy-mode value '{mode}'. It must be one of {' | '.join(DEPLOY_MODES)}.")
        sys.exit(1)
    if rollout:
        try:
            ok = 0 < float(rollout) <= 1
        except ValueError:
            ok = False
        if not ok:
            print_error(f"--production-rollout value '{rollout}' must be a number greater than 0 and at most 1.0 (e.g. 1.0, 0.1).")
            sys.exit(1)


def create_store_deploy_config(ctx):
    """Record the deploy mode and rollout fraction in the android section of .github/config/store-deploy.json (#767).

    Does nothing without the flags. An existing file is not deleted; only the android section is merged —
    the ios section or keys the user wrote must not be lost. The template does not ship this file, so updates never overwrite it.
    """
    mode, rollout = ctx.get("DEPLOY_MODE", ""), ctx.get("PRODUCTION_ROLLOUT", "")
    if not mode and not rollout:
        return
    print_step("Writing store-deploy.json...")
    cfg_dir = os.path.join(ctx["PROJECT_PATH"], ".github", "config")
    cfg_path = os.path.join(cfg_dir, "store-deploy.json")
    data = {}
    if path_exists(cfg_path):
        try:
            data = json.loads(read_text(cfg_path))
        except ValueError:
            print_error(f"{cfg_path} is not valid JSON. Fix it by hand and run again.")
            sys.exit(1)
        if not isinstance(data, dict):
            print_error(f"The top level of {cfg_path} must be an object.")
            sys.exit(1)
        backup_file(cfg_path)
    android = data.get("android") if isinstance(data.get("android"), dict) else {}
    if mode:
        android["deploy_mode"] = mode
    if rollout:
        android["production_rollout"] = rollout
    data["android"] = android
    make_dirs(cfg_dir)
    write_text(cfg_path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print_success(f"store-deploy.json written (android: {', '.join(f'{k}={v}' for k, v in android.items())})")


def update_gitignore(ctx):
    print_step("Updating .gitignore...")

    project_path = ctx["PROJECT_PATH"]

    # Check for a Git repository
    if not os.path.isdir(os.path.join(project_path, ".git")):
        print_info("Not a Git repository. Skipping the .gitignore update.")
        return

    gitignore_path = os.path.join(project_path, ".gitignore")
    android_gitignore_path = os.path.join(project_path, "android", ".gitignore")
    gitignore_updated = False

    # Handle the root .gitignore (only when the file exists)
    # sh/ps1 branch: ps1 had 4 entries (including "# Android signing"), but sh's 7 entries were adopted.
    if path_exists(gitignore_path):
        gitignore_entries = [
            "android/key.properties",
            "android/app/keystore/",
            "*.jks",
            "*.keystore",
            ".env",
            ".env.local",
            ".env.*.local",
        ]

        content = read_text(gitignore_path)
        for entry in gitignore_entries:
            if entry not in content:  # equivalent of grep -qF (fixed-string partial match)
                appended = f"\n# Play Store CI/CD - 민감한 파일 (자동 생성됨)\n{entry}\n"
                append_text(gitignore_path, appended)
                content += appended
                print_info(f"Added to the root .gitignore: {entry}")
                gitignore_updated = True
    # Do not create a root .gitignore if missing (the project may not use Git)

    # Handle android/.gitignore
    if path_exists(android_gitignore_path):
        # Check and add entries
        if "key.properties" not in read_text(android_gitignore_path):
            append_text(
                android_gitignore_path,
                "\n# Play Store Keystore (자동 생성됨)\nkey.properties\nkeystore/\n",
            )
            print_info("Added to android/.gitignore")
            gitignore_updated = True
    else:
        # Create android/.gitignore if missing
        make_dirs(os.path.join(project_path, "android"))
        write_text(android_gitignore_path, """# Play Store CI/CD - 민감한 파일 (자동 생성됨)
key.properties
keystore/
*.jks
*.keystore

# 환경 변수 파일
.env
.env.local
.env.*.local
""")
        print_info("Created android/.gitignore")
        gitignore_updated = True

    if gitignore_updated:
        print_success(".gitignore updated")
    else:
        print_info(".gitignore already has every entry.")


def _git(project_path, args, quiet_stdout=False, quiet_stderr=True):
    """Run git -C PROJECT_PATH .... Like sh, hides only stderr by default."""
    kwargs = {}
    if quiet_stdout:
        kwargs["stdout"] = subprocess.DEVNULL
    if quiet_stderr:
        kwargs["stderr"] = subprocess.DEVNULL
    try:
        return subprocess.run(["git", "-C", project_path] + args, **kwargs).returncode
    except OSError:
        return 1


def commit_gitignore(ctx):
    print_step("Committing the .gitignore changes...")

    project_path = ctx["PROJECT_PATH"]

    # Check for a Git repository
    if not os.path.isdir(os.path.join(project_path, ".git")):
        print_info("Not a Git repository. Skipping the commit.")
        return

    # Check that the Git command is available
    if shutil.which("git") is None:
        print_warning("Git is not installed. Skipping the commit.")
        return

    gitignore_path = os.path.join(project_path, ".gitignore")
    android_gitignore_path = os.path.join(project_path, "android", ".gitignore")
    has_changes = False

    # Check .gitignore changes
    if path_exists(gitignore_path):
        if _git(project_path, ["diff", "--quiet", gitignore_path]) != 0:
            has_changes = True

    if path_exists(android_gitignore_path):
        if _git(project_path, ["diff", "--quiet", android_gitignore_path]) != 0:
            has_changes = True

    if has_changes:
        # Remove already tracked files (if any)
        key_properties = os.path.join(project_path, "android", "key.properties")
        keystore_jks = os.path.join(project_path, "android", "app", "keystore", "key.jks")

        if _git(project_path, ["ls-files", "--error-unmatch", key_properties],
                quiet_stdout=True) == 0:
            print_warning("Removing the already tracked key.properties from Git...")
            _git(project_path, ["rm", "--cached", key_properties])

        if _git(project_path, ["ls-files", "--error-unmatch", keystore_jks],
                quiet_stdout=True) == 0:
            print_warning("Removing the already tracked keystore files from Git...")
            _git(project_path, ["rm", "--cached", keystore_jks])

        # Commit .gitignore
        if path_exists(gitignore_path):
            _git(project_path, ["add", gitignore_path])
        if path_exists(android_gitignore_path):
            _git(project_path, ["add", android_gitignore_path])

        if _git(project_path, ["diff", "--cached", "--quiet"]) == 0:
            print_info("No .gitignore changes (already committed).")
        else:
            # sh/ps1 branch: the commit messages differed
            #   (ps1: "chore: Update .gitignore for Android signing files") — sh text adopted.
            if _git(project_path, ["commit", "-m", "chore: Add keystore files to .gitignore"]) == 0:
                print_success(".gitignore changes committed")
            else:
                print_warning("Commit failed (already committed or nothing to commit)")
    else:
        print_info("No .gitignore changes.")


def create_keystore(ctx):
    print_step("Creating the keystore...")

    project_path = ctx["PROJECT_PATH"]
    keystore_dir = os.path.join(project_path, "android", "app", "keystore")
    keystore_path = os.path.join(keystore_dir, "key.jks")

    # Create the directory
    make_dirs(keystore_dir)

    # Check for an existing keystore
    if path_exists(keystore_path):
        print_info(f"A keystore already exists: {keystore_path}")
        print_info("Overwriting the existing keystore...")

        # Try deleting the alias from the existing keystore (before deleting the file)
        print_info("Trying to delete the alias from the existing keystore...")
        try:
            delete_rc = subprocess.run(
                ["keytool", "-delete",
                 "-alias", ctx["KEY_ALIAS"],
                 "-keystore", keystore_path,
                 "-storepass", ctx["STORE_PASSWORD"]],
                stderr=subprocess.DEVNULL,
            ).returncode
        except OSError:
            delete_rc = 1
        if delete_rc == 0:
            print_info("The existing alias was deleted from the keystore")
        else:
            print_warning("Could not delete the alias from the keystore (it may not exist or the password may differ)")
            print_warning("Trying to delete or replace the file...")

        # Delete the backup file if present
        backup_path = keystore_path + ".bak"
        if path_exists(backup_path):
            remove_file(backup_path)

        # Try backing up the file
        try:
            move_file(keystore_path, backup_path)
            print_info(f"Backed up the existing keystore: {backup_path}")
        except OSError:
            # If the file is locked, kill processes and retry
            print_warning("Could not move the keystore file. Trying to stop processes using the file...")

            if stop_processes_using_file(keystore_path):
                try:
                    remove_file(keystore_path)
                    print_info("Deleted the existing keystore (after stopping processes)")
                except OSError:
                    print_error(f"Still could not delete the keystore file after stopping processes: {keystore_path}")
                    print_error("Delete the file by hand or close the program that is using it.")
                    sys.exit(1)
            else:
                print_error(f"Could not delete the keystore file: {keystore_path}")
                print_error("Delete the file by hand or close the program that is using it.")
                sys.exit(1)

    # Build the keytool command
    dname = f"CN={ctx['CERT_CN']}, O={ctx['CERT_O']}, L={ctx['CERT_L']}, C={ctx['CERT_C']}"

    print_info("Keystore details:")
    print_info(f"  • Path: {keystore_path}")
    print_info(f"  • Alias: {ctx['KEY_ALIAS']}")
    print_info(f"  • Validity: {ctx['VALIDITY_DAYS']} days")
    print_info(f"  • Certificate: {dname}")

    # Run keytool (password passed via stdin)
    # sh/ps1 branch: ps1 used -genkeypair without stdin, but sh's -genkey + stdin was adopted.
    #   Like sh, lines containing "Warning:" in the output are hidden.
    stdin_text = (
        f"{ctx['STORE_PASSWORD']}\n{ctx['STORE_PASSWORD']}\n"
        f"{ctx['KEY_PASSWORD']}\n{ctx['KEY_PASSWORD']}\n{dname}\ny\n\n"
    )
    if DRY_RUN:
        _dry(f"create keystore (keytool): {keystore_path} (alias={ctx['KEY_ALIAS']}, {ctx['VALIDITY_DAYS']} days)")
        _DRY_FS[keystore_path] = "<dry-run keystore>"
        _DRY_DELETED.discard(keystore_path)
        print_success("Keystore created (dry-run — no real file)")
        return

    try:
        proc = subprocess.run(
            ["keytool", "-genkey", "-v",
             "-keystore", keystore_path,
             "-alias", ctx["KEY_ALIAS"],
             "-keyalg", "RSA",
             "-keysize", "2048",
             "-validity", ctx["VALIDITY_DAYS"],
             "-storepass", ctx["STORE_PASSWORD"],
             "-keypass", ctx["KEY_PASSWORD"],
             "-dname", dname],
            input=stdin_text,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            # sh streamed keytool's output bytes as is — decoding with the locale encoding (mac: UTF-8,
            # Korean Windows: cp949) is the closest behavior.
            text=True, errors="replace",
        )
        for line in (proc.stdout or "").splitlines():
            if "Warning:" not in line:
                print(line)
    except OSError as e:
        # The case where sh's shell prints "command not found" — show the original error as is
        print(str(e))

    if path_exists(keystore_path):
        print_success(f"Keystore created: {keystore_path}")
    else:
        print_error("Failed to create the keystore!")
        sys.exit(1)


def create_key_properties(ctx):
    print_step("Creating key.properties...")

    # If keystore creation was skipped, skip key.properties too
    if KEYSTORE_SKIPPED:
        print_warning("Skipping key.properties (the keystore was not overwritten)")
        print_warning("⚠️ The existing keystore is used, so check the passwords in key.properties by hand!")
        print_warning("   Enter the existing keystore passwords in android/key.properties.")
        print_warning("   Or go back to Step 2 and create the keystore again with overwrite (y).")
        return

    key_properties_path = os.path.join(ctx["PROJECT_PATH"], "android", "key.properties")

    # Back up and delete the existing file
    if path_exists(key_properties_path):
        print_info("Found an existing key.properties. Overwriting...")
        backup_path = key_properties_path + ".bak"

        # Delete the backup file if present
        if path_exists(backup_path):
            remove_file(backup_path)

        # Try backing up the file
        try:
            copy_file(key_properties_path, backup_path)
            remove_file(key_properties_path)
            print_info(f"Backed up the existing key.properties: {backup_path}")
        except OSError:
            # If the file is locked, kill processes and retry
            print_warning("Could not back up or delete key.properties. Trying to stop processes using the file...")

            if stop_processes_using_file(key_properties_path):
                try:
                    remove_file(key_properties_path)
                    print_info("Deleted the existing key.properties (after stopping processes)")
                except OSError:
                    print_error(f"Still could not delete key.properties after stopping processes: {key_properties_path}")
                    print_error("Delete the file by hand or close the program that is using it.")
                    sys.exit(1)
            else:
                print_error(f"Could not delete key.properties: {key_properties_path}")
                print_error("Delete the file by hand or close the program that is using it.")
                sys.exit(1)

    # sh/ps1 branch: ps1 wrote different content starting at storePassword without comments — sh content adopted.
    key_properties_content = f"""# Release Keystore Configuration
# WARNING: Do not commit this file to version control!
# This file is automatically generated by Play Store Wizard

storeFile=app/keystore/key.jks
storePassword={ctx['STORE_PASSWORD']}
keyAlias={ctx['KEY_ALIAS']}
keyPassword={ctx['KEY_PASSWORD']}
"""

    # Try writing the file
    try:
        write_text(key_properties_path, key_properties_content)
    except OSError:
        # If the file is locked, kill processes and retry
        print_warning("Could not write key.properties. Trying to stop processes using the file...")

        if stop_processes_using_file(key_properties_path):
            try:
                write_text(key_properties_path, key_properties_content)
                print_info("Wrote key.properties after stopping processes")
            except OSError:
                print_error("Still could not write key.properties after stopping processes")
                print_error("The file may still be locked. Close the program that is using it and try again.")
                sys.exit(1)
        else:
            print_error("Could not write key.properties")
            print_error("Another process may be using the file. Close the program that is using it and try again.")
            sys.exit(1)

    # Check the file was created properly
    if not path_exists(key_properties_path):
        print_error(f"key.properties was not created: {key_properties_path}")
        sys.exit(1)

    # Check the file content
    if "storePassword" not in read_text(key_properties_path):
        print_error(f"key.properties exists but its content is invalid: {key_properties_path}")
        sys.exit(1)

    print_success(f"key.properties created: {key_properties_path}")
    print_info(f"  • Store Password: {ctx['STORE_PASSWORD']}")
    print_info(f"  • Key Alias: {ctx['KEY_ALIAS']}")
    print_info(f"  • Key Password: {ctx['KEY_PASSWORD']}")


def patch_build_gradle_step(ctx):
    print_step("Adding the signing config to build.gradle.kts...")

    gradle_file = os.path.join(ctx["PROJECT_PATH"], "android", "app", "build.gradle.kts")

    if not path_exists(gradle_file):
        print_error(f"build.gradle.kts not found: {gradle_file}")
        sys.exit(1)

    # The old sh's patch script existence check + Python executable detection became unnecessary after absorbing it as an inner function.
    # sh/ps1 branch: ps1 had its own regex patch (subtly different text/patterns),
    #   but the patch py logic sh called (patch_build_gradle above) was adopted as is.
    try:
        success = patch_build_gradle(gradle_file)
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        success = False

    if not success:
        # Because of set -e, the old sh ended with exit code 1 and no extra message when the patch failed — kept the same.
        sys.exit(1)

    print_success("build.gradle.kts configured!")


def create_fastfile(ctx, template_dir):
    print_step("Creating Fastfile.playstore...")

    fastlane_dir = os.path.join(ctx["PROJECT_PATH"], "android", "fastlane")
    fastfile_path = os.path.join(fastlane_dir, "Fastfile.playstore")
    template_fastfile = os.path.join(template_dir, "Fastfile.playstore.template")

    # Create the fastlane directory
    make_dirs(fastlane_dir)

    # Back up the existing file
    if path_exists(fastfile_path):
        print_warning(f"Backing up existing Fastfile.playstore: {fastfile_path}.bak")
        backup_file(fastfile_path)

    # Check the template file exists
    if path_exists(template_fastfile):
        # Copy from the template and substitute placeholders
        write_text(
            fastfile_path,
            read_text(template_fastfile).replace("{{APPLICATION_ID}}", ctx["APPLICATION_ID"]),
        )
        print_info("Created from the template")
    else:
        # No template: create it directly
        # Note: the old sh heredoc printed the backslash in \#{...} as is (verified in bash) — kept byte-identical.
        # sh/ps1 branch: the ps1 fallback was entirely different content without package_name — sh content adopted.
        write_text(fastfile_path, f"""# Fastfile for Play Store Internal Testing Deployment
# Path: android/fastlane/Fastfile.playstore
# Generated by Flutter Play Store CI/CD Helper

default_platform(:android)

platform :android do
  desc "Deploy to Play Store Internal Testing"
  lane :deploy_internal do
    # Environment variables
    aab_path = ENV["AAB_PATH"] || "../build/app/outputs/bundle/release/app-release.aab"
    json_key = ENV["GOOGLE_PLAY_JSON_KEY"] || "~/.config/gcloud/service-account.json"

    puts "========================================="
    puts "Deploying to Play Store Internal Testing"
    puts "========================================="
    puts "AAB Path: \\#{{aab_path}}"
    puts "Service Account: \\#{{json_key}}"
    puts ""

    # Verify AAB exists
    unless File.exist?(aab_path)
      UI.user_error!("AAB file not found: \\#{{aab_path}}")
    end

    # Verify Service Account exists
    unless File.exist?(json_key)
      UI.user_error!("Service Account JSON not found: \\#{{json_key}}")
    end

    # Upload to Play Store
    # ⚠️ release_status 설정 가이드:
    #   - "draft": 앱이 Play Console에서 아직 한 번도 출시되지 않은 경우 (신규 앱)
    #   - "completed": 앱이 이미 Play Console에서 검토 완료되어 활성화된 경우
    # 신규 앱은 반드시 "draft"로 시작해야 합니다.
    upload_to_play_store(
      package_name: "{ctx['APPLICATION_ID']}",
      track: "internal",
      aab: aab_path,
      json_key: json_key,
      skip_upload_metadata: true,
      skip_upload_images: true,
      skip_upload_screenshots: true,
      release_status: "draft"  # 신규 앱: "draft" → 승인 후: "completed"로 변경
    )

    puts ""
    puts "========================================="
    puts "Successfully deployed to Internal Testing!"
    puts "========================================="
  end
end
""")

    print_success(f"Fastfile.playstore created: {fastfile_path}")
    print_info("  → The GitHub Actions workflow uses this file directly")


def create_gemfile(ctx):
    print_step("Creating Gemfile...")

    gemfile_path = os.path.join(ctx["PROJECT_PATH"], "android", "Gemfile")

    # Back up the existing file
    if path_exists(gemfile_path):
        print_warning(f"Backing up existing Gemfile: {gemfile_path}.bak")
        backup_file(gemfile_path)

    # sh/ps1 branch: ps1 lacked the "# frozen_string_literal: true" line — sh content adopted.
    write_text(gemfile_path, """# frozen_string_literal: true

source "https://rubygems.org"

# Fastlane - Android 빌드 자동화
gem "fastlane", "~> 2.225"

# multi_json - google-apis transitive 의존성이 gemspec에 선언 누락한 upstream 버그 회피 (Gem::LoadError 방지)
gem "multi_json"
""")

    print_success(f"Gemfile created: {gemfile_path}")


def print_completion(ctx):
    # sh/ps1 branch: ps1 had different content (English summary + base64 notes, etc.) — sh text adopted.
    print("")
    print(f"{GREEN}╔════════════════════════════════════════════════════════════════╗{NC}")
    print(f"{GREEN}║          🎉 Android Play Store deployment setup complete! 🎉  ║{NC}")
    print(f"{GREEN}╚════════════════════════════════════════════════════════════════╝{NC}")
    print("")
    print(f"{YELLOW}★ Wizard-first architecture ★{NC}")
    print("  Setup is complete. The workflows use these files as they are.")
    print("")
    print(f"{CYAN}Files created or modified:{NC}")
    print("  ✅ android/.gitignore                    (.gitignore update)")
    print("  ✅ android/app/keystore/key.jks         (keystore) ★")
    print("  ✅ android/key.properties               (signing info) ★")
    print("  ✅ android/app/build.gradle.kts         (signing config patch) ★")
    print("  ✅ android/fastlane/Fastfile.playstore  (Play Store upload) ★")
    print("  ✅ android/Gemfile                      (Fastlane dependencies)")
    print("")
    print(f"{CYAN}Configured values:{NC}")
    print(f"  • Application ID: {ctx['APPLICATION_ID']}")
    print(f"  • Key Alias: {ctx['KEY_ALIAS']}")
    print(f"  • Keystore validity: {ctx['VALIDITY_DAYS']} days")
    print("")
    print(f"{CYAN}Build pipeline:{NC}")
    print("  1. flutter build appbundle (create the AAB)")
    print("  2. fastlane deploy_internal (uses Fastfile.playstore)")
    print("")
    print(f"{YELLOW}Next steps:{NC}")
    print("  1. Set up GitHub Secrets:")
    print("     • RELEASE_KEYSTORE_BASE64 (the keystore file, base64-encoded)")
    print("     • RELEASE_KEYSTORE_PASSWORD")
    print("     • RELEASE_KEY_ALIAS")
    print("     • RELEASE_KEY_PASSWORD")
    print("     • GOOGLE_PLAY_SERVICE_ACCOUNT_JSON_BASE64")
    print("")
    print("  2. Commit the other changes (if needed):")
    print("     git add android/")
    print("     git commit -m \"chore: set up Android Play Store deployment\"")
    print("     (Note: .gitignore was already committed automatically)")
    print("")
    print("  3. Push to the deploy branch to test the build")
    print("")
    print("🎛️  Deploy mode (optional):")
    print("   Set ANDROID_DEPLOY_MODE in the GitHub repo Variables to choose the default deploy scope.")
    print("     store_only    : upload to internal testing only (default)")
    print("     store_prepare : promote to a production draft (waits for 'Start rollout' in the console)")
    print("     store_submit  : send to production review automatically (available after the first release is done by hand)")
    print("   When you run the workflow manually, the deploy_mode input overrides this variable.")
    print("")
    print("🛤️  Testing track promotion (optional · independent of the deploy mode):")
    print("     ANDROID_PROMOTE_TO_CLOSED_TESTING=true  also release to the closed testing track")
    print("     ANDROID_PROMOTE_TO_OPEN_TESTING=true    also release to the open testing track")
    print("     ANDROID_CLOSED_TESTING_TRACK            closed track name (default alpha)")
    print("     ANDROID_OPEN_TESTING_TRACK              open track name (default beta)")
    print("")
    print("   ⚠️  For personal developer accounts created after 2023-11-13, closed testing is effectively required.")
    print("      You get production access only after a closed test with at least 12 testers for at least 14 days,")
    print("      and the internal testing track that the default deploy reaches does not count toward it.")
    print("      (Accounts created before that date and organization accounts are not affected.)")


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
    print(f"{CYAN}║       Flutter Android Play Store setup script                  ║{NC}")
    print(f"{CYAN}╚════════════════════════════════════════════════════════════════╝{NC}")
    print("")

    # Check help options
    if params and params[0] in ("-h", "--help"):
        show_help()
        sys.exit(0)

    # Normalize named flags → positional (both old and new call forms supported)
    global DRY_RUN, NO_BACKUP
    params, cli_opts = normalize_params(params, ("project-path", "application-id", "key-alias", "store-password", "key-password", "validity-days", "cert-cn", "cert-o", "cert-l", "cert-c", "deploy-mode", "production-rollout"))
    DRY_RUN = cli_opts["dry_run"]
    NO_BACKUP = not cli_opts["backup"]
    if DRY_RUN:
        print(f"{YELLOW}⚠️  dry-run mode — no files are created or changed.{NC}")
        print("")

    # Validate parameters
    ctx = validate_params(params)
    # Optional flags (#767): record the deploy mode and rollout fraction in the code config (store-deploy.json).
    # Old positional calls have only 10, so these are empty then, and nothing is written.
    ctx["DEPLOY_MODE"] = (params[10] if len(params) > 10 else "").strip()
    ctx["PRODUCTION_ROLLOUT"] = (params[11] if len(params) > 11 else "").strip()
    validate_deploy_config(ctx)   # before side effects (keystore creation, etc.) — typos stop here

    print(f"{BLUE}Project path:{NC} {ctx['PROJECT_PATH']}")
    print(f"{BLUE}Application ID:{NC} {ctx['APPLICATION_ID']}")
    print(f"{BLUE}Key Alias:{NC} {ctx['KEY_ALIAS']}")
    print(f"{BLUE}Validity:{NC} {ctx['VALIDITY_DAYS']} days")
    print("")

    # Find the template directory
    template_dir = find_template_dir()

    # Create files (order matters!)
    update_gitignore(ctx)       # 1. update .gitignore first
    commit_gitignore(ctx)       # 2. commit .gitignore (before creating the keystore!)
    create_keystore(ctx)        # 3. now create the keystore (safe)
    create_key_properties(ctx)
    patch_build_gradle_step(ctx)
    create_fastfile(ctx, template_dir)
    create_gemfile(ctx)
    create_store_deploy_config(ctx)

    # Done
    print_completion(ctx)


# ===================================================================
# apply subcommand (old apply script — sh canonical)
# Runs at the project root (cwd). The config_json_file argument is accepted like the old sh but unused.
# ===================================================================


def _sed_double_quoted_greedy(line):
    """Equivalent of sed 's/.*"\\(.*\\)".*/\\1/' — returns the original line unchanged when there is no match."""
    return re.sub(r'.*"(.*)".*', r'\1', line, count=1)


def cmd_apply(params):
    # params: [config_json_file] — the old sh did not read the argument either (only in usage).
    print(f"{BLUE}========================================={NC}")
    print(f"{BLUE} Flutter Play Store CI/CD Auto Apply{NC}")
    print(f"{BLUE}========================================={NC}")
    print("")

    # Check if we're in a Flutter project
    if not path_exists("pubspec.yaml"):
        print(f"{RED}Error: This is not a Flutter project directory{NC}")
        print("Please run this script from your Flutter project root.")
        sys.exit(1)

    # Create necessary directories
    # sh/ps1 branch: ps1 printed "Exists:" when present, but sh always printed Created — sh adopted.
    print(f"{YELLOW}[1/5] Creating directories...{NC}")
    make_dirs("android/app/keystore")
    make_dirs("android/fastlane")
    make_dirs("android/fastlane/metadata/android/ko-KR/changelogs")
    print(f"{GREEN}  Created: android/app/keystore/{NC}")
    print(f"{GREEN}  Created: android/fastlane/{NC}")
    print(f"{GREEN}  Created: android/fastlane/metadata/android/ko-KR/changelogs/{NC}")

    # Detect gradle type
    print(f"{YELLOW}[2/5] Detecting Gradle configuration...{NC}")
    if path_exists("android/app/build.gradle.kts"):
        gradle_file = "android/app/build.gradle.kts"
        gradle_type = "kts"
        print(f"{GREEN}  Detected: Kotlin DSL (build.gradle.kts){NC}")
    elif path_exists("android/app/build.gradle"):
        gradle_file = "android/app/build.gradle"
        gradle_type = "groovy"
        print(f"{GREEN}  Detected: Groovy DSL (build.gradle){NC}")
    else:
        print(f"{RED}Error: Cannot find build.gradle file{NC}")
        sys.exit(1)

    # Create Fastfile.playstore if not exists
    print(f"{YELLOW}[3/5] Creating Fastlane configuration...{NC}")
    if not path_exists("android/fastlane/Fastfile.playstore"):
        # Get applicationId from build.gradle
        gradle_lines = read_text(gradle_file).splitlines()
        app_id = ""
        if gradle_type == "kts":
            matched = [l for l in gradle_lines if re.search(r'applicationId\s*=', l)]
        else:
            matched = [l for l in gradle_lines if re.search(r'applicationId\s', l)]
        if matched:
            app_id = _sed_double_quoted_greedy(matched[0])

        write_text("android/fastlane/Fastfile.playstore", f"""# Fastfile for Play Store Internal Testing Deployment
# Path: android/fastlane/Fastfile.playstore
# Generated by Flutter Play Store CI/CD Helper

default_platform(:android)

platform :android do
  desc "Deploy to Play Store Internal Testing"
  lane :deploy_internal do
    # Environment variables
    aab_path = ENV["AAB_PATH"] || "../build/app/outputs/bundle/release/app-release.aab"
    json_key = ENV["GOOGLE_PLAY_JSON_KEY"] || "~/.config/gcloud/service-account.json"

    puts "========================================="
    puts "Deploying to Play Store Internal Testing"
    puts "========================================="
    puts "AAB Path: #{{aab_path}}"
    puts "Service Account: #{{json_key}}"
    puts ""

    # Verify AAB exists
    unless File.exist?(aab_path)
      UI.user_error!("AAB file not found: #{{aab_path}}")
    end

    # Verify Service Account exists
    unless File.exist?(json_key)
      UI.user_error!("Service Account JSON not found: #{{json_key}}")
    end

    # Upload to Play Store
    upload_to_play_store(
      package_name: "{app_id}",
      track: "internal",
      aab: aab_path,
      json_key: json_key,
      skip_upload_metadata: true,
      skip_upload_images: true,
      skip_upload_screenshots: true,
      release_status: "completed"
    )

    puts ""
    puts "========================================="
    puts "Successfully deployed to Internal Testing!"
    puts "========================================="
  end

  desc "Validate Service Account JSON"
  lane :validate do
    json_key = ENV["GOOGLE_PLAY_JSON_KEY"] || "~/.config/gcloud/service-account.json"

    validate_play_store_json_key(
      json_key: json_key
    )

    puts "Service Account validation successful!"
  end

  desc "Promote internal to beta"
  lane :promote_to_beta do
    json_key = ENV["GOOGLE_PLAY_JSON_KEY"] || "~/.config/gcloud/service-account.json"

    upload_to_play_store(
      package_name: "{app_id}",
      track: "internal",
      track_promote_to: "beta",
      json_key: json_key,
      skip_upload_apk: true,
      skip_upload_aab: true,
      skip_upload_metadata: true,
      skip_upload_images: true,
      skip_upload_screenshots: true
    )

    puts "Promoted from internal to beta!"
  end
end
""")
        print(f"{GREEN}  Created: android/fastlane/Fastfile.playstore{NC}")
    else:
        print(f"{YELLOW}  Skipped: android/fastlane/Fastfile.playstore already exists{NC}")

    # Create key.properties template
    print(f"{YELLOW}[4/5] Creating key.properties template...{NC}")
    if not path_exists("android/key.properties"):
        write_text("android/key.properties", """# Release Keystore Configuration
# WARNING: Do not commit this file to version control!
# Add 'android/key.properties' to your .gitignore

storeFile=app/keystore/key.jks
storePassword=YOUR_STORE_PASSWORD
keyAlias=YOUR_KEY_ALIAS
keyPassword=YOUR_KEY_PASSWORD
""")
        print(f"{GREEN}  Created: android/key.properties (template){NC}")
        print(f"{YELLOW}  NOTE: Please update with your actual keystore credentials{NC}")
    else:
        print(f"{YELLOW}  Skipped: android/key.properties already exists{NC}")

    # Update .gitignore
    print(f"{YELLOW}[5/5] Updating .gitignore...{NC}")
    gitignore_entries = [
        "android/key.properties",
        "android/app/keystore/",
        "*.jks",
        "*.keystore",
    ]

    gitignore_content = read_text(".gitignore") if path_exists(".gitignore") else ""
    for entry in gitignore_entries:
        if entry not in gitignore_content:
            append_text(".gitignore", entry + "\n")
            gitignore_content += entry + "\n"
            print(f"{GREEN}  Added to .gitignore: {entry}{NC}")

    print("")
    print(f"{GREEN}========================================={NC}")
    print(f"{GREEN} Setup Complete!{NC}")
    print(f"{GREEN}========================================={NC}")
    print("")
    print(f"{BLUE}Next Steps:{NC}")
    print("1. Generate your release keystore:")
    print(f"   {YELLOW}keytool -genkey -v -keystore android/app/keystore/key.jks -keyalg RSA -keysize 2048 -validity 10000 -alias your-key-alias{NC}")
    print("")
    print("2. Update android/key.properties with your keystore credentials")
    print("")
    print("3. Modify android/app/build.gradle.kts to add signing configuration")
    print("   (See the HTML wizard for the exact code)")
    print("")
    print("4. Set up GitHub Secrets:")
    print("   - RELEASE_KEYSTORE_BASE64")
    print("   - RELEASE_KEYSTORE_PASSWORD")
    print("   - RELEASE_KEY_ALIAS")
    print("   - RELEASE_KEY_PASSWORD")
    print("   - GOOGLE_PLAY_SERVICE_ACCOUNT_JSON_BASE64")
    print("")
    print(f"{BLUE}For detailed instructions, open:{NC}")
    print("  .github/util/flutter/android-playstore-setup-wizard/index.html")


# ===================================================================
# detect-app-id subcommand (old detect script — sh canonical, JSON output)
# ===================================================================


def _detect_android_env_posix():
    """Old sh logic: mac/linux SDK search + automatic shell rc addition."""
    env_status = "ok"
    env_message = ""

    home = os.path.expanduser("~")
    android_home = os.environ.get("ANDROID_HOME", "")

    # Check ANDROID_HOME
    if not android_home:
        # Find the Android SDK in default paths
        if os.path.isdir(os.path.join(home, "Library", "Android", "sdk")):
            android_home = os.path.join(home, "Library", "Android", "sdk")
        elif os.path.isdir(os.path.join(home, "Android", "Sdk")):
            android_home = os.path.join(home, "Android", "Sdk")

    # If ANDROID_HOME is still missing, try setting it automatically
    if not android_home or not os.path.isdir(android_home):
        possible_paths = [
            os.path.join(home, "Library", "Android", "sdk"),
            os.path.join(home, "Android", "Sdk"),
            "/usr/local/share/android-sdk",
        ]
        for path in possible_paths:
            if os.path.isdir(path):
                android_home = path
                break

    # Add ANDROID_HOME to ~/.zshrc (if missing)
    if android_home and os.path.isdir(android_home):
        shell_rc = ""
        if path_exists(os.path.join(home, ".zshrc")):
            shell_rc = os.path.join(home, ".zshrc")
        elif path_exists(os.path.join(home, ".bashrc")):
            shell_rc = os.path.join(home, ".bashrc")
        elif path_exists(os.path.join(home, ".bash_profile")):
            shell_rc = os.path.join(home, ".bash_profile")

        if shell_rc:
            # Check that ANDROID_HOME is set
            if "export ANDROID_HOME" not in read_text(shell_rc):
                append_text(
                    shell_rc,
                    "\n# Android SDK (자동 추가됨 by playstore-wizard)\n"
                    f"export ANDROID_HOME=\"{android_home}\"\n"
                    "export PATH=\"$PATH:$ANDROID_HOME/platform-tools\"\n"
                    "export PATH=\"$PATH:$ANDROID_HOME/cmdline-tools/latest/bin\"\n",
                )
                env_message = f"Added ANDROID_HOME to {shell_rc}. Reopen the terminal or run source {shell_rc}"

        # Apply to the current session too
        os.environ["ANDROID_HOME"] = android_home
        os.environ["PATH"] = (
            os.environ.get("PATH", "")
            + os.pathsep + os.path.join(android_home, "platform-tools")
            + os.pathsep + os.path.join(android_home, "cmdline-tools", "latest", "bin")
        )
    else:
        env_status = "warning"
        env_message = "Android SDK not found. Open SDK Manager in Android Studio and install it."

    return env_status, env_message


def _detect_android_env_windows():
    """sh/ps1 branch: the sh SDK path is mac/linux only, so Windows adopts the ps1 logic
    (LOCALAPPDATA path search + permanent user env var registration)."""
    env_status = "ok"
    env_message = ""

    android_home = os.environ.get("ANDROID_HOME", "")

    if not android_home or not os.path.isdir(android_home):
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        user_profile = os.environ.get("USERPROFILE", "")
        possible_paths = [
            os.path.join(local_app_data, "Android", "Sdk") if local_app_data else "",
            os.path.join(user_profile, "AppData", "Local", "Android", "Sdk") if user_profile else "",
            "C:\\Android\\Sdk",
        ]
        for path in possible_paths:
            if path and os.path.isdir(path):
                android_home = path
                break

    if android_home and os.path.isdir(android_home):
        # Set env vars (current session)
        os.environ["ANDROID_HOME"] = android_home

        # Add to user env vars (permanent) - only if missing (equivalent of ps1's SetEnvironmentVariable)
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0,
                                winreg.KEY_READ | winreg.KEY_WRITE) as key:
                try:
                    winreg.QueryValueEx(key, "ANDROID_HOME")
                    has_user_var = True
                except FileNotFoundError:
                    has_user_var = False
                if not has_user_var:
                    winreg.SetValueEx(key, "ANDROID_HOME", 0, winreg.REG_SZ, android_home)
                    env_message = "Added ANDROID_HOME to your user environment variables. Reopen the terminal."
        except OSError as registry_error:
            env_message = f"Could not save ANDROID_HOME: {registry_error}. Set it manually."
    else:
        env_status = "warning"
        env_message = "Android SDK not found. Open SDK Manager in Android Studio and install it."

    return env_status, env_message


def cmd_detect_app_id(project_path):
    # Check the project path
    if not project_path:
        print('{"error": "Enter the project path", "env": "error"}')
        sys.exit(1)

    if not os.path.isdir(project_path):
        print('{"error": "The project path does not exist", "env": "error"}')
        sys.exit(1)

    # 1. Android SDK environment check and auto-setup
    if os.name == "nt":
        env_status, env_message = _detect_android_env_windows()
    else:
        env_status, env_message = _detect_android_env_posix()

    # 2. Check the keytool command
    keytool_status = "ok"
    if shutil.which("keytool") is None:
        # Check that Java is installed
        if shutil.which("java") is None:
            keytool_status = "error"
            env_status = "error"
            if os.name == "nt":
                # sh/ps1 branch: sh's brew hint is mac-only, so Windows adopts the ps1 text
                env_message = "Java is not installed. Install a JDK."
            else:
                env_message = "Java is not installed. Install a JDK: brew install openjdk"
        else:
            keytool_status = "warning"

    # 3. Extract the Application ID
    if path_exists(os.path.join(project_path, "android", "app", "build.gradle.kts")):
        gradle_file = os.path.join(project_path, "android", "app", "build.gradle.kts")
        gradle_type = "kts"
    elif path_exists(os.path.join(project_path, "android", "app", "build.gradle")):
        gradle_file = os.path.join(project_path, "android", "app", "build.gradle")
        gradle_type = "groovy"
    else:
        print('{"error": "build.gradle not found", "env": "error"}')
        sys.exit(1)

    gradle_lines = read_text(gradle_file).splitlines()
    application_id = ""

    # Kotlin DSL (build.gradle.kts)
    if gradle_type == "kts":
        matched = [l for l in gradle_lines if re.search(r'applicationId\s*=', l)]
        if matched:
            # Equivalent of sed 's/.*"\([^"]*\)".*/\1/' (line unchanged without a match — preserves sh behavior)
            application_id = re.sub(r'.*"([^"]*)".*', r'\1', matched[0], count=1)

    # Groovy (build.gradle)
    if not application_id:
        matched = [l for l in gradle_lines
                   if re.search(r'applicationId\s+', l) and "=" not in l]
        if matched:
            line = re.sub(r'.*"([^"]*)".*', r'\1', matched[0], count=1)
            line = re.sub(r".*'([^']*)'.*", r'\1', line, count=1)
            application_id = line

    # Try extracting from namespace
    if not application_id:
        matched = [l for l in gradle_lines if re.search(r'namespace\s*=', l)]
        if matched:
            application_id = re.sub(r'.*"([^"]*)".*', r'\1', matched[0], count=1)

    if not application_id:
        print('{"error": "applicationId not found", "env": "error"}')
        sys.exit(1)

    # 4. Print the result (JSON) — same manual format as the old sh
    if env_message:
        print(f'{{"applicationId": "{application_id}", "env": "{env_status}", "keytool": "{keytool_status}", "message": "{env_message}", "gradleType": "{gradle_type}"}}')
    else:
        print(f'{{"applicationId": "{application_id}", "env": "{env_status}", "keytool": "{keytool_status}", "gradleType": "{gradle_type}"}}')


# ===================================================================
# Entry point
# ===================================================================


def build_parser():
    parser = argparse.ArgumentParser(
        prog="playstore-wizard.py",
        description="Flutter Android Play Store wizard local script",
    )
    sub = parser.add_subparsers(dest="command")

    # setup handles -h/--help and positional arguments itself like the old sh (blocks argparse)
    p_setup = sub.add_parser(
        "setup", add_help=False,
        help="Initial Play Store deployment setup (keystore, key.properties, build.gradle.kts, Fastfile, Gemfile)",
    )
    p_setup.add_argument("params", nargs=argparse.REMAINDER)

    p_apply = sub.add_parser(
        "apply", add_help=False,
        help="Apply the generated setup to the Flutter project (run from the project root)",
    )
    p_apply.add_argument("params", nargs=argparse.REMAINDER)

    p_detect = sub.add_parser(
        "detect-app-id", add_help=False,
        help="Check the environment and detect applicationId (JSON output)",
    )
    p_detect.add_argument("params", nargs=argparse.REMAINDER)

    return parser


def main():
    # Arguments after the subcommand are handled as is by each command, like the old sh.
    # (argparse REMAINDER cannot swallow a leading "-h", so dispatch is manual)
    parser = build_parser()
    argv = sys.argv[1:]

    if not argv:
        parser.print_help()
        sys.exit(1)

    command, params = argv[0], argv[1:]

    if command == "setup":
        cmd_setup(params)
    elif command == "apply":
        cmd_apply(params)
    elif command == "detect-app-id":
        cmd_detect_app_id(params[0] if params else "")
    elif command in ("-h", "--help"):
        parser.print_help()
        sys.exit(0)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
