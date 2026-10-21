#!/usr/bin/env python3
# ===================================================================
# OAuth Login Wizard - CLI (Python, stdlib 전용)
# ===================================================================
# Kakao·Google 로그인 네이티브 설정을 Flutter 프로젝트에 적용한다 (#156).
#
# 서브커맨드 4개
#   detect       : applicationId·bundle ID·설정 파일 위치·기존 항목 감지 (JSON, 읽기 전용)
#   fingerprints : keytool 로 키스토어 SHA-1·SHA-256·Kakao 키 해시 출력 (JSON, 읽기 전용)
#   key-hash     : SHA-1(16진) > Kakao 키 해시(base64) (JSON)
#   setup        : AndroidManifest.xml·Info.plist·.gitignore 패치 (멱등)
#
# 사용법:
#   python3 oauth-wizard.py setup --project-path . \
#     --kakao-native-app-key 0123456789abcdef0123456789abcdef \
#     --google-ios-client-id 1234-abc.apps.googleusercontent.com \
#     [--google-server-client-id 1234-web.apps.googleusercontent.com] \
#     [--update-gitignore] [--firebase-files] \
#     [--dry-run] [--non-interactive] [--no-backup]
#
# 순서: 입력 검증 > 새 내용 전부 계산 > (확인) > 백업 > 쓰기
#   계산을 먼저 끝내므로 파일 하나라도 문제가 있으면 아무것도 바꾸지 않는다.
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

# ---- stdout/stderr UTF-8 (cp949 콘솔 대응) ----
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _ansi_enabled():
    """색상 출력 여부 — 파이프·NO_COLOR 면 끈다"""
    if os.environ.get("NO_COLOR"):
        return False
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


if _ansi_enabled():
    RED, GREEN, YELLOW, BLUE, NC = "\033[0;31m", "\033[0;32m", "\033[1;33m", "\033[0;34m", "\033[0m"
else:
    RED = GREEN = YELLOW = BLUE = NC = ""

# 개행 보존 (CRLF 파일을 LF 로 바꾸지 않는다)
_READ_KWARGS = _WRITE_KWARGS = dict(encoding="utf-8", errors="surrogateescape", newline="")

# >>> 공통 블록: 쓰기 게이트 (testflight·playstore 동일 — _shared/check-consistency.py 가 비교)
# 파일을 변경하는 원시 동작(쓰기·복사·이동·삭제·디렉터리 생성)은 전부 아래 게이트를 거친다.
# DRY_RUN이면 디스크를 건드리지 않고 "무엇을 할지"만 출력한다.
#
# ⚠️ 오버레이가 필요한 이유
#   "쓰고 → 다시 읽어 검증"하는 단계가 있어, 쓰기만 건너뛰면 뒷 단계가 낡은 내용을
#   읽어 실제 실행과 다른 경로를 타고 거짓 실패를 낸다. 그래서 dry-run에서는
#   쓰였을 내용을 메모리에 두고 read_text가 그것을 먼저 본다.
# 인코딩·개행 처리는 마법사마다 다르므로 블록 밖의 _READ_KWARGS·_WRITE_KWARGS 를 쓴다.
DRY_RUN = False
NO_BACKUP = False
_DRY_FS = {}          # path -> content (dry-run 가상 파일 내용)
_DRY_DELETED = set()  # dry-run에서 삭제된 것으로 간주하는 경로


def _dry(msg):
    print(f"{YELLOW}[dry-run]{NC} {msg}")


def copy_file(src, dst):
    """shutil.copyfile 대체 — dry-run이면 계획만 출력하고 오버레이에 반영한다."""
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
    """백업 생성. --no-backup이면 건너뛴다."""
    if NO_BACKUP:
        return
    copy_file(path, f"{path}{suffix}")


def remove_file(path):
    """삭제 — dry-run이면 계획만. 없으면 조용히 통과."""
    if DRY_RUN:
        _dry(f"delete: {path}")
        _DRY_FS.pop(path, None)
        _DRY_DELETED.add(path)
        return
    if os.path.exists(path):
        os.remove(path)


def move_file(src, dst):
    """이동(주로 백업 복원) — dry-run이면 계획만."""
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
    """존재 확인 — dry-run 오버레이를 반영한다."""
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
# 상수
# ============================================
MANIFEST_RELATIVE_PATH = "android/app/src/main/AndroidManifest.xml"
INFO_PLIST_RELATIVE_PATH = "ios/Runner/Info.plist"
GITIGNORE_RELATIVE_PATH = ".gitignore"
GRADLE_RELATIVE_PATHS = ("android/app/build.gradle.kts", "android/app/build.gradle")
PBXPROJ_RELATIVE_PATH = "ios/Runner.xcodeproj/project.pbxproj"

KAKAO_ACTIVITY_NAME = "com.kakao.sdk.flutter.auth.AuthCodeHandlerActivity"
# Kakao 네이티브 앱 키: 32자리 16진
KAKAO_NATIVE_APP_KEY_RE = re.compile(r"^[0-9a-fA-F]{32}$")
KAKAO_URL_SCHEME_RE = re.compile(r"^kakao[0-9a-fA-F]{32}$")
# 카카오톡 로그인(kakaokompassauth)·공유(kakaolink) — developers.kakao.com iOS 시작하기 기준
KAKAO_QUERIES_SCHEMES = ("kakaokompassauth", "kakaolink")
# Google OAuth 클라이언트 ID: {번호}-{식별자}.apps.googleusercontent.com
GOOGLE_CLIENT_ID_RE = re.compile(r"^([0-9]+-[0-9a-z]+)\.apps\.googleusercontent\.com$")
GOOGLE_REVERSED_PREFIX = "com.googleusercontent.apps."

GITIGNORE_HEADER = "# OAuth wizard (projectops)"
# 마법사 내보내기 파일 — Secret 값이 그대로 들어 있다
GITIGNORE_EXPORT_PATTERNS = ("oauth-secrets-*.json", "oauth-secrets-*.txt", "oauth-setup-*.zip")
# Firebase 설정 파일 — CI 가 GitHub Secret 에서 다시 만든다
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
# 감지 (읽기 전용)
# ============================================

def detect_application_id(project_path):
    """build.gradle(.kts) applicationId > 값 (없으면 None)"""
    for relative_path in GRADLE_RELATIVE_PATHS:
        gradle_path = os.path.join(project_path, relative_path)
        if not os.path.exists(gradle_path):
            continue
        match = re.search(r"""applicationId\s*=?\s*["']([^"']+)["']""", read_text(gradle_path))
        if match:
            return {"value": match.group(1), "source": relative_path}
    return None


def detect_bundle_id(project_path):
    """project.pbxproj PRODUCT_BUNDLE_IDENTIFIER > 앱 본체 값 (테스트 타깃 제외, 최빈값)"""
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
    """Info.plist 문자열 > dict (plistlib)"""
    return plistlib.loads(content.encode("utf-8"))


def collect_url_schemes(plist_data):
    schemes = []
    for url_type in plist_data.get("CFBundleURLTypes", []) or []:
        schemes.extend(url_type.get("CFBundleURLSchemes", []) or [])
    return schemes


def cmd_detect(args):
    """앱 ID·설정 파일·기존 OAuth 항목 감지 > JSON"""
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
        except Exception as error:  # noqa: BLE001 — 깨진 plist 도 감지 결과로 돌려준다
            result["infoPlist"]["parseError"] = str(error)
    result["next"] = "setup --project-path <path> --kakao-native-app-key <key> / --google-ios-client-id <id>"
    emit_json(result)
    return 0


# ============================================
# 키 지문 / Kakao 키 해시
# ============================================

def sha1_hex_to_key_hash(sha1_hex):
    """SHA-1 16진(콜론 허용) > Kakao 키 해시 base64 (xxd -r -p | openssl base64 와 같음)"""
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
    """keytool -list -v 출력 > {"sha1": ..., "sha256": ...}"""
    fingerprints = {}
    for label, key in (("SHA1", "sha1"), ("SHA256", "sha256")):
        match = re.search(rf"^\s*{label}:\s*([0-9A-Fa-f:]+)\s*$", output, re.M)
        if match:
            fingerprints[key] = match.group(1).upper()
    return fingerprints


def cmd_fingerprints(args):
    """keytool 실행(읽기 전용) > SHA-1·SHA-256·Kakao 키 해시"""
    keytool_path = shutil.which("keytool")
    if not keytool_path:
        emit_json({"ok": False, "error": "keytool not found. Install a JDK (Android Studio ships one) and add it to PATH."})
        return 1
    # 비밀번호: 인자 > 환경변수 KEYSTORE_PASSWORD > 디버그 키 기본값
    store_password = args.storepass or os.environ.get("KEYSTORE_PASSWORD")
    if not store_password and args.alias == "androiddebugkey":
        store_password = "android"
    if not store_password:
        emit_json({"ok": False, "error": "Pass --storepass or set KEYSTORE_PASSWORD (release keystores have no default password)."})
        return 1
    command = [keytool_path, "-list", "-v", "-keystore", os.path.expanduser(args.keystore),
               "-alias", args.alias, "-storepass", store_password]
    completed = subprocess.run(command, capture_output=True, text=True)
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
# setup: 패치 계산 (메모리) — 쓰기는 apply_changes 에서만
# ============================================

def to_reversed_client_id(ios_client_id):
    """iOS 클라이언트 ID > REVERSED_CLIENT_ID (com.googleusercontent.apps.{번호}-{식별자})"""
    match = GOOGLE_CLIENT_ID_RE.match(ios_client_id)
    return GOOGLE_REVERSED_PREFIX + match.group(1)


def validate_setup_args(args):
    """입력 검증 > 실패 사유 목록 (빈 목록이면 통과)"""
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
    """AuthCodeHandlerActivity 블록 (developers.kakao.com Flutter 시작하기와 같은 마크업)"""
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
    """AndroidManifest.xml > (새 내용, 변경 설명 목록). 이미 같으면 내용 그대로"""
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
            # 액티비티는 있는데 scheme 이 없으면 사람이 고친 블록 — 덮어쓰지 않고 실패
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
    """CFBundleURLTypes 에 scheme 보장. 같은 제공자 scheme 이 다르면 교체 > 변경 설명"""
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
    """Info.plist > (새 내용, 변경 설명 목록)"""
    plist_data = load_info_plist(content)
    notes = []

    # Kakao: URL scheme kakao{키} + 카카오톡 앱 확인 허용 목록
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
    # plistlib 로 다시 쓰면 XML 주석이 사라진다 — 조용히 지우지 않게 변경 내역에 남긴다
    if "<!--" in content:
        notes.append("XML comments in Info.plist are not kept (the file is rewritten) — check the diff")
    new_content = plistlib.dumps(plist_data, sort_keys=False).decode("utf-8")
    newline = detect_newline(content)
    if newline != "\n":
        new_content = new_content.replace("\n", newline)
    return new_content, notes


def patch_gitignore(content, include_firebase_files):
    """.gitignore > (새 내용, 변경 설명 목록). 이미 있는 줄은 다시 넣지 않는다"""
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
    """대상 파일별 새 내용 계산 > [{path, relative, content, notes}] (디스크 무변경)"""
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
        except Exception as error:  # noqa: BLE001 — 파일 이름을 붙여 다시 던진다
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
    """변경된 파일만: 백업 > 쓰기 (게이트 경유 — dry-run 이면 계획만)"""
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
    """검증 > 계획 > (확인) > 적용 > 다음 할 일 안내"""
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
    # 대화형 터미널에서만 확인 (CI·파이프·--non-interactive 는 바로 적용)
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
