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

# ── 쓰기 게이트 (--dry-run 지원) ─────────────────────────────────────
# 파일을 변경하는 원시 동작은 전부 아래 게이트 함수를 거친다.
# DRY_RUN이면 디스크를 건드리지 않고 "무엇을 할지"만 출력한다.
#
# ⚠️ 오버레이가 필요한 이유
#   이 스크립트는 "쓰고 → 다시 읽어 검증"하는 단계가 여러 곳이다.
#   단순히 쓰기만 건너뛰면 뒷 단계가 낡은 내용을 읽어 실제 실행과 다른
#   경로를 타고 거짓 실패를 낸다. 그래서 dry-run에서는 쓰였을 내용을
#   메모리에 보관하고 read_text가 그것을 먼저 보게 한다.
DRY_RUN = False
NO_BACKUP = False
_DRY_FS = {}       # path -> content (dry-run 가상 파일 내용)
_DRY_DELETED = set()  # dry-run에서 삭제된 것으로 간주하는 경로


def _dry(msg):
    print(f"{YELLOW}[dry-run]{NC} {msg}")


def copy_file(src, dst):
    """shutil.copyfile 대체 — dry-run이면 계획만 출력하고 오버레이에 반영한다."""
    if DRY_RUN:
        _dry(f"복사: {src} → {dst}")
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
    """삭제 — dry-run이면 계획만. 없으면 조용히 통과(구 동작 유지)."""
    if DRY_RUN:
        _dry(f"삭제: {path}")
        _DRY_FS.pop(path, None)
        _DRY_DELETED.add(path)
        return
    if os.path.exists(path):
        os.remove(path)


def move_file(src, dst):
    """이동(주로 백업 복원) — dry-run이면 계획만."""
    if DRY_RUN:
        _dry(f"이동: {src} → {dst}")
        try:
            _DRY_FS[dst] = read_text(src)
            _DRY_DELETED.discard(dst)
        except OSError:
            pass
        _DRY_FS.pop(src, None)
        _DRY_DELETED.add(src)
        return
    shutil.move(src, dst)


def path_exists(path):
    """존재 확인 — dry-run 오버레이를 반영한다."""
    if DRY_RUN:
        if path in _DRY_FS:
            return True
        if path in _DRY_DELETED:
            return False
    return os.path.exists(path)


def make_dirs(path):
    if DRY_RUN:
        _dry(f"디렉터리 생성: {path}")
        return
    os.makedirs(path, exist_ok=True)


# 파일 IO: 바이트 보존을 위해 surrogateescape + 개행 무변환(newline="")
_IO_KWARGS = dict(encoding="utf-8", errors="surrogateescape", newline="")


def read_text(path):
    if DRY_RUN:
        if path in _DRY_FS:
            return _DRY_FS[path]
        if path in _DRY_DELETED:
            raise FileNotFoundError(path)
    with open(path, "r", **_IO_KWARGS) as f:
        return f.read()


def write_text(path, content):
    if DRY_RUN:
        _dry(f"쓰기: {path} ({len(content)} bytes)")
        _DRY_FS[path] = content
        _DRY_DELETED.discard(path)
        return
    with open(path, "w", **_IO_KWARGS) as f:
        f.write(content)


def append_text(path, content):
    if DRY_RUN:
        _dry(f"추가: {path}")
        base = read_text(path) if (path in _DRY_FS or path_exists(path)) else ""
        _DRY_FS[path] = base + content
        _DRY_DELETED.discard(path)
        return
    with open(path, "a", **_IO_KWARGS) as f:
        f.write(content)


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
    print(f"""{CYAN}Flutter iOS TestFlight 초기화 스크립트{NC}

{YELLOW}★ 마법사 우선 아키텍처 ★{NC}
  모든 설정 파일은 이 마법사가 생성하고,
  GitHub Actions 워크플로우는 생성된 파일을 그대로 사용합니다.

{BLUE}빌드 파이프라인:{NC}
  1. flutter build ios --no-codesign (Flutter 빌드)
  2. xcodebuild archive (Xcode 아카이브 생성)
  3. xcodebuild -exportArchive (IPA 생성)
  4. fastlane upload_testflight (TestFlight 업로드)

{BLUE}사용법 (권장 — 명명 플래그):{NC}
  python3 testflight-wizard.py setup \\
    --project-path /path/to/project \\
    --bundle-id com.example.myapp \\
    --team-id ABC1234DEF \\
    --profile-name "MyApp Distribution"

{BLUE}사용법 (구형 — 위치인자, 계속 지원):{NC}
  python3 testflight-wizard.py setup PROJECT_PATH BUNDLE_ID TEAM_ID PROFILE_NAME [USES_ENCRYPTION]

{BLUE}매개변수:{NC}
  --project-path      Flutter 프로젝트 루트 경로
  --bundle-id         iOS 앱 Bundle ID (예: com.example.myapp)
  --team-id           Apple Developer Team ID (10자리)
  --profile-name      Provisioning Profile 이름
  --uses-encryption   암호화 사용 여부 (true/false, 기본값: false)

{BLUE}공통 옵션 (3종 마법사 동일):{NC}
  --dry-run           무엇을 바꿀지만 출력하고 파일은 건드리지 않음
  --no-backup         기존 파일 백업(.bak)을 만들지 않음
  --non-interactive   확인 프롬프트 없이 진행 (CI용)

{BLUE}예시:{NC}
  python3 testflight-wizard.py setup --project-path . --bundle-id com.example.myapp \\
    --team-id ABC1234DEF --profile-name "MyApp Distribution" --dry-run
  python3 testflight-wizard.py setup /path/to/project com.example.myapp ABC1234DEF "MyApp Distribution"

{BLUE}생성/수정되는 파일:{NC}
  - ios/Gemfile                    Fastlane 의존성
  - ios/fastlane/Fastfile          TestFlight 업로드 설정 ★
  - ios/ExportOptions.plist        IPA 익스포트 설정 ★
  - ios/Runner.xcodeproj           Manual Signing 패치 ★
  - ios/Runner/Info.plist          암호화 설정 (ITSAppUsesNonExemptEncryption)
""")


# 매개변수 검증
def validate_params(params):
    global PROJECT_PATH, BUNDLE_ID, TEAM_ID, PROFILE_NAME, USES_NON_EXEMPT_ENCRYPTION

    if len(params) < 4:
        print_error("매개변수가 부족합니다.")
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
        print_error(f"프로젝트 경로가 존재하지 않습니다: {PROJECT_PATH}")
        sys.exit(1)

    # pubspec.yaml 확인 (Flutter 프로젝트)
    if not path_exists(f"{PROJECT_PATH}/pubspec.yaml"):
        print_error("Flutter 프로젝트가 아닙니다 (pubspec.yaml 없음)")
        sys.exit(1)

    # ios 폴더 확인
    if not os.path.isdir(f"{PROJECT_PATH}/ios"):
        print_error("iOS 폴더가 없습니다. 'flutter create .' 명령을 먼저 실행하세요.")
        sys.exit(1)

    # Bundle ID 형식 확인
    if "." not in BUNDLE_ID:
        print_error(f"Bundle ID 형식이 올바르지 않습니다: {BUNDLE_ID}")
        print_error("예시: com.example.myapp")
        sys.exit(1)

    # Team ID 길이 확인
    if len(TEAM_ID) != 10:
        print_error(f"Team ID는 10자리여야 합니다: {TEAM_ID}")
        sys.exit(1)

    # 암호화 설정 값 검증 (true/false만 허용)
    if USES_NON_EXEMPT_ENCRYPTION not in ("true", "false"):
        print_warning(f"암호화 설정 값이 올바르지 않습니다: {USES_NON_EXEMPT_ENCRYPTION}")
        print_warning("기본값 'false'를 사용합니다.")
        USES_NON_EXEMPT_ENCRYPTION = "false"


# 템플릿 디렉토리 찾기
def find_template_dir():
    global TEMPLATE_DIR
    # 스크립트 위치 기준
    script_dir = os.path.dirname(os.path.abspath(__file__))
    TEMPLATE_DIR = f"{script_dir}/templates"

    if not os.path.isdir(TEMPLATE_DIR):
        print_error(f"템플릿 디렉토리를 찾을 수 없습니다: {TEMPLATE_DIR}")
        sys.exit(1)

    print_info(f"템플릿 디렉토리: {TEMPLATE_DIR}")


# Gemfile 생성
def create_gemfile():
    print_step("Gemfile 생성 중...")

    gemfile_path = f"{PROJECT_PATH}/ios/Gemfile"

    # 기존 파일 백업
    if path_exists(gemfile_path):
        print_warning(f"기존 Gemfile 백업: {gemfile_path}.bak")
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

    print_success(f"Gemfile 생성 완료: {gemfile_path}")


# Fastfile 생성 (템플릿에서 복사)
# ★ 이 파일이 GitHub Actions 워크플로우에서 직접 사용됩니다 ★
def create_fastfile():
    print_step("Fastfile 생성 중...")

    fastlane_dir = f"{PROJECT_PATH}/ios/fastlane"
    fastfile_path = f"{fastlane_dir}/Fastfile"
    template_fastfile = f"{TEMPLATE_DIR}/Fastfile.ios.template"

    # fastlane 디렉토리 생성
    make_dirs(fastlane_dir)

    # 기존 파일 백업
    if path_exists(fastfile_path):
        print_warning(f"기존 Fastfile 백업: {fastfile_path}.bak")
        backup_file(fastfile_path)

    # 템플릿 파일 존재 확인
    if not path_exists(template_fastfile):
        print_error(f"Fastfile 템플릿을 찾을 수 없습니다: {template_fastfile}")
        sys.exit(1)

    # 템플릿에서 복사
    copy_file(template_fastfile, fastfile_path)

    print_success(f"Fastfile 생성 완료: {fastfile_path}")
    print_info("  → GitHub Actions 워크플로우에서 이 파일을 직접 사용합니다")


# ExportOptions.plist 생성 (xcodebuild -exportArchive에 필요)
def create_export_options_plist():
    print_step("ExportOptions.plist 생성 중...")

    export_options_path = f"{PROJECT_PATH}/ios/ExportOptions.plist"
    template_export_options = f"{TEMPLATE_DIR}/ExportOptions.plist"

    # 기존 파일 백업
    if path_exists(export_options_path):
        print_warning(f"기존 ExportOptions.plist 백업: {export_options_path}.bak")
        backup_file(export_options_path)

    # 템플릿 파일 존재 확인
    if path_exists(template_export_options):
        # 템플릿에서 복사하고 플레이스홀더 치환
        content = read_text(template_export_options)
        content = content.replace("{{TEAM_ID}}", TEAM_ID)
        content = content.replace("{{BUNDLE_ID}}", BUNDLE_ID)
        content = content.replace("{{PROFILE_NAME}}", PROFILE_NAME)
        write_text(export_options_path, content)
        print_info("  → 템플릿에서 생성됨")
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
    <key>stripSwiftSymbols</key>
    <true/>
    <key>uploadBitcode</key>
    <false/>
    <key>uploadSymbols</key>
    <true/>
</dict>
</plist>
""")

    print_success(f"ExportOptions.plist 생성 완료: {export_options_path}")
    print_info(f"  • Team ID: {TEAM_ID}")
    print_info(f"  • Bundle ID: {BUNDLE_ID}")
    print_info(f"  • Profile Name: {PROFILE_NAME}")


# .gitignore 업데이트 (선택사항)
def update_gitignore():
    print_step(".gitignore 확인 중...")

    gitignore_path = f"{PROJECT_PATH}/ios/.gitignore"

    # Gemfile.lock은 일반적으로 커밋하지 않음
    if path_exists(gitignore_path):
        if not re.search("Gemfile.lock", read_text(gitignore_path)):
            # 게이트 경유 — dry-run이면 실제 추가하지 않는다
            append_text(gitignore_path, "\n# Fastlane\nGemfile.lock\n")
            print_info("Gemfile.lock을 .gitignore에 추가했습니다")

    print_success(".gitignore 확인 완료")


# Info.plist에 암호화 설정 추가 (Export Compliance)
def update_info_plist_encryption():
    print_step("Info.plist에 암호화 설정 추가 중...")

    info_plist_path = f"{PROJECT_PATH}/ios/Runner/Info.plist"

    if not path_exists(info_plist_path):
        print_error(f"Info.plist 파일을 찾을 수 없습니다: {info_plist_path}")
        return 1

    content = read_text(info_plist_path)

    # 이미 ITSAppUsesNonExemptEncryption 키가 있는지 확인
    if "ITSAppUsesNonExemptEncryption" in content:
        print_info("ITSAppUsesNonExemptEncryption이 이미 설정되어 있습니다")
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
        print_success("ITSAppUsesNonExemptEncryption 값 업데이트 완료")
        return 0

    # 백업 생성
    backup_file(info_plist_path)
    print_info(f"백업 생성: {info_plist_path}.bak")

    # </dict> 바로 앞에 ITSAppUsesNonExemptEncryption 추가
    encryption_value = "true" if USES_NON_EXEMPT_ENCRYPTION == "true" else "false"

    content = content.replace(
        "</dict>",
        f"<key>ITSAppUsesNonExemptEncryption</key>\n\t<{encryption_value}/>\n</dict>",
    )
    write_text(info_plist_path, content)

    # 변경 확인
    if "ITSAppUsesNonExemptEncryption" in read_text(info_plist_path):
        print_success(f"ITSAppUsesNonExemptEncryption 추가 완료: <{encryption_value}/>")
        remove_file(f"{info_plist_path}.bak")
    else:
        print_error("ITSAppUsesNonExemptEncryption 추가 실패!")
        move_file(f"{info_plist_path}.bak", info_plist_path)
        return 1

    return 0


# Xcode 프로젝트의 Bundle ID 변경 (Apple Developer 설정과 일치시키기 위해)
def update_bundle_id():
    print_step("Bundle ID 확인 및 업데이트 중...")

    pbxproj_path = f"{PROJECT_PATH}/ios/Runner.xcodeproj/project.pbxproj"

    if not path_exists(pbxproj_path):
        print_error(f"project.pbxproj 파일을 찾을 수 없습니다: {pbxproj_path}")
        return 1

    content = read_text(pbxproj_path)

    # 입력한 Bundle ID가 이미 존재하면 스킵
    if f"PRODUCT_BUNDLE_IDENTIFIER = {BUNDLE_ID};" in content:
        print_info(f"Bundle ID가 이미 올바르게 설정되어 있습니다: {BUNDLE_ID}")
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
        print_error("현재 Bundle ID를 찾을 수 없습니다")
        return 1

    print_info(f"현재 Bundle ID: {current_bundle_id}")
    print_info(f"변경할 Bundle ID: {BUNDLE_ID}")

    # Bundle ID가 다르면 변경
    if current_bundle_id != BUNDLE_ID:
        print_warning("Bundle ID가 다릅니다. 자동으로 변경합니다...")

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
            print_success(f"Bundle ID 변경 완료: {current_bundle_id} → {BUNDLE_ID}")
            remove_file(f"{pbxproj_path}.bundleid.bak")
        else:
            print_error("Bundle ID 변경 실패!")
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
    print_step("Xcode 프로젝트에 DEVELOPMENT_TEAM 및 Manual Signing 설정 중...")

    pbxproj_path = f"{PROJECT_PATH}/ios/Runner.xcodeproj/project.pbxproj"

    if not path_exists(pbxproj_path):
        print_error(f"project.pbxproj 파일을 찾을 수 없습니다: {pbxproj_path}")
        return 1

    # 먼저 Bundle ID 업데이트 수행
    # (sh에서는 set -e로 인해 update_bundle_id 실패 시 스크립트가 즉시 종료됨 — 동일하게 처리)
    rc = update_bundle_id()
    if rc != 0:
        sys.exit(rc)

    # 백업 생성
    backup_file(pbxproj_path)
    print_info(f"백업 생성: {pbxproj_path}.bak")

    content = read_text(pbxproj_path)

    # 이미 DEVELOPMENT_TEAM이 있는지 확인
    if f"DEVELOPMENT_TEAM = {TEAM_ID}" in content:
        print_info("DEVELOPMENT_TEAM이 이미 설정되어 있습니다")
        # CODE_SIGN_STYLE도 확인하고 필요시 추가
        if "CODE_SIGN_STYLE = Manual" not in content:
            print_info("CODE_SIGN_STYLE = Manual 추가 중...")
            # Automatic을 Manual로 변경하거나 새로 추가
            if "CODE_SIGN_STYLE = Automatic" in content:
                content = content.replace("CODE_SIGN_STYLE = Automatic;", "CODE_SIGN_STYLE = Manual;")
            else:
                # DEVELOPMENT_TEAM 라인 다음에 CODE_SIGN_STYLE 추가
                content = content.replace(
                    f"DEVELOPMENT_TEAM = {TEAM_ID};",
                    f"DEVELOPMENT_TEAM = {TEAM_ID};\n\t\t\t\tCODE_SIGN_STYLE = Manual;",
                )
            print_success("CODE_SIGN_STYLE = Manual 설정 완료")

        # PROVISIONING_PROFILE_SPECIFIER 업데이트
        if "PROVISIONING_PROFILE_SPECIFIER" in content:
            content = _replace_profile_specifier(content)
            print_success("PROVISIONING_PROFILE_SPECIFIER 업데이트 완료")

        write_text(pbxproj_path, content)
        remove_file(f"{pbxproj_path}.bak")
        print_success("Xcode 프로젝트 확인 완료")
        return 0

    # DEVELOPMENT_TEAM이 있지만 다른 값이면 교체
    if "DEVELOPMENT_TEAM = " in content:
        print_info("기존 DEVELOPMENT_TEAM 값을 업데이트합니다")
        content = re.sub(r"DEVELOPMENT_TEAM = [^;\n]*;", f"DEVELOPMENT_TEAM = {TEAM_ID};", content)
        print_success("DEVELOPMENT_TEAM 업데이트 완료")

        # CODE_SIGN_STYLE = Manual 설정
        if "CODE_SIGN_STYLE = Automatic" in content:
            content = content.replace("CODE_SIGN_STYLE = Automatic;", "CODE_SIGN_STYLE = Manual;")
            print_success("CODE_SIGN_STYLE = Manual 설정 완료")
        elif "CODE_SIGN_STYLE = Manual" not in content:
            content = content.replace(
                f"DEVELOPMENT_TEAM = {TEAM_ID};",
                f"DEVELOPMENT_TEAM = {TEAM_ID};\n\t\t\t\tCODE_SIGN_STYLE = Manual;",
            )
            print_success("CODE_SIGN_STYLE = Manual 추가 완료")

        # CODE_SIGN_IDENTITY 설정
        if 'CODE_SIGN_IDENTITY = "Apple Distribution"' not in content:
            content = content.replace(
                "CODE_SIGN_STYLE = Manual;",
                'CODE_SIGN_STYLE = Manual;\n\t\t\t\tCODE_SIGN_IDENTITY = "Apple Distribution";',
            )
            print_success("CODE_SIGN_IDENTITY = Apple Distribution 추가 완료")

        # PROVISIONING_PROFILE_SPECIFIER 설정 (핵심!)
        if "PROVISIONING_PROFILE_SPECIFIER" not in content:
            content = content.replace(
                'CODE_SIGN_IDENTITY = "Apple Distribution";',
                'CODE_SIGN_IDENTITY = "Apple Distribution";\n\t\t\t\t'
                f'"PROVISIONING_PROFILE_SPECIFIER" = "{PROFILE_NAME}";',
            )
            print_success(f"PROVISIONING_PROFILE_SPECIFIER = {PROFILE_NAME} 추가 완료")
        else:
            # 기존 값이 있으면 업데이트
            content = _replace_profile_specifier(content)
            print_success("PROVISIONING_PROFILE_SPECIFIER 업데이트 완료")

        # 구버전 CODE_SIGN_IDENTITY 설정 업데이트
        if '"CODE_SIGN_IDENTITY[sdk=iphoneos*]" = "iPhone Developer"' in content:
            content = content.replace(
                '"CODE_SIGN_IDENTITY[sdk=iphoneos*]" = "iPhone Developer"',
                '"CODE_SIGN_IDENTITY[sdk=iphoneos*]" = "Apple Distribution"',
            )
            print_success("CODE_SIGN_IDENTITY[sdk=iphoneos*] 업데이트 완료")

        write_text(pbxproj_path, content)
        remove_file(f"{pbxproj_path}.bak")
        return 0

    # Runner 타겟의 buildSettings에 DEVELOPMENT_TEAM 추가
    # PRODUCT_BUNDLE_IDENTIFIER 라인 다음에 추가
    print_info("DEVELOPMENT_TEAM 추가 중...")

    # Bundle ID가 존재하는지 확인 (update_bundle_id에서 이미 처리했으므로 존재해야 함)
    if f"PRODUCT_BUNDLE_IDENTIFIER = {BUNDLE_ID};" not in content:
        print_error("Bundle ID를 project.pbxproj에서 찾을 수 없습니다!")
        print("")
        print_error("┌─────────────────────────────────────────────────────────────────┐")
        print_error(f"│ 입력한 Bundle ID: {BUNDLE_ID}")
        print_error("├─────────────────────────────────────────────────────────────────┤")
        print_error("│ project.pbxproj에 존재하는 Bundle ID들:")
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
        print_error("해결 방법:")
        print_info("1. 위 목록에서 정확한 Bundle ID를 확인하세요 (대소문자 구분!)")
        print_info("2. 올바른 Bundle ID로 스크립트를 다시 실행하세요")
        print_info(f'   예: python3 testflight-wizard.py setup "{PROJECT_PATH}" "정확한.번들.아이디" "{TEAM_ID}" "{PROFILE_NAME}"')
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
        print_success("CODE_SIGN_IDENTITY[sdk=iphoneos*] 업데이트 완료")

    write_text(pbxproj_path, content)

    # 변경 확인
    if f"DEVELOPMENT_TEAM = {TEAM_ID}" in content and "CODE_SIGN_STYLE = Manual" in content:
        print_success(f"DEVELOPMENT_TEAM 추가 완료: {TEAM_ID}")
        print_success("CODE_SIGN_STYLE = Manual 설정 완료")
        remove_file(f"{pbxproj_path}.bak")
    else:
        print_error("DEVELOPMENT_TEAM 또는 CODE_SIGN_STYLE 추가 실패!")
        print("")
        print_error("디버그 정보:")
        print_info(f"  • 입력한 Bundle ID: {BUNDLE_ID}")
        print_info(f"  • 입력한 Team ID: {TEAM_ID}")
        print_info(f"  • project.pbxproj 경로: {pbxproj_path}")
        print("")
        print_error("가능한 원인:")
        print_info("  1. 텍스트 치환 실행 중 오류 발생")
        print_info("  2. 파일 쓰기 권한 문제")
        print("")
        print_warning("수동 설정 방법:")
        print_info("  Xcode 열기 → Runner 타겟 → Signing & Capabilities → Team 선택")
        move_file(f"{pbxproj_path}.bak", pbxproj_path)
        return 1

    print_success("Xcode 프로젝트 설정 완료 (Manual Signing 적용됨)")
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
    print(f"{GREEN}║          🎉 iOS TestFlight 배포 설정 완료! 🎉                  ║{NC}")
    print(f"{GREEN}╚════════════════════════════════════════════════════════════════╝{NC}")
    print("")
    print(f"{YELLOW}★ 마법사 우선 아키텍처 ★{NC}")
    print("  모든 설정이 완료되었습니다. 워크플로우는 이 파일들을 그대로 사용합니다.")
    print("")
    print(f"{CYAN}생성/수정된 파일:{NC}")
    print("  ✅ ios/Gemfile                    (Fastlane 의존성)")
    print("  ✅ ios/fastlane/Fastfile          (TestFlight 업로드) ★ 워크플로우에서 직접 사용")
    print("  ✅ ios/ExportOptions.plist        (IPA 익스포트 설정) ★ 핵심")
    print("  ✅ ios/Runner.xcodeproj           (Manual Signing 패치) ★ 핵심")
    print("  ✅ ios/Runner/Info.plist          (암호화 설정)")
    print("")
    print(f"{CYAN}설정된 정보:{NC}")
    print(f"  • Bundle ID: {BUNDLE_ID}")
    print(f"  • Team ID: {TEAM_ID}")
    print(f"  • Profile Name: {PROFILE_NAME}")
    print("  • Code Sign Style: Manual")
    print(f"  • 암호화 설정: {encryption_display}")
    print("")
    print(f"{CYAN}빌드 파이프라인:{NC}")
    print("  1. flutter build ios --no-codesign")
    print("  2. xcodebuild archive")
    print("  3. xcodebuild -exportArchive (ExportOptions.plist 사용)")
    print("  4. fastlane upload_testflight (Fastfile의 lane 사용)")
    print("")
    print(f"{YELLOW}다음 단계:{NC}")
    print("  1. GitHub Secrets 설정:")
    print("     • APPLE_CERTIFICATE_BASE64")
    print("     • APPLE_CERTIFICATE_PASSWORD")
    print("     • APPLE_PROVISIONING_PROFILE_BASE64")
    print("     • IOS_PROVISIONING_PROFILE_NAME")
    print("     • APP_STORE_CONNECT_API_KEY_ID")
    print("     • APP_STORE_CONNECT_ISSUER_ID")
    print("     • APP_STORE_CONNECT_API_KEY_BASE64")
    print("")
    print("  2. 변경사항 커밋:")
    print("     git add ios/")
    print('     git commit -m "chore: iOS TestFlight 배포 설정"')
    print("")
    print("  3. deploy 브랜치로 푸시하여 빌드 테스트")
    print("")
    print("🎛️  배포 모드 설정 (선택):")
    print("   GitHub repo Variables에 IOS_DEPLOY_MODE 를 설정하면 기본 배포 범위를 정할 수 있습니다.")
    print("     store_only    : TestFlight 업로드까지만 (기본)")
    print("     store_prepare : App Store 제출 직전까지 (사람이 ASC에서 Add for Review)")
    print("     store_submit  : App Store 심사 자동 제출 (정식 출시 1회 수동 이후부터 가능)")
    print("   워크플로우 수동 실행 시 deploy_mode 입력이 이 변수보다 우선합니다.")


# ===================================================================
# 메인 실행
# ===================================================================

# ===================================================================
# 3종 공통 인자 계약 (testflight / playstore / firebase 동일)
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
# ⚠️ 이 블록은 3종 .py에 동일하게 존재해야 한다.
#    _shared/check-consistency.py 가 동일성을 검증한다.
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
                    print_error(f"--{key} 값이 없습니다.")
                    sys.exit(1)
                named[key] = params[i + 1]
                i += 2
            if key not in order:
                print_error(f"알 수 없는 옵션입니다: --{key}")
                print(f"사용 가능: {', '.join('--' + k for k in order)}")
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


def cmd_setup(params):
    print("")
    print(f"{CYAN}╔════════════════════════════════════════════════════════════════╗{NC}")
    print(f"{CYAN}║       Flutter iOS TestFlight 초기화 스크립트                   ║{NC}")
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
        print(f"{YELLOW}⚠️  dry-run 모드 — 실제 파일은 만들거나 고치지 않습니다.{NC}")
        print("")

    # 매개변수 검증
    validate_params(params)

    print(f"{BLUE}프로젝트 경로:{NC} {PROJECT_PATH}")
    print(f"{BLUE}Bundle ID:{NC} {BUNDLE_ID}")
    print(f"{BLUE}Team ID:{NC} {TEAM_ID}")
    print(f"{BLUE}Profile Name:{NC} {PROFILE_NAME}")
    print(f"{BLUE}암호화 사용:{NC} {USES_NON_EXEMPT_ENCRYPTION}")
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
        description="Flutter iOS TestFlight 초기화 스크립트",
    )
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser(
        "setup",
        add_help=False,
        help="iOS TestFlight 배포 설정 생성 (PROJECT_PATH BUNDLE_ID TEAM_ID PROFILE_NAME [USES_ENCRYPTION])",
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
