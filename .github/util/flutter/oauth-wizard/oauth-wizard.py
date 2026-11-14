#!/usr/bin/env python3
# ===================================================================
# OAuth Login Wizard - CLI (Python, stdlib only)
# ===================================================================
# Applies Kakao/Google login native setup to a Flutter project (#156).
#
# 4 subcommands
#   detect       : detect applicationId, bundle ID, config file locations, existing entries (JSON, read-only)
#   fingerprints : print keystore SHA-1, SHA-256 and Kakao key hash with keytool (JSON, read-only)
#   key-hash     : SHA-1 (hex) > Kakao key hash (base64) (JSON)
#   setup        : patch AndroidManifest.xml, Info.plist, .gitignore (idempotent)
#
# Usage:
#   python3 oauth-wizard.py setup --project-path . \
#     --kakao-native-app-key 0123456789abcdef0123456789abcdef \
#     --google-ios-client-id 1234-abc.apps.googleusercontent.com \
#     [--google-server-client-id 1234-web.apps.googleusercontent.com] \
#     [--update-gitignore] [--firebase-files] \
#     [--dry-run] [--non-interactive] [--no-backup]
#
# Order: validate input > compute all new content > (confirm) > back up > write
#   Computation finishes first, so if any one file has a problem nothing is changed.
# ===================================================================
import argparse
import base64
import binascii
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys

# ---- stdout/stderr UTF-8 (cp949 console support) ----
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _ansi_enabled():
    """Whether to print colors — off for pipes and NO_COLOR"""
    if os.environ.get("NO_COLOR"):
        return False
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


if _ansi_enabled():
    RED, GREEN, YELLOW, BLUE, NC = "\033[0;31m", "\033[0;32m", "\033[1;33m", "\033[0;34m", "\033[0m"
else:
    RED = GREEN = YELLOW = BLUE = NC = ""

# Preserve newlines (CRLF files are not converted to LF)
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


# ============================================
# Constants
# ============================================
MANIFEST_RELATIVE_PATH = "android/app/src/main/AndroidManifest.xml"
INFO_PLIST_RELATIVE_PATH = "ios/Runner/Info.plist"
GITIGNORE_RELATIVE_PATH = ".gitignore"
GRADLE_RELATIVE_PATHS = ("android/app/build.gradle.kts", "android/app/build.gradle")
PBXPROJ_RELATIVE_PATH = "ios/Runner.xcodeproj/project.pbxproj"

KAKAO_ACTIVITY_NAME = "com.kakao.sdk.flutter.auth.AuthCodeHandlerActivity"
# Kakao native app key: 32 hex characters
KAKAO_NATIVE_APP_KEY_RE = re.compile(r"^[0-9a-fA-F]{32}$")
KAKAO_URL_SCHEME_RE = re.compile(r"^kakao[0-9a-fA-F]{32}$")
# KakaoTalk login (kakaokompassauth) and sharing (kakaolink) — per developers.kakao.com iOS getting started
KAKAO_QUERIES_SCHEMES = ("kakaokompassauth", "kakaolink")
# Google OAuth client ID: {number}-{identifier}.apps.googleusercontent.com
GOOGLE_CLIENT_ID_RE = re.compile(r"^([0-9]+-[0-9a-z]+)\.apps\.googleusercontent\.com$")
GOOGLE_REVERSED_PREFIX = "com.googleusercontent.apps."

GITIGNORE_HEADER = "# OAuth wizard (projectops)"
# Wizard export file — contains Secret values as is
GITIGNORE_EXPORT_PATTERNS = ("oauth-secrets-*.json", "oauth-secrets-*.txt", "oauth-setup-*.zip")
# Firebase config files — CI recreates them from GitHub Secrets
GITIGNORE_FIREBASE_PATTERNS = ("android/app/google-services.json", "ios/Runner/GoogleService-Info.plist")


def print_info(message):
    print(f"{BLUE}[info]{NC} {message}")


def print_error(message):
    print(f"{RED}[error]{NC} {message}", file=sys.stderr)


def emit_json(payload):
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def detect_newline(content):
    return "\r\n" if "\r\n" in content else "\n"


# ============================================
# Detection (read-only)
# ============================================

def detect_application_id(project_path):
    """build.gradle(.kts) applicationId > value (None if missing)"""
    for relative_path in GRADLE_RELATIVE_PATHS:
        gradle_path = os.path.join(project_path, relative_path)
        if not os.path.exists(gradle_path):
            continue
        match = re.search(r"""applicationId\s*=?\s*["']([^"']+)["']""", read_text(gradle_path))
        if match:
            return {"value": match.group(1), "source": relative_path}
    return None


def detect_bundle_id(project_path):
    """project.pbxproj PRODUCT_BUNDLE_IDENTIFIER > app value (test targets excluded, most frequent value)"""
    pbxproj_path = os.path.join(project_path, PBXPROJ_RELATIVE_PATH)
    if not os.path.exists(pbxproj_path):
        return None
    values = re.findall(r'PRODUCT_BUNDLE_IDENTIFIER\s*=\s*"?([^";]+)"?;', read_text(pbxproj_path))
    app_values = [value.strip() for value in values if not value.strip().endswith("Tests")]
    if not app_values:
        return None
    most_common = max(set(app_values), key=app_values.count)
    return {"value": most_common, "source": PBXPROJ_RELATIVE_PATH}


def load_info_plist(content):
    """Info.plist string > dict (plistlib)"""
    return plistlib.loads(content.encode("utf-8"))


def collect_url_schemes(plist_data):
    schemes = []
    for url_type in plist_data.get("CFBundleURLTypes", []) or []:
        schemes.extend(url_type.get("CFBundleURLSchemes", []) or [])
    return schemes


def cmd_detect(args):
    """Detect app IDs, config files and existing OAuth entries > JSON"""
    project_path = os.path.abspath(args.project_path)
    manifest_path = os.path.join(project_path, MANIFEST_RELATIVE_PATH)
    plist_path = os.path.join(project_path, INFO_PLIST_RELATIVE_PATH)
    result = {
        "ok": True,
        "projectPath": project_path,
        "isFlutterProject": os.path.exists(os.path.join(project_path, "pubspec.yaml")),
        "applicationId": detect_application_id(project_path),
        "bundleId": detect_bundle_id(project_path),
        "androidManifest": {"path": MANIFEST_RELATIVE_PATH, "exists": os.path.exists(manifest_path)},
        "infoPlist": {"path": INFO_PLIST_RELATIVE_PATH, "exists": os.path.exists(plist_path)},
    }
    if result["androidManifest"]["exists"]:
        result["androidManifest"]["hasKakaoActivity"] = KAKAO_ACTIVITY_NAME in read_text(manifest_path)
    if result["infoPlist"]["exists"]:
        try:
            plist_data = load_info_plist(read_text(plist_path))
            schemes = collect_url_schemes(plist_data)
            result["infoPlist"]["urlSchemes"] = schemes
            result["infoPlist"]["hasGIDClientID"] = "GIDClientID" in plist_data
        except Exception as error:  # noqa: BLE001 — a broken plist is returned as a detection result too
            result["infoPlist"]["parseError"] = str(error)
    result["next"] = "setup --project-path <path> --kakao-native-app-key <key> / --google-ios-client-id <id>"
    emit_json(result)
    return 0


# ============================================
# Key fingerprints / Kakao key hash
# ============================================

def sha1_hex_to_key_hash(sha1_hex):
    """SHA-1 hex (colons allowed) > Kakao key hash base64 (same as xxd -r -p | openssl base64)"""
    cleaned = re.sub(r"[^0-9a-fA-F]", "", sha1_hex or "")
    if len(cleaned) != 40:
        raise ValueError("SHA-1 must be 40 hex characters (20 bytes), e.g. AA:BB:...:FF")
    return base64.b64encode(binascii.unhexlify(cleaned)).decode("ascii")


def cmd_key_hash(args):
    try:
        key_hash = sha1_hex_to_key_hash(args.sha1)
    except ValueError as error:
        emit_json({"ok": False, "error": str(error)})
        return 1
    emit_json({"ok": True, "sha1": args.sha1, "kakaoKeyHash": key_hash,
               "next": "Register kakaoKeyHash in Kakao Developers > App > Platform > Android"})
    return 0


def parse_keytool_fingerprints(output):
    """keytool -list -v output > {"sha1": ..., "sha256": ...}"""
    fingerprints = {}
    for label, key in (("SHA1", "sha1"), ("SHA256", "sha256")):
        match = re.search(rf"^\s*{label}:\s*([0-9A-Fa-f:]+)\s*$", output, re.M)
        if match:
            fingerprints[key] = match.group(1).upper()
    return fingerprints


def cmd_fingerprints(args):
    """Run keytool (read-only) > SHA-1, SHA-256, Kakao key hash"""
    keytool_path = shutil.which("keytool")
    if not keytool_path:
        emit_json({"ok": False, "error": "keytool not found. Install a JDK (Android Studio ships one) and add it to PATH."})
        return 1
    # Password: argument > env KEYSTORE_PASSWORD > debug key default
    store_password = args.storepass or os.environ.get("KEYSTORE_PASSWORD")
    if not store_password and args.alias == "androiddebugkey":
        store_password = "android"
    if not store_password:
        emit_json({"ok": False, "error": "Pass --storepass or set KEYSTORE_PASSWORD (release keystores have no default password)."})
        return 1
    command = [keytool_path, "-list", "-v", "-keystore", os.path.expanduser(args.keystore),
               "-alias", args.alias, "-storepass", store_password]
    completed = subprocess.run(command, capture_output=True, text=True, errors="replace")
    fingerprints = parse_keytool_fingerprints(completed.stdout)
    if completed.returncode != 0 or "sha1" not in fingerprints:
        message = (completed.stderr or completed.stdout).strip().splitlines()
        emit_json({"ok": False, "error": message[-1] if message else "keytool failed"})
        return 1
    emit_json({"ok": True, "keystore": args.keystore, "alias": args.alias,
               "sha1": fingerprints["sha1"], "sha256": fingerprints.get("sha256"),
               "kakaoKeyHash": sha1_hex_to_key_hash(fingerprints["sha1"]),
               "next": "Register SHA-1/SHA-256 in Firebase or Google Cloud, and kakaoKeyHash in Kakao Developers"})
    return 0


# ============================================
# setup: compute patches (in memory) — writes happen only in apply_changes
# ============================================

def to_reversed_client_id(ios_client_id):
    """iOS client ID > REVERSED_CLIENT_ID (com.googleusercontent.apps.{number}-{identifier})"""
    match = GOOGLE_CLIENT_ID_RE.match(ios_client_id)
    return GOOGLE_REVERSED_PREFIX + match.group(1)


def validate_setup_args(args):
    """Validate input > list of failure reasons (empty list passes)"""
    problems = []
    if not (args.kakao_native_app_key or args.google_ios_client_id or args.update_gitignore):
        problems.append("Nothing to do: pass --kakao-native-app-key and/or --google-ios-client-id (or --update-gitignore).")
    if args.kakao_native_app_key and not KAKAO_NATIVE_APP_KEY_RE.match(args.kakao_native_app_key):
        problems.append("--kakao-native-app-key must be the 32-character Native App Key (hex), not the REST API or JavaScript key.")
    for flag, value in (("--google-ios-client-id", args.google_ios_client_id),
                        ("--google-server-client-id", args.google_server_client_id)):
        if value and not GOOGLE_CLIENT_ID_RE.match(value):
            problems.append(f"{flag} must look like 1234567890-abc123.apps.googleusercontent.com")
    if args.google_server_client_id and not args.google_ios_client_id:
        problems.append("--google-server-client-id needs --google-ios-client-id (both go into Info.plist).")
    return problems


def build_kakao_activity_block(native_app_key, indent, newline):
    """AuthCodeHandlerActivity block (same markup as developers.kakao.com Flutter getting started)"""
    inner = indent + "    "
    lines = [
        f'{indent}<activity',
        f'{inner}android:name="{KAKAO_ACTIVITY_NAME}"',
        f'{inner}android:exported="true">',
        f'{inner}<intent-filter android:label="flutter_web_auth">',
        f'{inner}    <action android:name="android.intent.action.VIEW" />',
        f'{inner}    <category android:name="android.intent.category.DEFAULT" />',
        f'{inner}    <category android:name="android.intent.category.BROWSABLE" />',
        f'{inner}    <data android:scheme="kakao{native_app_key}" android:host="oauth" />',
        f'{inner}</intent-filter>',
        f'{indent}</activity>',
    ]
    return newline.join(lines) + newline


def patch_manifest(content, native_app_key):
    """AndroidManifest.xml > (new content, change descriptions). Content unchanged if already the same"""
    newline = detect_newline(content)
    scheme = f"kakao{native_app_key}"
    activity_match = re.search(
        rf"<activity\b[^>]*{re.escape(KAKAO_ACTIVITY_NAME)}.*?</activity>", content, re.S)
    if activity_match:
        block = activity_match.group(0)
        scheme_match = re.search(r'android:scheme="(kakao[^"]*)"', block)
        if scheme_match and scheme_match.group(1) == scheme:
            return content, []
        if scheme_match:
            new_block = block.replace(scheme_match.group(0), f'android:scheme="{scheme}"')
            note = f"updated Kakao URL scheme {scheme_match.group(1)} -> {scheme}"
        else:
            # An activity without a scheme is a block someone edited by hand — fail instead of overwriting
            raise ValueError(f"{KAKAO_ACTIVITY_NAME} exists but has no kakao scheme; fix it by hand")
        start, end = activity_match.span()
        return content[:start] + new_block + content[end:], [note]

    closing_index = content.rfind("</application>")
    if closing_index == -1:
        raise ValueError("no </application> tag found")
    line_start = content.rfind("\n", 0, closing_index) + 1
    closing_indent = content[line_start:closing_index]
    if closing_indent.strip():
        closing_indent = ""
    block = build_kakao_activity_block(native_app_key, closing_indent + "    ", newline)
    new_content = content[:line_start] + block + content[line_start:]
    return new_content, [f"added Kakao AuthCodeHandlerActivity (scheme {scheme}, host oauth)"]


def upsert_url_scheme(plist_data, scheme, is_same_provider):
    """Ensure the scheme in CFBundleURLTypes. Replace if the same provider's scheme differs > change description"""
    url_types = plist_data.setdefault("CFBundleURLTypes", [])
    for url_type in url_types:
        schemes = url_type.get("CFBundleURLSchemes", []) or []
        for index, existing in enumerate(schemes):
            if existing == scheme:
                return None
            if is_same_provider(existing):
                schemes[index] = scheme
                return f"updated URL scheme {existing} -> {scheme}"
    url_types.append({"CFBundleTypeRole": "Editor", "CFBundleURLSchemes": [scheme]})
    return f"added URL scheme {scheme}"


def patch_info_plist(content, args):
    """Info.plist > (new content, change descriptions)"""
    plist_data = load_info_plist(content)
    notes = []

    # Kakao: URL scheme kakao{key} + KakaoTalk app query allow list
    if args.kakao_native_app_key:
        notes.append(upsert_url_scheme(plist_data, f"kakao{args.kakao_native_app_key}",
                                       lambda existing: bool(KAKAO_URL_SCHEME_RE.match(existing))))
        queries = plist_data.setdefault("LSApplicationQueriesSchemes", [])
        missing = [scheme for scheme in KAKAO_QUERIES_SCHEMES if scheme not in queries]
        if missing:
            queries.extend(missing)
            notes.append(f"added LSApplicationQueriesSchemes {', '.join(missing)}")

    # Google: GIDClientID(·GIDServerClientID) + REVERSED_CLIENT_ID URL scheme
    if args.google_ios_client_id:
        for key, value in (("GIDClientID", args.google_ios_client_id),
                           ("GIDServerClientID", args.google_server_client_id)):
            if value and plist_data.get(key) != value:
                notes.append(f"{'updated' if key in plist_data else 'added'} {key}")
                plist_data[key] = value
        notes.append(upsert_url_scheme(plist_data, to_reversed_client_id(args.google_ios_client_id),
                                       lambda existing: existing.startswith(GOOGLE_REVERSED_PREFIX)))

    notes = [note for note in notes if note]
    if not notes:
        return content, []
    # Rewriting with plistlib drops XML comments — record it in the changes instead of deleting silently
    if "<!--" in content:
        notes.append("XML comments in Info.plist are not kept (the file is rewritten) — check the diff")
    new_content = plistlib.dumps(plist_data, sort_keys=False).decode("utf-8")
    newline = detect_newline(content)
    if newline != "\n":
        new_content = new_content.replace("\n", newline)
    return new_content, notes


def patch_gitignore(content, include_firebase_files):
    """.gitignore > (new content, change descriptions). Existing lines are not added again"""
    patterns = list(GITIGNORE_EXPORT_PATTERNS)
    if include_firebase_files:
        patterns.extend(GITIGNORE_FIREBASE_PATTERNS)
    existing_lines = {line.strip() for line in content.splitlines()}
    missing = [pattern for pattern in patterns if pattern not in existing_lines]
    if not missing:
        return content, []
    newline = detect_newline(content) if content else "\n"
    prefix = "" if not content or content.endswith(("\n", "\r\n")) else newline
    lines = [] if GITIGNORE_HEADER in existing_lines else [GITIGNORE_HEADER]
    addition = prefix + newline.join(lines + missing) + newline
    return content + addition, [f"added {', '.join(missing)}"]


def plan_changes(args, project_path):
    """Compute new content per target file > [{path, relative, content, notes}] (disk untouched)"""
    plans = []
    targets = []
    if args.kakao_native_app_key:
        targets.append((MANIFEST_RELATIVE_PATH, lambda text: patch_manifest(text, args.kakao_native_app_key)))
    if args.kakao_native_app_key or args.google_ios_client_id:
        targets.append((INFO_PLIST_RELATIVE_PATH, lambda text: patch_info_plist(text, args)))
    for relative_path, patcher in targets:
        absolute_path = os.path.join(project_path, relative_path)
        if not path_exists(absolute_path):
            raise ValueError(f"{relative_path} not found — run this from your Flutter project root (or pass --project-path)")
        original = read_text(absolute_path)
        try:
            new_content, notes = patcher(original)
        except Exception as error:  # noqa: BLE001 — rethrow with the file name attached
            raise ValueError(f"{relative_path}: {error}") from error
        plans.append({"path": absolute_path, "relative": relative_path, "content": new_content,
                      "notes": notes, "exists": True})
    if args.update_gitignore:
        absolute_path = os.path.join(project_path, GITIGNORE_RELATIVE_PATH)
        exists = path_exists(absolute_path)
        original = read_text(absolute_path) if exists else ""
        new_content, notes = patch_gitignore(original, args.firebase_files)
        plans.append({"path": absolute_path, "relative": GITIGNORE_RELATIVE_PATH, "content": new_content,
                      "notes": notes, "exists": exists})
    return plans


def apply_changes(plans):
    """Changed files only: back up > write (through the gate — plan only in dry-run)"""
    for plan in plans:
        if not plan["notes"]:
            continue
        if plan["exists"]:
            backup_file(plan["path"])
        write_text(plan["path"], plan["content"])


def print_plan(plans):
    for plan in plans:
        if plan["notes"]:
            for note in plan["notes"]:
                print(f"{GREEN}[changed]{NC} {plan['relative']}: {note}")
        else:
            print(f"[unchanged] {plan['relative']}: already configured")


def confirm_apply():
    try:
        answer = input("Apply these changes? [y/N] ").strip().lower()
    except EOFError:
        return False
    return answer in ("y", "yes")


def cmd_setup(args):
    """Validate > plan > (confirm) > apply > next steps guidance"""
    global DRY_RUN, NO_BACKUP
    DRY_RUN = args.dry_run
    NO_BACKUP = args.no_backup

    problems = validate_setup_args(args)
    if problems:
        for problem in problems:
            print_error(problem)
        return 1
    project_path = os.path.abspath(args.project_path)
    if not os.path.exists(os.path.join(project_path, "pubspec.yaml")):
        print_error(f"pubspec.yaml not found in {project_path} — is this a Flutter project?")
        return 1

    try:
        plans = plan_changes(args, project_path)
    except ValueError as error:
        print_error(str(error))
        print_error("No files were changed.")
        return 1

    print_info(f"Project: {project_path}{' (dry run — nothing is written)' if DRY_RUN else ''}")
    print_plan(plans)
    has_changes = any(plan["notes"] for plan in plans)
    if not has_changes:
        print_info("Everything is already configured. Nothing to change.")
        return 0
    # Confirm only on an interactive terminal (CI, pipes and --non-interactive apply directly)
    if not DRY_RUN and not args.non_interactive and sys.stdin.isatty() and not confirm_apply():
        print_info("Cancelled. No files were changed.")
        return 0

    apply_changes(plans)
    print_info("Done." if not DRY_RUN else "Dry run finished. Run again without --dry-run to apply.")
    print_info("Next: flutter pub add kakao_flutter_sdk_user google_sign_in  (only the packages you use)")
    if not NO_BACKUP and not DRY_RUN:
        print_info("Backups were saved next to each changed file as *.bak — delete them after checking the diff.")
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        prog="oauth-wizard.py",
        description="OAuth login wizard (Kakao, Google) for Flutter — native config helper")
    subparsers = parser.add_subparsers(dest="command", required=True)

    detect_parser = subparsers.add_parser("detect", help="Detect app IDs and existing OAuth entries (JSON, read-only)")
    detect_parser.add_argument("--project-path", default=".")
    detect_parser.set_defaults(handler=cmd_detect)

    fingerprints_parser = subparsers.add_parser("fingerprints", help="Print SHA-1, SHA-256 and Kakao key hash of a keystore (JSON)")
    fingerprints_parser.add_argument("--keystore", default="~/.android/debug.keystore")
    fingerprints_parser.add_argument("--alias", default="androiddebugkey")
    fingerprints_parser.add_argument("--storepass", default=None, help="or set KEYSTORE_PASSWORD")
    fingerprints_parser.set_defaults(handler=cmd_fingerprints)

    key_hash_parser = subparsers.add_parser("key-hash", help="Convert a SHA-1 fingerprint to a Kakao key hash (JSON)")
    key_hash_parser.add_argument("--sha1", required=True)
    key_hash_parser.set_defaults(handler=cmd_key_hash)

    setup_parser = subparsers.add_parser("setup", help="Patch AndroidManifest.xml, Info.plist and .gitignore (idempotent)")
    setup_parser.add_argument("--project-path", default=".")
    setup_parser.add_argument("--kakao-native-app-key", default="")
    setup_parser.add_argument("--google-ios-client-id", default="")
    setup_parser.add_argument("--google-server-client-id", default="")
    setup_parser.add_argument("--update-gitignore", action="store_true", help="add wizard export files to .gitignore")
    setup_parser.add_argument("--firebase-files", action="store_true",
                              help="with --update-gitignore: also ignore google-services.json and GoogleService-Info.plist")
    setup_parser.add_argument("--dry-run", action="store_true", help="show what would change, write nothing")
    setup_parser.add_argument("--non-interactive", action="store_true", help="do not ask for confirmation")
    setup_parser.add_argument("--no-backup", action="store_true", help="do not create *.bak backups")
    setup_parser.set_defaults(handler=cmd_setup)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
