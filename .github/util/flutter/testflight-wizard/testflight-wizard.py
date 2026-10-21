#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ===================================================================
# Flutter iOS TestFlight 초기화 스크립트
# ===================================================================
#
# 이 스크립트는 Flutter 프로젝트에 iOS TestFlight 배포를 위한
# 빌드 환경 설정을 자동으로 구성합니다.
#
# ★ 마법사 우선 아키텍처 ★
# - 모든 설정 파일은 이 마법사가 생성합니다
# - GitHub Actions 워크플로우는 생성된 파일을 그대로 사용합니다
# - 초기 설정 후 수정 불필요 (One-time setup)
#
# 빌드 파이프라인:
#   1. flutter build ios --no-codesign (Flutter 빌드)
#   2. xcodebuild archive (Xcode 아카이브 생성)
#   3. xcodebuild -exportArchive (IPA 생성)
#   4. fastlane upload_testflight (TestFlight 업로드)
#
# 사용법:
#   python3 testflight-wizard.py setup PROJECT_PATH BUNDLE_ID TEAM_ID PROFILE_NAME [USES_ENCRYPTION]
#
# 예시:
#   python3 testflight-wizard.py setup /path/to/project com.example.myapp ABC1234DEF "MyApp Distribution"
#   python3 testflight-wizard.py setup /path/to/project com.example.myapp ABC1234DEF "MyApp Distribution" false
#
# 생성/수정되는 파일:
#   - ios/Gemfile                    (Fastlane 의존성)
#   - ios/fastlane/Fastfile          (TestFlight 업로드 설정) ★ 핵심
#   - ios/ExportOptions.plist        (IPA 익스포트 설정) ★ 핵심
#   - ios/Runner.xcodeproj           (Manual Signing 패치) ★ 핵심
#   - ios/Runner/Info.plist          (암호화 설정)
#
# 참고: 구 bash 스크립트의 1:1 Python 포팅이다 (로직/문구/종료코드 보존).
#       sed 기반 치환은 문자열/정규식 치환으로 옮겼으며, sed가 라인 단위로
#       동작하던 패턴([^"]* 등)은 개행 불포함 패턴으로 동일하게 유지했다.
# ===================================================================

import argparse
import os
import re
import shutil
import sys

# cp949 콘솔 등에서 한글/이모지 출력이 깨지지 않도록 UTF-8 강제
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

# 색상 정의 (기존 sh와 동일 팔레트)
RED = "\033[0;31m"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
BLUE = "\033[0;34m"
CYAN = "\033[0;36m"
NC = "\033[0m"  # No Color


def _enable_ansi():
    """Windows 콘솔에서 ANSI 활성화 시도. 실패 시 무색 출력."""
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

# 전역 설정 (sh의 전역 변수와 동일 역할)
PROJECT_PATH = ""
BUNDLE_ID = ""
TEAM_ID = ""
PROFILE_NAME = ""
USES_NON_EXEMPT_ENCRYPTION = "false"
TEMPLATE_DIR = ""

# 파일 IO: 바이트 보존을 위해 surrogateescape + 개행 무변환(newline="")
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


# 출력 함수
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


# 도움말
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


# 매개변수 검증
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
    # 5번째 매개변수: 암호화 사용 여부 (기본값: false)
    USES_NON_EXEMPT_ENCRYPTION = params[4] if len(params) >= 5 and params[4] else "false"

    # 프로젝트 경로 확인
    if not os.path.isdir(PROJECT_PATH):
        print_error(f"Project path does not exist: {PROJECT_PATH}")
        sys.exit(1)

    # pubspec.yaml 확인 (Flutter 프로젝트)
    if not path_exists(f"{PROJECT_PATH}/pubspec.yaml"):
        print_error("Not a Flutter project (no pubspec.yaml)")
        sys.exit(1)

    # ios 폴더 확인
    if not os.path.isdir(f"{PROJECT_PATH}/ios"):
        print_error("No ios folder. Run 'flutter create .' first.")
        sys.exit(1)

    # Bundle ID 형식 확인
    if "." not in BUNDLE_ID:
        print_error(f"Invalid Bundle ID format: {BUNDLE_ID}")
        print_error("Example: com.example.myapp")
        sys.exit(1)

    # Team ID 길이 확인
    if len(TEAM_ID) != 10:
        print_error(f"Team ID must be 10 characters: {TEAM_ID}")
        sys.exit(1)

    # 암호화 설정 값 검증 (true/false만 허용)
    if USES_NON_EXEMPT_ENCRYPTION not in ("true", "false"):
        print_warning(f"Invalid encryption value: {USES_NON_EXEMPT_ENCRYPTION}")
        print_warning("Using the default 'false'.")
        USES_NON_EXEMPT_ENCRYPTION = "false"


# 템플릿 디렉토리 찾기
def find_template_dir():
    global TEMPLATE_DIR
    # 스크립트 위치 기준
    script_dir = os.path.dirname(os.path.abspath(__file__))
    TEMPLATE_DIR = f"{script_dir}/templates"

    if not os.path.isdir(TEMPLATE_DIR):
        print_error(f"Template directory not found: {TEMPLATE_DIR}")
        sys.exit(1)

    print_info(f"Template directory: {TEMPLATE_DIR}")


# Gemfile 생성
def create_gemfile():
    print_step("Creating Gemfile...")

    gemfile_path = f"{PROJECT_PATH}/ios/Gemfile"

    # 기존 파일 백업
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


# Fastfile 생성 (템플릿에서 복사)
# ★ 이 파일이 GitHub Actions 워크플로우에서 직접 사용됩니다 ★
def create_fastfile():
    print_step("Creating Fastfile...")

    fastlane_dir = f"{PROJECT_PATH}/ios/fastlane"
    fastfile_path = f"{fastlane_dir}/Fastfile"
    template_fastfile = f"{TEMPLATE_DIR}/Fastfile.ios.template"

    # fastlane 디렉토리 생성
    make_dirs(fastlane_dir)

    # 기존 파일 백업
    if path_exists(fastfile_path):
        print_warning(f"Backing up existing Fastfile: {fastfile_path}.bak")
        backup_file(fastfile_path)

    # 템플릿 파일 존재 확인
    if not path_exists(template_fastfile):
        print_error(f"Fastfile template not found: {template_fastfile}")
        sys.exit(1)

    # 템플릿에서 복사
    copy_file(template_fastfile, fastfile_path)

    print_success(f"Fastfile created: {fastfile_path}")
    print_info("  → The GitHub Actions workflow uses this file directly")


# ExportOptions.plist 생성 (xcodebuild -exportArchive에 필요)
def create_export_options_plist():
    print_step("Creating ExportOptions.plist...")

    export_options_path = f"{PROJECT_PATH}/ios/ExportOptions.plist"
    template_export_options = f"{TEMPLATE_DIR}/ExportOptions.plist"

    # 기존 파일 백업
    if path_exists(export_options_path):
        print_warning(f"Backing up existing ExportOptions.plist: {export_options_path}.bak")
        backup_file(export_options_path)

    # 템플릿 파일 존재 확인
    if path_exists(template_export_options):
        # 템플릿에서 복사하고 플레이스홀더 치환
        content = read_text(template_export_options)
        content = content.replace("{{TEAM_ID}}", TEAM_ID)
        content = content.replace("{{BUNDLE_ID}}", BUNDLE_ID)
        content = content.replace("{{PROFILE_NAME}}", PROFILE_NAME)
        write_text(export_options_path, content)
        print_info("  → Created from the template")
    else:
        # 템플릿이 없으면 직접 생성
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


# .gitignore 업데이트 (선택사항)
def update_gitignore():
    print_step("Checking .gitignore...")

    gitignore_path = f"{PROJECT_PATH}/ios/.gitignore"

    # Gemfile.lock은 일반적으로 커밋하지 않음
    if path_exists(gitignore_path):
        if not re.search("Gemfile.lock", read_text(gitignore_path)):
            # 게이트 경유 — dry-run이면 실제 추가하지 않는다
            append_text(gitignore_path, "\n# Fastlane\nGemfile.lock\n")
            print_info("Added Gemfile.lock to .gitignore")

    print_success(".gitignore checked")


# Info.plist에 암호화 설정 추가 (Export Compliance)
def update_info_plist_encryption():
    print_step("Adding the encryption setting to Info.plist...")

    info_plist_path = f"{PROJECT_PATH}/ios/Runner/Info.plist"

    if not path_exists(info_plist_path):
        print_error(f"Info.plist not found: {info_plist_path}")
        return 1

    content = read_text(info_plist_path)

    # 이미 ITSAppUsesNonExemptEncryption 키가 있는지 확인
    if "ITSAppUsesNonExemptEncryption" in content:
        print_info("ITSAppUsesNonExemptEncryption is already set")
        # 기존 값을 업데이트 (sed와 동일하게 키/값이 같은 줄에 있을 때만 매칭)
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

    # 백업 생성
    backup_file(info_plist_path)
    print_info(f"Backup created: {info_plist_path}.bak")

    # </dict> 바로 앞에 ITSAppUsesNonExemptEncryption 추가
    encryption_value = "true" if USES_NON_EXEMPT_ENCRYPTION == "true" else "false"

    content = content.replace(
        "</dict>",
        f"<key>ITSAppUsesNonExemptEncryption</key>\n\t<{encryption_value}/>\n</dict>",
    )
    write_text(info_plist_path, content)

    # 변경 확인
    if "ITSAppUsesNonExemptEncryption" in read_text(info_plist_path):
        print_success(f"ITSAppUsesNonExemptEncryption added: <{encryption_value}/>")
        remove_file(f"{info_plist_path}.bak")
    else:
        print_error("Failed to add ITSAppUsesNonExemptEncryption!")
        move_file(f"{info_plist_path}.bak", info_plist_path)
        return 1

    return 0


# Xcode 프로젝트의 Bundle ID 변경 (Apple Developer 설정과 일치시키기 위해)
def update_bundle_id():
    print_step("Checking and updating the Bundle ID...")

    pbxproj_path = f"{PROJECT_PATH}/ios/Runner.xcodeproj/project.pbxproj"

    if not path_exists(pbxproj_path):
        print_error(f"project.pbxproj not found: {pbxproj_path}")
        return 1

    content = read_text(pbxproj_path)

    # 입력한 Bundle ID가 이미 존재하면 스킵
    if f"PRODUCT_BUNDLE_IDENTIFIER = {BUNDLE_ID};" in content:
        print_info(f"Bundle ID is already set correctly: {BUNDLE_ID}")
        return 0

    # 현재 project.pbxproj에 있는 Runner 앱의 Bundle ID 추출 (RunnerTests 제외)
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

    # Bundle ID가 다르면 변경
    if current_bundle_id != BUNDLE_ID:
        print_warning("The Bundle ID differs. Changing it automatically...")

        # 백업 생성
        backup_file(pbxproj_path, ".bundleid.bak")

        # Runner 앱의 Bundle ID 변경 (정확히 매칭)
        content = content.replace(
            f"PRODUCT_BUNDLE_IDENTIFIER = {current_bundle_id};",
            f"PRODUCT_BUNDLE_IDENTIFIER = {BUNDLE_ID};",
        )

        # RunnerTests의 Bundle ID도 함께 변경 (Runner 앱의 Bundle ID + .RunnerTests)
        content = content.replace(
            f"PRODUCT_BUNDLE_IDENTIFIER = {current_bundle_id}.RunnerTests;",
            f"PRODUCT_BUNDLE_IDENTIFIER = {BUNDLE_ID}.RunnerTests;",
        )
        write_text(pbxproj_path, content)

        # 변경 확인
        if f"PRODUCT_BUNDLE_IDENTIFIER = {BUNDLE_ID};" in read_text(pbxproj_path):
            print_success(f"Bundle ID changed: {current_bundle_id} → {BUNDLE_ID}")
            remove_file(f"{pbxproj_path}.bundleid.bak")
        else:
            print_error("Failed to change the Bundle ID!")
            move_file(f"{pbxproj_path}.bundleid.bak", pbxproj_path)
            return 1

    return 0


def _replace_profile_specifier(content):
    """"PROVISIONING_PROFILE_SPECIFIER" = "..."; 값을 PROFILE_NAME으로 갱신."""
    return re.sub(
        r'"PROVISIONING_PROFILE_SPECIFIER" = "[^"\n]*";',
        lambda m: f'"PROVISIONING_PROFILE_SPECIFIER" = "{PROFILE_NAME}";',
        content,
    )


# Xcode 프로젝트에 DEVELOPMENT_TEAM 및 Manual Signing 추가 (CI 빌드에 필수)
def patch_xcode_project():
    print_step("Setting DEVELOPMENT_TEAM and Manual Signing in the Xcode project...")

    pbxproj_path = f"{PROJECT_PATH}/ios/Runner.xcodeproj/project.pbxproj"

    if not path_exists(pbxproj_path):
        print_error(f"project.pbxproj not found: {pbxproj_path}")
        return 1

    # 먼저 Bundle ID 업데이트 수행
    # (sh에서는 set -e로 인해 update_bundle_id 실패 시 스크립트가 즉시 종료됨 — 동일하게 처리)
    rc = update_bundle_id()
    if rc != 0:
        sys.exit(rc)

    # 백업 생성
    backup_file(pbxproj_path)
    print_info(f"Backup created: {pbxproj_path}.bak")

    content = read_text(pbxproj_path)

    # 이미 DEVELOPMENT_TEAM이 있는지 확인
    if f"DEVELOPMENT_TEAM = {TEAM_ID}" in content:
        print_info("DEVELOPMENT_TEAM is already set")
        # CODE_SIGN_STYLE도 확인하고 필요시 추가
        if "CODE_SIGN_STYLE = Manual" not in content:
            print_info("Adding CODE_SIGN_STYLE = Manual...")
            # Automatic을 Manual로 변경하거나 새로 추가
            if "CODE_SIGN_STYLE = Automatic" in content:
                content = content.replace("CODE_SIGN_STYLE = Automatic;", "CODE_SIGN_STYLE = Manual;")
            else:
                # DEVELOPMENT_TEAM 라인 다음에 CODE_SIGN_STYLE 추가
                content = content.replace(
                    f"DEVELOPMENT_TEAM = {TEAM_ID};",
                    f"DEVELOPMENT_TEAM = {TEAM_ID};\n\t\t\t\tCODE_SIGN_STYLE = Manual;",
                )
            print_success("CODE_SIGN_STYLE = Manual set")

        # PROVISIONING_PROFILE_SPECIFIER 업데이트
        if "PROVISIONING_PROFILE_SPECIFIER" in content:
            content = _replace_profile_specifier(content)
            print_success("PROVISIONING_PROFILE_SPECIFIER updated")

        write_text(pbxproj_path, content)
        remove_file(f"{pbxproj_path}.bak")
        print_success("Xcode project checked")
        return 0

    # DEVELOPMENT_TEAM이 있지만 다른 값이면 교체
    if "DEVELOPMENT_TEAM = " in content:
        print_info("Updating the existing DEVELOPMENT_TEAM value")
        content = re.sub(r"DEVELOPMENT_TEAM = [^;\n]*;", f"DEVELOPMENT_TEAM = {TEAM_ID};", content)
        print_success("DEVELOPMENT_TEAM updated")

        # CODE_SIGN_STYLE = Manual 설정
        if "CODE_SIGN_STYLE = Automatic" in content:
            content = content.replace("CODE_SIGN_STYLE = Automatic;", "CODE_SIGN_STYLE = Manual;")
            print_success("CODE_SIGN_STYLE = Manual set")
        elif "CODE_SIGN_STYLE = Manual" not in content:
            content = content.replace(
                f"DEVELOPMENT_TEAM = {TEAM_ID};",
                f"DEVELOPMENT_TEAM = {TEAM_ID};\n\t\t\t\tCODE_SIGN_STYLE = Manual;",
            )
            print_success("CODE_SIGN_STYLE = Manual added")

        # CODE_SIGN_IDENTITY 설정
        if 'CODE_SIGN_IDENTITY = "Apple Distribution"' not in content:
            content = content.replace(
                "CODE_SIGN_STYLE = Manual;",
                'CODE_SIGN_STYLE = Manual;\n\t\t\t\tCODE_SIGN_IDENTITY = "Apple Distribution";',
            )
            print_success("CODE_SIGN_IDENTITY = Apple Distribution added")

        # PROVISIONING_PROFILE_SPECIFIER 설정 (핵심!)
        if "PROVISIONING_PROFILE_SPECIFIER" not in content:
            content = content.replace(
                'CODE_SIGN_IDENTITY = "Apple Distribution";',
                'CODE_SIGN_IDENTITY = "Apple Distribution";\n\t\t\t\t'
                f'"PROVISIONING_PROFILE_SPECIFIER" = "{PROFILE_NAME}";',
            )
            print_success(f"PROVISIONING_PROFILE_SPECIFIER = {PROFILE_NAME} added")
        else:
            # 기존 값이 있으면 업데이트
            content = _replace_profile_specifier(content)
            print_success("PROVISIONING_PROFILE_SPECIFIER updated")

        # 구버전 CODE_SIGN_IDENTITY 설정 업데이트
        if '"CODE_SIGN_IDENTITY[sdk=iphoneos*]" = "iPhone Developer"' in content:
            content = content.replace(
                '"CODE_SIGN_IDENTITY[sdk=iphoneos*]" = "iPhone Developer"',
                '"CODE_SIGN_IDENTITY[sdk=iphoneos*]" = "Apple Distribution"',
            )
            print_success("CODE_SIGN_IDENTITY[sdk=iphoneos*] updated")

        write_text(pbxproj_path, content)
        remove_file(f"{pbxproj_path}.bak")
        return 0

    # Runner 타겟의 buildSettings에 DEVELOPMENT_TEAM 추가
    # PRODUCT_BUNDLE_IDENTIFIER 라인 다음에 추가
    print_info("Adding DEVELOPMENT_TEAM...")

    # Bundle ID가 존재하는지 확인 (update_bundle_id에서 이미 처리했으므로 존재해야 함)
    if f"PRODUCT_BUNDLE_IDENTIFIER = {BUNDLE_ID};" not in content:
        print_error("Bundle ID not found in project.pbxproj!")
        print("")
        print_error("┌─────────────────────────────────────────────────────────────────┐")
        print_error(f"│ Bundle ID you entered: {BUNDLE_ID}")
        print_error("├─────────────────────────────────────────────────────────────────┤")
        print_error("│ Bundle IDs found in project.pbxproj:")
        # 실제 존재하는 Bundle ID 목록 출력
        found_ids = []
        for line in content.splitlines():
            if "PRODUCT_BUNDLE_IDENTIFIER = " in line:
                value = re.sub(r".*= ", "  • ", line)
                value = re.sub(r";$", "", value)
                found_ids.append(value)
        for entry in sorted(set(found_ids)):
            # sh의 `while read line`은 앞뒤 공백을 제거하므로 동일하게 strip
            print_error(f"│ {entry.strip()}")
        print_error("└─────────────────────────────────────────────────────────────────┘")
        print("")
        print_error("How to fix:")
        print_info("1. Find the exact Bundle ID in the list above (case-sensitive!)")
        print_info("2. Run the script again with the correct Bundle ID")
        print_info(f'   e.g. python3 testflight-wizard.py setup "{PROJECT_PATH}" "exact.bundle.id" "{TEAM_ID}" "{PROFILE_NAME}"')
        move_file(f"{pbxproj_path}.bak", pbxproj_path)
        return 1

    # Runner 앱의 Bundle ID 라인 다음에 Manual Signing 관련 설정 모두 추가
    # - DEVELOPMENT_TEAM: Apple 팀 ID
    # - CODE_SIGN_STYLE: Manual (자동 서명 비활성화)
    # - CODE_SIGN_IDENTITY: Apple Distribution (배포용 인증서)
    # - PROVISIONING_PROFILE_SPECIFIER: 프로비저닝 프로파일 이름
    content = content.replace(
        f"PRODUCT_BUNDLE_IDENTIFIER = {BUNDLE_ID};",
        f"PRODUCT_BUNDLE_IDENTIFIER = {BUNDLE_ID};\n"
        f"\t\t\t\tDEVELOPMENT_TEAM = {TEAM_ID};\n"
        "\t\t\t\tCODE_SIGN_STYLE = Manual;\n"
        '\t\t\t\tCODE_SIGN_IDENTITY = "Apple Distribution";\n'
        f'\t\t\t\t"PROVISIONING_PROFILE_SPECIFIER" = "{PROFILE_NAME}";',
    )

    # 구버전 CODE_SIGN_IDENTITY 설정이 있으면 Apple Distribution으로 변경
    if '"CODE_SIGN_IDENTITY[sdk=iphoneos*]" = "iPhone Developer"' in content:
        content = content.replace(
            '"CODE_SIGN_IDENTITY[sdk=iphoneos*]" = "iPhone Developer"',
            '"CODE_SIGN_IDENTITY[sdk=iphoneos*]" = "Apple Distribution"',
        )
        print_success("CODE_SIGN_IDENTITY[sdk=iphoneos*] updated")

    write_text(pbxproj_path, content)

    # 변경 확인
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


# 완료 메시지
def print_completion():
    # 암호화 설정 표시 텍스트
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
# 메인 실행
# ===================================================================

# >>> 공통 블록: 인자 계약 (testflight·playstore 동일 — _shared/check-consistency.py 가 비교)
# ===================================================================
# 공통 인자 계약 (명명 플래그 정본 + 구 위치인자 호환)
# ===================================================================
# 정본은 **명명 플래그**다. 위치인자가 10개까지 늘어나면서 순서 실수가
# 잦았고(특히 비밀번호 자리), 무엇을 넘기는지 명령어만 보고 알 수 없었다.
#
# 다만 구 위치인자 호출도 계속 받는다 — 마법사 HTML이 이미 생성해 사용자가
# 복사해 둔 명령어가 위치인자 형식이기 때문이다. 둘 다 동작한다.
#
#   신형:  setup --project-path /p --bundle-id com.x.y --team-id ABC123 ...
#   구형:  setup /p com.x.y ABC123 "Profile Name"
#
# firebase 는 위치인자 호출 이력이 없어 argparse 로 같은 플래그만 받는다.
# ===================================================================

COMMON_FLAGS = ("--dry-run", "--non-interactive", "--no-backup")


def normalize_params(params, order):
    """명명 플래그와 위치인자를 함께 받아 (위치인자 리스트, 옵션 dict)로 정규화한다.

    order: 위치인자 순서에 대응하는 플래그 이름 튜플
           예) ("project-path", "bundle-id", "team-id", "profile-name")
    지원 형식: --key value / --key=value / 부울 플래그(COMMON_FLAGS)
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
        # 명명 플래그가 하나라도 있으면 명명 방식으로 간주하고 order대로 재배열한다.
        # 값이 빠진 자리는 빈 문자열로 채워 기존 검증 로직이 그대로 잡아내게 한다.
        merged = [named.get(k, "") for k in order]
        # 위치인자를 섞어 쓴 경우(부분 마이그레이션) 앞에서부터 빈 자리를 메운다
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

    # 도움말 옵션 확인
    if params and params[0] in ("-h", "--help"):
        show_help()
        sys.exit(0)

    # 명명 플래그 → 위치인자 정규화 (구/신 호출 형식 모두 지원)
    global DRY_RUN, NO_BACKUP
    params, cli_opts = normalize_params(params, ("project-path", "bundle-id", "team-id", "profile-name", "uses-encryption"))
    DRY_RUN = cli_opts["dry_run"]
    NO_BACKUP = not cli_opts["backup"]
    if DRY_RUN:
        print(f"{YELLOW}⚠️  dry-run mode — no files are created or changed.{NC}")
        print("")

    # 매개변수 검증
    validate_params(params)

    print(f"{BLUE}Project path:{NC} {PROJECT_PATH}")
    print(f"{BLUE}Bundle ID:{NC} {BUNDLE_ID}")
    print(f"{BLUE}Team ID:{NC} {TEAM_ID}")
    print(f"{BLUE}Profile Name:{NC} {PROFILE_NAME}")
    print(f"{BLUE}Uses encryption:{NC} {USES_NON_EXEMPT_ENCRYPTION}")
    print("")

    # 템플릿 디렉토리 찾기
    find_template_dir()

    # 파일 생성
    create_gemfile()
    create_fastfile()
    create_export_options_plist()
    update_gitignore()
    # (sh의 set -e와 동일: 실패 시 해당 종료코드로 즉시 종료)
    rc = patch_xcode_project()
    if rc != 0:
        sys.exit(rc)
    rc = update_info_plist_encryption()
    if rc != 0:
        sys.exit(rc)

    # 완료
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

    # setup 이후 인자는 구 sh와 동일하게 위치 인자 그대로 전달한다.
    # (argparse REMAINDER는 선두의 -h 등을 삼키지 못하는 알려진 문제가 있어 직접 라우팅)
    if argv and argv[0] == "setup":
        cmd_setup(argv[1:])
        return

    if argv:
        parser.parse_args(argv)  # -h/--help 및 알 수 없는 인자 처리
    parser.print_help()
    sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
