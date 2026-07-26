#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ===================================================================
# Flutter Android Play Store 마법사 로컬 실행 스크립트 (Python 단일 파일)
# ===================================================================
#
# 구 sh/ps1 스크립트 3쌍 + 패치 py 1개를 argparse 서브커맨드로 통합했다.
#   setup         : Play Store 배포 초기 설정 (구 setup 스크립트, sh 829줄 canonical)
#   apply         : 생성된 설정을 Flutter 프로젝트에 적용 (구 apply 스크립트)
#   detect-app-id : 환경 검사 + applicationId 자동 감지 (구 감지 스크립트, JSON 출력)
#
# ★ 로직 보존 원칙 ★
# - 구 .sh가 canonical이다. 동일 입력 → 동일 산출물(파일 경로/내용), 동일 검증 순서,
#   동일 에러 메시지(한국어 문구 그대로), 동일 종료 코드를 유지한다.
# - .sh와 .ps1이 갈리던 지점은 .sh 기준으로 통일했고, 각 지점에 "sh/ps1 분기:" 주석으로
#   기록했다. Windows에서만 의미 있는 동작(프로세스 종료, SDK 경로, 사용자 env 등록)은
#   .ps1 동작을 Windows 분기로 채택했다.
# - 구 gradle 패치 py의 로직은 patch_build_gradle() 내부 함수로 문자열/정규식
#   한 글자도 바꾸지 않고 흡수했다 (단독 파일은 삭제됨).
#
# 사용법:
#   python playstore-wizard.py setup PROJECT_PATH APPLICATION_ID KEY_ALIAS STORE_PASSWORD KEY_PASSWORD VALIDITY_DAYS CERT_CN CERT_O CERT_L CERT_C
#   python playstore-wizard.py apply [config_json_file]
#   python playstore-wizard.py detect-app-id PROJECT_PATH
#
# stdlib 전용 (외부 패키지 금지) — 내부망/양OS 동작 목표.
# ===================================================================

import argparse
import os
import re
import shutil
import subprocess
import sys
import time

# 한국어 Windows cp949 콘솔 대응
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ===================================================================
# 색상 정의 (구 sh와 동일 팔레트)
# Windows에서는 ctypes로 VT 모드 활성화 시도, 실패 시 색코드 없이 출력
# ===================================================================


def _ansi_enabled():
    if os.name != "nt":
        return True
    # 파이프/리다이렉트면 sh와 동일하게 코드를 그대로 내보낸다
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


# 출력 함수 (setup: 구 sh와 동일)
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
# build.gradle.kts 자동 패치 (구 단독 패치 py에서 그대로 흡수 — 로직/문구 무변경)
# - key.properties 로드 코드 추가
# - signingConfigs 블록 추가/업데이트
# - buildTypes.release에 signingConfig 설정
# ===================================================================


def patch_build_gradle(gradle_file_path):
    """build.gradle.kts 파일을 자동으로 패치합니다."""

    # 1. 파일 읽기
    try:
        with open(gradle_file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        print(f"❌ 파일을 찾을 수 없습니다: {gradle_file_path}")
        return False
    except Exception as e:
        print(f"❌ 파일 읽기 오류: {e}")
        return False

    # 백업 생성 (게이트 경유 — dry-run/--no-backup 반영)
    backup_path = f"{gradle_file_path}.bak"
    if NO_BACKUP:
        print("ℹ️  --no-backup: 백업을 건너뜁니다")
    else:
        try:
            _write_text(backup_path, content)
            print(f"✅ 백업 생성: {backup_path}")
        except Exception as e:
            print(f"⚠️  백업 생성 실패 (계속 진행): {e}")

    original_content = content

    # 2. key.properties 로드 코드 추가 (없는 경우)
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
        # plugins { ... } 다음에 추가
        pattern = r'(plugins\s*\{[^}]*\})'
        replacement = r'\1\n' + key_properties_code
        content = re.sub(pattern, replacement, content, count=1, flags=re.DOTALL)
        print("✅ key.properties 로드 코드 추가")
    else:
        print("ℹ️  key.properties 로드 코드 이미 존재")

    # 3. signingConfigs 블록 추가/업데이트
    if 'signingConfigs {' not in content and 'signingConfigs{' not in content:
        # signingConfigs 블록 추가
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
        # android { 다음에 추가
        pattern = r'(android\s*\{)'
        replacement = r'\1\n' + signing_configs_code
        content = re.sub(pattern, replacement, content, count=1)
        print("✅ signingConfigs 블록 추가")
    else:
        print("ℹ️  signingConfigs 블록 이미 존재")
        # 기존 storeFile 경로 수정 (file(it) → rootProject.file(it))
        if 'storeFile = keystoreProperties["storeFile"]?.let { file(it) }' in content:
            content = content.replace(
                'storeFile = keystoreProperties["storeFile"]?.let { file(it) }',
                'storeFile = keystoreProperties["storeFile"]?.let { rootProject.file(it) }'
            )
            print("✅ 기존 storeFile 경로 수정 (file(it) → rootProject.file(it))")

    # 4. buildTypes.release에 signingConfig 설정
    # 기존 debug signingConfig 제거
    content = re.sub(
        r'\s*signingConfig\s*=\s*signingConfigs\.getByName\(["\']debug["\']\)',
        '',
        content
    )

    # release { } 블록에 signingConfig 추가 (없는 경우)
    if 'signingConfig = signingConfigs.getByName("release")' not in content and \
       "signingConfig = signingConfigs.getByName('release')" not in content:
        # release { 다음에 추가 (중복 방지)
        # buildTypes 블록 내부의 release 블록 찾기
        pattern = r'(buildTypes\s*\{[^}]*release\s*\{)'
        if re.search(pattern, content, re.DOTALL):
            replacement = r'\1\n            signingConfig = signingConfigs.getByName("release")'
            content = re.sub(pattern, replacement, content, count=1, flags=re.DOTALL)
            print("✅ release buildType에 signingConfig 추가")
        else:
            print("⚠️  release buildType 블록을 찾을 수 없습니다")
    else:
        print("ℹ️  release buildType에 signingConfig 이미 존재")

    # 5. flutter.source 설정 추가/수정
    if 'flutter {' in content or 'flutter{' in content:
        # source = "../.." 확인
        if not re.search(r'flutter\s*\{[^}]*source\s*=\s*"\.\.\/\.\."', content, re.DOTALL):
            # source = "." → "../.." 변경
            if re.search(r'flutter\s*\{[^}]*source\s*=\s*"\."', content, re.DOTALL):
                content = re.sub(
                    r'(flutter\s*\{[^}]*source\s*=\s*)"\."',
                    r'\1"../.."',
                    content,
                    count=1,
                    flags=re.DOTALL
                )
                print("✅ flutter.source updated to '../..' (project root)")
            # flutter 블록은 있지만 source가 없는 경우
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
        print("ℹ️  flutter 블록이 없습니다 (추가 필요 시 수동으로 추가하세요)")

    # 6. 파일 저장 (변경사항이 있는 경우에만)
    if content != original_content:
        try:
            _write_text(gradle_file_path, content)
            print("✅ build.gradle.kts 패치 완료!")
            return True
        except Exception as e:
            print(f"❌ 파일 저장 오류: {e}")
            # 백업에서 복원 시도
            if path_exists(backup_path):
                try:
                    _write_text(gradle_file_path, _read_text(backup_path))
                    print("✅ 백업에서 복원 완료")
                except Exception:
                    pass
            return False
    else:
        print("ℹ️  변경사항 없음 (이미 설정되어 있습니다)")
        return True


# ===================================================================
# 공통: 파일을 사용 중인 프로세스 찾기 및 종료 (setup 전용 헬퍼)
# sh/ps1 분기: sh는 lsof + pgrep, ps1은 Get-Process로 java/gradle 전체 종료.
#   POSIX에서는 sh 로직 그대로, Windows에서는 ps1과 동등한 taskkill 방식을 쓴다.
# ===================================================================


def stop_processes_using_file(file_path):
    if not os.path.isfile(file_path):
        return False

    print_info(f"파일을 사용 중인 프로세스 찾는 중: {file_path}")

    processes_killed = False

    if os.name != "nt":
        # lsof 명령어 사용 (Linux/macOS)
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
                    os.kill(pid, 0)  # kill -0: 살아있는지 확인
                except OSError:
                    continue
                try:
                    proc_name = subprocess.run(
                        ["ps", "-p", str(pid), "-o", "comm="],
                        capture_output=True, text=True, encoding="utf-8", errors="replace"
                    ).stdout.strip() or "unknown"
                except OSError:
                    proc_name = "unknown"
                print_warning(f"프로세스 종료 중: {proc_name} (PID: {pid})")
                try:
                    os.kill(pid, 9)
                    processes_killed = True
                except OSError:
                    pass
                time.sleep(0.5)

        # 모든 Java/Gradle 프로세스 종료 (파일이 잠겨있을 때)
        if not processes_killed:
            print_warning("파일을 사용하는 프로세스를 찾지 못했습니다. 모든 Java/Gradle 프로세스 종료 시도 중...")
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
                    print_warning(f"프로세스 종료 중: {proc_name} (PID: {pid})")
                    try:
                        os.kill(pid, 9)
                        processes_killed = True
                    except OSError:
                        pass
                    time.sleep(0.5)
    else:
        # Windows (ps1 방식): java/gradle 프로세스 강제 종료
        print_warning("파일을 사용하는 프로세스를 찾지 못했습니다. 모든 Java/Gradle 프로세스 종료 시도 중...")
        for proc_name in ("java", "javaw", "gradle", "gradlew"):
            try:
                rc = subprocess.run(
                    ["taskkill", "/F", "/IM", proc_name + ".exe"],
                    capture_output=True
                ).returncode
            except OSError:
                rc = 1
            if rc == 0:
                print_warning(f"프로세스 종료 중: {proc_name}")
                processes_killed = True
                time.sleep(0.5)

    if processes_killed:
        print_info("프로세스 종료 완료. 파일 핸들이 해제될 때까지 5초 대기 중...")
        time.sleep(5)
        return True

    return False


# ===================================================================
# setup 서브커맨드 (구 setup 스크립트 — sh canonical)
# ===================================================================

# keystore 생성 스킵 여부 (sh와 동일 — sh에서도 1로 바뀌는 경로는 없다, 동작 보존용)
KEYSTORE_SKIPPED = False


def show_help():
    print(f"""{CYAN}Flutter Android Play Store 초기화 스크립트{NC}

{YELLOW}★ 마법사 우선 아키텍처 ★{NC}
  모든 설정 파일은 이 마법사가 생성하고,
  GitHub Actions 워크플로우는 생성된 파일을 그대로 사용합니다.

{BLUE}빌드 파이프라인:{NC}
  1. flutter build appbundle (AAB 생성)
  2. fastlane deploy_internal (Play Store 업로드)

{BLUE}사용법 (권장 — 명명 플래그):{NC}
  python playstore-wizard.py setup \\
    --project-path /path/to/project \\
    --application-id com.example.app \\
    --key-alias my-release-key \\
    --store-password MyPass123 --key-password MyPass123 \\
    --validity-days 99999 \\
    --cert-cn "My Name" --cert-o "My Company" --cert-l "Seoul" --cert-c "KR"

{BLUE}사용법 (구형 — 위치인자 10개, 계속 지원):{NC}
  python playstore-wizard.py setup PROJECT_PATH APPLICATION_ID KEY_ALIAS STORE_PASSWORD KEY_PASSWORD VALIDITY_DAYS CERT_CN CERT_O CERT_L CERT_C
  ⚠️ 순서가 하나만 어긋나도 비밀번호가 잘못 저장됩니다. 명명 플래그를 권장합니다.

{BLUE}매개변수:{NC}
  --project-path      Flutter 프로젝트 루트 경로
  --application-id    Android 앱 Application ID (예: com.example.app)
  --key-alias         Keystore alias 이름
  --store-password    Keystore 비밀번호
  --key-password      Key 비밀번호
  --validity-days     유효기간 (일 단위, 예: 99999)
  --cert-cn           인증서 Common Name (예: "My Name")
  --cert-o            인증서 Organization (예: "My Company")
  --cert-l            인증서 Locality (예: "Seoul")
  --cert-c            인증서 Country Code (예: "KR")

{BLUE}공통 옵션 (3종 마법사 동일):{NC}
  --dry-run           무엇을 바꿀지만 출력하고 파일·keystore를 만들지 않음
  --no-backup         기존 파일 백업(.bak)을 만들지 않음
  --non-interactive   확인 프롬프트 없이 진행 (CI용)

{BLUE}예시:{NC}
  python playstore-wizard.py setup --project-path . --application-id com.example.app \\
    --key-alias my-release-key --store-password MyPass123 --key-password MyPass123 \\
    --validity-days 99999 --cert-cn "My Name" --cert-o "My Company" --cert-l "Seoul" --cert-c "KR" --dry-run

{BLUE}생성/수정되는 파일:{NC}
  - android/.gitignore                    .gitignore 업데이트 ★ 먼저 실행
  - android/app/keystore/key.jks         Keystore 생성 ★
  - android/key.properties               서명 정보 ★
  - android/app/build.gradle.kts         서명 설정 패치 ★
  - android/fastlane/Fastfile.playstore  Play Store 업로드 설정 ★
  - android/Gemfile                      Fastlane 의존성
""")


def validate_params(params):
    # sh/ps1 분기: ps1은 param() 필수 바인딩 + Application ID 정규식 검증이었지만,
    #   sh 기준(개수 검증 + '.' 포함 여부만)으로 통일.
    if len(params) < 10:
        print_error("매개변수가 부족합니다.")
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

    # 프로젝트 경로 확인
    if not os.path.isdir(ctx["PROJECT_PATH"]):
        print_error(f"프로젝트 경로가 존재하지 않습니다: {ctx['PROJECT_PATH']}")
        sys.exit(1)

    # pubspec.yaml 확인 (Flutter 프로젝트)
    if not os.path.isfile(os.path.join(ctx["PROJECT_PATH"], "pubspec.yaml")):
        print_error("Flutter 프로젝트가 아닙니다 (pubspec.yaml 없음)")
        sys.exit(1)

    # android 폴더 확인
    if not os.path.isdir(os.path.join(ctx["PROJECT_PATH"], "android")):
        print_error("Android 폴더가 없습니다. 'flutter create .' 명령을 먼저 실행하세요.")
        sys.exit(1)

    # Application ID 형식 확인
    if "." not in ctx["APPLICATION_ID"]:
        print_error(f"Application ID 형식이 올바르지 않습니다: {ctx['APPLICATION_ID']}")
        print_error("예시: com.example.app")
        sys.exit(1)

    # 비밀번호 확인
    if not ctx["STORE_PASSWORD"] or not ctx["KEY_PASSWORD"]:
        print_error("Keystore 비밀번호와 Key 비밀번호는 필수입니다.")
        sys.exit(1)

    # 유효기간 확인
    if not re.match(r"^[0-9]+$", ctx["VALIDITY_DAYS"]):
        print_error(f"유효기간은 숫자여야 합니다: {ctx['VALIDITY_DAYS']}")
        sys.exit(1)

    # 인증서 정보 확인
    if not ctx["CERT_CN"] or not ctx["CERT_O"] or not ctx["CERT_L"] or not ctx["CERT_C"]:
        print_error("인증서 정보(CN, O, L, C)는 모두 필수입니다.")
        sys.exit(1)

    # Country Code 길이 확인
    if len(ctx["CERT_C"]) != 2:
        print_error(f"Country Code는 2자리여야 합니다: {ctx['CERT_C']}")
        sys.exit(1)

    return ctx


def find_template_dir():
    # 스크립트 위치 기준
    script_dir = os.path.dirname(os.path.abspath(__file__))
    template_dir = os.path.join(script_dir, "templates")

    if not os.path.isdir(template_dir):
        print_error(f"템플릿 디렉토리를 찾을 수 없습니다: {template_dir}")
        sys.exit(1)

    print_info(f"템플릿 디렉토리: {template_dir}")
    return template_dir


# ── 쓰기 게이트 (--dry-run 지원) ─────────────────────────────────────
# 파일·keystore를 변경하는 원시 동작은 전부 아래 게이트를 거친다.
# DRY_RUN이면 디스크를 건드리지 않고 "무엇을 할지"만 출력한다.
#
# ⚠️ 오버레이가 필요한 이유
#   이 스크립트는 "쓰고 → 다시 읽어 검증"하는 단계가 있다. 쓰기만 건너뛰면
#   뒷 단계가 낡은 내용을 읽어 실제 실행과 다른 경로를 타고 거짓 실패를 낸다.
#   그래서 dry-run에서는 쓰였을 내용을 메모리에 두고 읽기가 그것을 먼저 본다.
#
# ⚠️ 이 블록은 3종 .py의 공통 계약이다 (_shared/check-consistency.py가 검증).
DRY_RUN = False
NO_BACKUP = False
_DRY_FS = {}
_DRY_DELETED = set()


def _dry(msg):
    print(f"{YELLOW}[dry-run]{NC} {msg}")


def copy_file(src, dst):
    if DRY_RUN:
        _dry(f"복사: {src} → {dst}")
        try:
            _DRY_FS[dst] = _read_text(src)
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
    if DRY_RUN:
        _dry(f"삭제: {path}")
        _DRY_FS.pop(path, None)
        _DRY_DELETED.add(path)
        return
    if os.path.exists(path):
        os.remove(path)


def move_file(src, dst):
    if DRY_RUN:
        _dry(f"이동: {src} → {dst}")
        try:
            _DRY_FS[dst] = _read_text(src)
            _DRY_DELETED.discard(dst)
        except OSError:
            pass
        _DRY_FS.pop(src, None)
        _DRY_DELETED.add(src)
        return
    shutil.move(src, dst)


def make_dirs(path):
    if DRY_RUN:
        _dry(f"디렉터리 생성: {path}")
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


def _read_text(path):
    if DRY_RUN:
        if path in _DRY_FS:
            return _DRY_FS[path]
        if path in _DRY_DELETED:
            raise FileNotFoundError(path)
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def _append_text(path, text):
    if DRY_RUN:
        _dry(f"추가: {path}")
        base = _read_text(path) if (path in _DRY_FS or path_exists(path)) else ""
        _DRY_FS[path] = base + text
        _DRY_DELETED.discard(path)
        return
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        f.write(text)


def _write_text(path, text):
    if DRY_RUN:
        _dry(f"쓰기: {path} ({len(text)} bytes)")
        _DRY_FS[path] = text
        _DRY_DELETED.discard(path)
        return
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def update_gitignore(ctx):
    print_step(".gitignore 업데이트 중...")

    project_path = ctx["PROJECT_PATH"]

    # Git 저장소 확인
    if not os.path.isdir(os.path.join(project_path, ".git")):
        print_info("Git 저장소가 아닙니다. .gitignore 업데이트를 건너뜁니다.")
        return

    gitignore_path = os.path.join(project_path, ".gitignore")
    android_gitignore_path = os.path.join(project_path, "android", ".gitignore")
    gitignore_updated = False

    # 루트 .gitignore 처리 (파일이 존재할 때만)
    # sh/ps1 분기: ps1은 4개 항목("# Android signing" 포함)이었지만 sh의 7개 항목을 채택.
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

        content = _read_text(gitignore_path)
        for entry in gitignore_entries:
            if entry not in content:  # grep -qF 대응 (고정 문자열 부분 일치)
                appended = f"\n# Play Store CI/CD - 민감한 파일 (자동 생성됨)\n{entry}\n"
                _append_text(gitignore_path, appended)
                content += appended
                print_info(f"루트 .gitignore에 추가: {entry}")
                gitignore_updated = True
    # 루트 .gitignore가 없으면 생성하지 않음 (Git 미사용 프로젝트 가능성)

    # android/.gitignore 처리
    if path_exists(android_gitignore_path):
        # 항목 확인 및 추가
        if "key.properties" not in _read_text(android_gitignore_path):
            _append_text(
                android_gitignore_path,
                "\n# Play Store Keystore (자동 생성됨)\nkey.properties\nkeystore/\n",
            )
            print_info("android/.gitignore에 추가됨")
            gitignore_updated = True
    else:
        # android/.gitignore가 없으면 생성
        make_dirs(os.path.join(project_path, "android"))
        _write_text(android_gitignore_path, """# Play Store CI/CD - 민감한 파일 (자동 생성됨)
key.properties
keystore/
*.jks
*.keystore

# 환경 변수 파일
.env
.env.local
.env.*.local
""")
        print_info("android/.gitignore 생성됨")
        gitignore_updated = True

    if gitignore_updated:
        print_success(".gitignore 업데이트 완료")
    else:
        print_info(".gitignore에 이미 모든 항목이 포함되어 있습니다.")


def _git(project_path, args, quiet_stdout=False, quiet_stderr=True):
    """git -C PROJECT_PATH ... 실행. sh와 동일하게 기본은 stderr만 숨긴다."""
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
    print_step(".gitignore 변경사항 커밋 중...")

    project_path = ctx["PROJECT_PATH"]

    # Git 저장소 확인
    if not os.path.isdir(os.path.join(project_path, ".git")):
        print_info("Git 저장소가 아닙니다. 커밋을 건너뜁니다.")
        return

    # Git 명령어 사용 가능 여부 확인
    if shutil.which("git") is None:
        print_warning("Git이 설치되어 있지 않습니다. 커밋을 건너뜁니다.")
        return

    gitignore_path = os.path.join(project_path, ".gitignore")
    android_gitignore_path = os.path.join(project_path, "android", ".gitignore")
    has_changes = False

    # .gitignore 변경사항 확인
    if path_exists(gitignore_path):
        if _git(project_path, ["diff", "--quiet", gitignore_path]) != 0:
            has_changes = True

    if path_exists(android_gitignore_path):
        if _git(project_path, ["diff", "--quiet", android_gitignore_path]) != 0:
            has_changes = True

    if has_changes:
        # 이미 추적 중인 파일 제거 (있는 경우)
        key_properties = os.path.join(project_path, "android", "key.properties")
        keystore_jks = os.path.join(project_path, "android", "app", "keystore", "key.jks")

        if _git(project_path, ["ls-files", "--error-unmatch", key_properties],
                quiet_stdout=True) == 0:
            print_warning("이미 추적 중인 key.properties를 Git에서 제거합니다...")
            _git(project_path, ["rm", "--cached", key_properties])

        if _git(project_path, ["ls-files", "--error-unmatch", keystore_jks],
                quiet_stdout=True) == 0:
            print_warning("이미 추적 중인 keystore 파일을 Git에서 제거합니다...")
            _git(project_path, ["rm", "--cached", keystore_jks])

        # .gitignore 커밋
        if path_exists(gitignore_path):
            _git(project_path, ["add", gitignore_path])
        if path_exists(android_gitignore_path):
            _git(project_path, ["add", android_gitignore_path])

        if _git(project_path, ["diff", "--cached", "--quiet"]) == 0:
            print_info(".gitignore에 변경사항이 없습니다 (이미 커밋됨).")
        else:
            # sh/ps1 분기: 커밋 메시지가 달랐다
            #   (ps1: "chore: Update .gitignore for Android signing files") — sh 문구 채택.
            if _git(project_path, ["commit", "-m", "chore: Add keystore files to .gitignore"]) == 0:
                print_success(".gitignore 변경사항 커밋 완료")
            else:
                print_warning("커밋 실패 (이미 커밋되었거나 변경사항 없음)")
    else:
        print_info(".gitignore에 변경사항이 없습니다.")


def create_keystore(ctx):
    print_step("Keystore 생성 중...")

    project_path = ctx["PROJECT_PATH"]
    keystore_dir = os.path.join(project_path, "android", "app", "keystore")
    keystore_path = os.path.join(keystore_dir, "key.jks")

    # 디렉토리 생성
    make_dirs(keystore_dir)

    # 기존 keystore 확인
    if path_exists(keystore_path):
        print_info(f"기존 keystore가 존재합니다: {keystore_path}")
        print_info("기존 keystore 덮어쓰기 중...")

        # 기존 keystore에서 alias 삭제 시도 (파일 삭제 전에)
        print_info("기존 keystore에서 alias 삭제 시도 중...")
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
            print_info("기존 alias가 keystore에서 삭제되었습니다")
        else:
            print_warning("keystore에서 alias 삭제 실패 (존재하지 않거나 비밀번호가 다를 수 있음)")
            print_warning("파일 삭제/교체를 시도합니다...")

        # 백업 파일이 있으면 삭제
        backup_path = keystore_path + ".bak"
        if path_exists(backup_path):
            remove_file(backup_path)

        # 파일 백업 시도
        try:
            move_file(keystore_path, backup_path)
            print_info(f"기존 keystore 백업: {backup_path}")
        except OSError:
            # 파일이 잠겨있으면 프로세스 종료 후 재시도
            print_warning("keystore 파일 이동 실패. 파일을 사용 중인 프로세스 종료 시도 중...")

            if stop_processes_using_file(keystore_path):
                try:
                    remove_file(keystore_path)
                    print_info("기존 keystore 삭제됨 (프로세스 종료 후)")
                except OSError:
                    print_error(f"프로세스 종료 후에도 keystore 파일 삭제 실패: {keystore_path}")
                    print_error("파일을 수동으로 삭제하거나 파일을 사용하는 프로그램을 닫으세요.")
                    sys.exit(1)
            else:
                print_error(f"keystore 파일 삭제 실패: {keystore_path}")
                print_error("파일을 수동으로 삭제하거나 파일을 사용하는 프로그램을 닫으세요.")
                sys.exit(1)

    # keytool 명령어 생성
    dname = f"CN={ctx['CERT_CN']}, O={ctx['CERT_O']}, L={ctx['CERT_L']}, C={ctx['CERT_C']}"

    print_info("Keystore 정보:")
    print_info(f"  • 경로: {keystore_path}")
    print_info(f"  • Alias: {ctx['KEY_ALIAS']}")
    print_info(f"  • 유효기간: {ctx['VALIDITY_DAYS']} days")
    print_info(f"  • 인증서: {dname}")

    # keytool 실행 (비밀번호는 stdin으로 전달)
    # sh/ps1 분기: ps1은 -genkeypair + stdin 미사용이었지만 sh의 -genkey + stdin 전달을 채택.
    #   sh와 동일하게 출력에서 "Warning:" 포함 라인은 숨긴다.
    stdin_text = (
        f"{ctx['STORE_PASSWORD']}\n{ctx['STORE_PASSWORD']}\n"
        f"{ctx['KEY_PASSWORD']}\n{ctx['KEY_PASSWORD']}\n{dname}\ny\n\n"
    )
    if DRY_RUN:
        _dry(f"keystore 생성(keytool): {keystore_path} (alias={ctx['KEY_ALIAS']}, {ctx['VALIDITY_DAYS']}일)")
        _DRY_FS[keystore_path] = "<dry-run keystore>"
        _DRY_DELETED.discard(keystore_path)
        print_success("keystore 생성 완료 (dry-run — 실제 파일 없음)")
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
            # sh는 keytool 출력 바이트를 그대로 흘려보냈다 — 로케일 인코딩(mac: UTF-8,
            # 한국어 Windows: cp949)으로 디코딩하는 것이 가장 근접한 동작이다.
            text=True, errors="replace",
        )
        for line in (proc.stdout or "").splitlines():
            if "Warning:" not in line:
                print(line)
    except OSError as e:
        # sh에서는 셸이 "command not found"를 출력하는 상황 — 오류 원문을 그대로 보여준다
        print(str(e))

    if path_exists(keystore_path):
        print_success(f"Keystore 생성 완료: {keystore_path}")
    else:
        print_error("Keystore 생성 실패!")
        sys.exit(1)


def create_key_properties(ctx):
    print_step("key.properties 생성 중...")

    # keystore 생성이 스킵되었으면 key.properties도 스킵
    if KEYSTORE_SKIPPED:
        print_warning("key.properties 생성 스킵 (keystore가 덮어쓰기되지 않음)")
        print_warning("⚠️ 기존 keystore를 사용하므로 key.properties의 비밀번호를 수동으로 확인하세요!")
        print_warning("   기존 keystore의 비밀번호를 android/key.properties에 입력해야 합니다.")
        print_warning("   또는 Step 2로 돌아가서 keystore를 덮어쓰기(y)로 다시 생성하세요.")
        return

    key_properties_path = os.path.join(ctx["PROJECT_PATH"], "android", "key.properties")

    # 기존 파일 백업 및 삭제
    if path_exists(key_properties_path):
        print_info("기존 key.properties 발견. 덮어쓰기 중...")
        backup_path = key_properties_path + ".bak"

        # 백업 파일이 있으면 삭제
        if path_exists(backup_path):
            remove_file(backup_path)

        # 파일 백업 시도
        try:
            copy_file(key_properties_path, backup_path)
            remove_file(key_properties_path)
            print_info(f"기존 key.properties 백업: {backup_path}")
        except OSError:
            # 파일이 잠겨있으면 프로세스 종료 후 재시도
            print_warning("key.properties 파일 백업/삭제 실패. 파일을 사용 중인 프로세스 종료 시도 중...")

            if stop_processes_using_file(key_properties_path):
                try:
                    remove_file(key_properties_path)
                    print_info("기존 key.properties 삭제됨 (프로세스 종료 후)")
                except OSError:
                    print_error(f"프로세스 종료 후에도 key.properties 파일 삭제 실패: {key_properties_path}")
                    print_error("파일을 수동으로 삭제하거나 파일을 사용하는 프로그램을 닫으세요.")
                    sys.exit(1)
            else:
                print_error(f"key.properties 파일 삭제 실패: {key_properties_path}")
                print_error("파일을 수동으로 삭제하거나 파일을 사용하는 프로그램을 닫으세요.")
                sys.exit(1)

    # sh/ps1 분기: ps1은 주석 없이 storePassword부터 쓰는 다른 내용이었다 — sh 내용 채택.
    key_properties_content = f"""# Release Keystore Configuration
# WARNING: Do not commit this file to version control!
# This file is automatically generated by Play Store Wizard

storeFile=app/keystore/key.jks
storePassword={ctx['STORE_PASSWORD']}
keyAlias={ctx['KEY_ALIAS']}
keyPassword={ctx['KEY_PASSWORD']}
"""

    # 파일 쓰기 시도
    try:
        _write_text(key_properties_path, key_properties_content)
    except OSError:
        # 파일이 잠겨있으면 프로세스 종료 후 재시도
        print_warning("key.properties 파일 쓰기 실패. 파일을 사용 중인 프로세스 종료 시도 중...")

        if stop_processes_using_file(key_properties_path):
            try:
                _write_text(key_properties_path, key_properties_content)
                print_info("프로세스 종료 후 key.properties 쓰기 성공")
            except OSError:
                print_error("프로세스 종료 후에도 key.properties 파일 쓰기 실패")
                print_error("파일이 여전히 잠겨있을 수 있습니다. 파일을 사용하는 프로그램을 수동으로 닫고 다시 시도하세요.")
                sys.exit(1)
        else:
            print_error("key.properties 파일 쓰기 실패")
            print_error("파일이 다른 프로세스에서 사용 중일 수 있습니다. 파일을 사용하는 프로그램을 닫고 다시 시도하세요.")
            sys.exit(1)

    # 파일이 제대로 생성되었는지 확인
    if not path_exists(key_properties_path):
        print_error(f"key.properties 파일이 생성되지 않았습니다: {key_properties_path}")
        sys.exit(1)

    # 파일 내용 확인
    if "storePassword" not in _read_text(key_properties_path):
        print_error(f"key.properties 파일이 존재하지만 내용이 유효하지 않습니다: {key_properties_path}")
        sys.exit(1)

    print_success(f"key.properties 생성 완료: {key_properties_path}")
    print_info(f"  • Store Password: {ctx['STORE_PASSWORD']}")
    print_info(f"  • Key Alias: {ctx['KEY_ALIAS']}")
    print_info(f"  • Key Password: {ctx['KEY_PASSWORD']}")


def patch_build_gradle_step(ctx):
    print_step("build.gradle.kts에 서명 설정 추가 중...")

    gradle_file = os.path.join(ctx["PROJECT_PATH"], "android", "app", "build.gradle.kts")

    if not path_exists(gradle_file):
        print_error(f"build.gradle.kts 파일을 찾을 수 없습니다: {gradle_file}")
        sys.exit(1)

    # 구 sh의 패치 스크립트 존재 확인 + Python 실행 파일 탐지는 내부 함수 흡수로 불필요해짐.
    # sh/ps1 분기: ps1은 자체 regex 패치(문구/패턴이 미묘하게 다름)였지만,
    #   sh가 호출하던 패치 py 로직(위 patch_build_gradle)을 그대로 채택.
    try:
        success = patch_build_gradle(gradle_file)
    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        success = False

    if not success:
        # 구 sh는 set -e 때문에 패치 실패 시 추가 메시지 없이 종료 코드 1로 끝났다 — 동일하게 유지.
        sys.exit(1)

    print_success("build.gradle.kts 자동 설정 완료!")


def create_fastfile(ctx, template_dir):
    print_step("Fastfile.playstore 생성 중...")

    fastlane_dir = os.path.join(ctx["PROJECT_PATH"], "android", "fastlane")
    fastfile_path = os.path.join(fastlane_dir, "Fastfile.playstore")
    template_fastfile = os.path.join(template_dir, "Fastfile.playstore.template")

    # fastlane 디렉토리 생성
    make_dirs(fastlane_dir)

    # 기존 파일 백업
    if path_exists(fastfile_path):
        print_warning(f"기존 Fastfile.playstore 백업: {fastfile_path}.bak")
        backup_file(fastfile_path)

    # 템플릿 파일 존재 확인
    if path_exists(template_fastfile):
        # 템플릿에서 복사하고 플레이스홀더 치환
        _write_text(
            fastfile_path,
            _read_text(template_fastfile).replace("{{APPLICATION_ID}}", ctx["APPLICATION_ID"]),
        )
        print_info("템플릿에서 생성됨")
    else:
        # 템플릿이 없으면 직접 생성
        # 주의: 구 sh 헤레독은 \#{...}의 백슬래시를 그대로 출력했다 (bash 실측 확인) — 바이트 동일 유지.
        # sh/ps1 분기: ps1 fallback은 package_name 없는 전혀 다른 내용이었다 — sh 내용 채택.
        _write_text(fastfile_path, f"""# Fastfile for Play Store Internal Testing Deployment
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

    print_success(f"Fastfile.playstore 생성 완료: {fastfile_path}")
    print_info("  → GitHub Actions 워크플로우에서 이 파일을 직접 사용합니다")


def create_gemfile(ctx):
    print_step("Gemfile 생성 중...")

    gemfile_path = os.path.join(ctx["PROJECT_PATH"], "android", "Gemfile")

    # 기존 파일 백업
    if path_exists(gemfile_path):
        print_warning(f"기존 Gemfile 백업: {gemfile_path}.bak")
        backup_file(gemfile_path)

    # sh/ps1 분기: ps1에는 "# frozen_string_literal: true" 줄이 없었다 — sh 내용 채택.
    _write_text(gemfile_path, """# frozen_string_literal: true

source "https://rubygems.org"

# Fastlane - Android 빌드 자동화
gem "fastlane", "~> 2.225"

# multi_json - google-apis transitive 의존성이 gemspec에 선언 누락한 upstream 버그 회피 (Gem::LoadError 방지)
gem "multi_json"
""")

    print_success(f"Gemfile 생성 완료: {gemfile_path}")


def print_completion(ctx):
    # sh/ps1 분기: ps1은 영어 요약 + base64 안내 등 다른 내용이었다 — sh 문구 채택.
    print("")
    print(f"{GREEN}╔════════════════════════════════════════════════════════════════╗{NC}")
    print(f"{GREEN}║          🎉 Android Play Store 배포 설정 완료! 🎉             ║{NC}")
    print(f"{GREEN}╚════════════════════════════════════════════════════════════════╝{NC}")
    print("")
    print(f"{YELLOW}★ 마법사 우선 아키텍처 ★{NC}")
    print("  모든 설정이 완료되었습니다. 워크플로우는 이 파일들을 그대로 사용합니다.")
    print("")
    print(f"{CYAN}생성/수정된 파일:{NC}")
    print("  ✅ android/.gitignore                    (.gitignore 업데이트)")
    print("  ✅ android/app/keystore/key.jks         (Keystore 생성) ★")
    print("  ✅ android/key.properties               (서명 정보) ★")
    print("  ✅ android/app/build.gradle.kts         (서명 설정 패치) ★")
    print("  ✅ android/fastlane/Fastfile.playstore  (Play Store 업로드) ★")
    print("  ✅ android/Gemfile                      (Fastlane 의존성)")
    print("")
    print(f"{CYAN}설정된 정보:{NC}")
    print(f"  • Application ID: {ctx['APPLICATION_ID']}")
    print(f"  • Key Alias: {ctx['KEY_ALIAS']}")
    print(f"  • Keystore 유효기간: {ctx['VALIDITY_DAYS']} days")
    print("")
    print(f"{CYAN}빌드 파이프라인:{NC}")
    print("  1. flutter build appbundle (AAB 생성)")
    print("  2. fastlane deploy_internal (Fastfile.playstore 사용)")
    print("")
    print(f"{YELLOW}다음 단계:{NC}")
    print("  1. GitHub Secrets 설정:")
    print("     • RELEASE_KEYSTORE_BASE64 (keystore 파일을 base64 인코딩)")
    print("     • RELEASE_KEYSTORE_PASSWORD")
    print("     • RELEASE_KEY_ALIAS")
    print("     • RELEASE_KEY_PASSWORD")
    print("     • GOOGLE_PLAY_SERVICE_ACCOUNT_JSON_BASE64")
    print("")
    print("  2. 추가 변경사항 커밋 (필요시):")
    print("     git add android/")
    print("     git commit -m \"chore: Android Play Store 배포 설정\"")
    print("     (참고: .gitignore는 이미 자동으로 커밋되었습니다)")
    print("")
    print("  3. deploy 브랜치로 푸시하여 빌드 테스트")
    print("")
    print("🎛️  배포 모드 설정 (선택):")
    print("   GitHub repo Variables에 ANDROID_DEPLOY_MODE 를 설정하면 기본 배포 범위를 정할 수 있습니다.")
    print("     store_only    : 내부 테스트(internal) 업로드까지만 (기본)")
    print("     store_prepare : production draft 승급 (콘솔에서 '출시 시작' 대기)")
    print("     store_submit  : production 심사 자동 등록 (정식 출시 1회 수동 이후부터 가능)")
    print("   워크플로우 수동 실행 시 deploy_mode 입력이 이 변수보다 우선합니다.")


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
    print(f"{CYAN}║       Flutter Android Play Store 초기화 스크립트               ║{NC}")
    print(f"{CYAN}╚════════════════════════════════════════════════════════════════╝{NC}")
    print("")

    # 도움말 옵션 확인
    if params and params[0] in ("-h", "--help"):
        show_help()
        sys.exit(0)

    # 명명 플래그 → 위치인자 정규화 (구/신 호출 형식 모두 지원)
    global DRY_RUN, NO_BACKUP
    params, cli_opts = normalize_params(params, ("project-path", "application-id", "key-alias", "store-password", "key-password", "validity-days", "cert-cn", "cert-o", "cert-l", "cert-c"))
    DRY_RUN = cli_opts["dry_run"]
    NO_BACKUP = not cli_opts["backup"]
    if DRY_RUN:
        print(f"{YELLOW}⚠️  dry-run 모드 — 실제 파일은 만들거나 고치지 않습니다.{NC}")
        print("")

    # 매개변수 검증
    ctx = validate_params(params)

    print(f"{BLUE}프로젝트 경로:{NC} {ctx['PROJECT_PATH']}")
    print(f"{BLUE}Application ID:{NC} {ctx['APPLICATION_ID']}")
    print(f"{BLUE}Key Alias:{NC} {ctx['KEY_ALIAS']}")
    print(f"{BLUE}유효기간:{NC} {ctx['VALIDITY_DAYS']} days")
    print("")

    # 템플릿 디렉토리 찾기
    template_dir = find_template_dir()

    # 파일 생성 (순서 중요!)
    update_gitignore(ctx)       # 1. 먼저 .gitignore 업데이트
    commit_gitignore(ctx)       # 2. .gitignore 커밋 (Keystore 생성 전!)
    create_keystore(ctx)        # 3. 이제 Keystore 생성 (안전)
    create_key_properties(ctx)
    patch_build_gradle_step(ctx)
    create_fastfile(ctx, template_dir)
    create_gemfile(ctx)

    # 완료
    print_completion(ctx)


# ===================================================================
# apply 서브커맨드 (구 apply 스크립트 — sh canonical)
# 프로젝트 루트(cwd)에서 실행한다. config_json_file 인자는 구 sh와 동일하게 받되 사용하지 않는다.
# ===================================================================


def _sed_double_quoted_greedy(line):
    """sed 's/.*"\\(.*\\)".*/\\1/' 대응 — 매치 없으면 원본 라인 그대로 반환."""
    return re.sub(r'.*"(.*)".*', r'\1', line, count=1)


def cmd_apply(params):
    # params: [config_json_file] — 구 sh도 인자를 읽지 않았다 (usage에만 존재).
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
    # sh/ps1 분기: ps1은 존재 시 "Exists:"를 출력했지만 sh는 항상 Created를 출력 — sh 채택.
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
        gradle_lines = _read_text(gradle_file).splitlines()
        app_id = ""
        if gradle_type == "kts":
            matched = [l for l in gradle_lines if re.search(r'applicationId\s*=', l)]
        else:
            matched = [l for l in gradle_lines if re.search(r'applicationId\s', l)]
        if matched:
            app_id = _sed_double_quoted_greedy(matched[0])

        _write_text("android/fastlane/Fastfile.playstore", f"""# Fastfile for Play Store Internal Testing Deployment
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
        _write_text("android/key.properties", """# Release Keystore Configuration
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

    gitignore_content = _read_text(".gitignore") if path_exists(".gitignore") else ""
    for entry in gitignore_entries:
        if entry not in gitignore_content:
            _append_text(".gitignore", entry + "\n")
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
# detect-app-id 서브커맨드 (구 감지 스크립트 — sh canonical, JSON 출력)
# ===================================================================


def _detect_android_env_posix():
    """구 sh 로직: mac/linux SDK 탐색 + 쉘 rc 자동 추가."""
    env_status = "ok"
    env_message = ""

    home = os.path.expanduser("~")
    android_home = os.environ.get("ANDROID_HOME", "")

    # ANDROID_HOME 확인
    if not android_home:
        # 기본 경로에서 Android SDK 찾기
        if os.path.isdir(os.path.join(home, "Library", "Android", "sdk")):
            android_home = os.path.join(home, "Library", "Android", "sdk")
        elif os.path.isdir(os.path.join(home, "Android", "Sdk")):
            android_home = os.path.join(home, "Android", "Sdk")

    # ANDROID_HOME이 여전히 없으면 자동 설정 시도
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

    # ~/.zshrc에 ANDROID_HOME 추가 (없으면)
    if android_home and os.path.isdir(android_home):
        shell_rc = ""
        if path_exists(os.path.join(home, ".zshrc")):
            shell_rc = os.path.join(home, ".zshrc")
        elif path_exists(os.path.join(home, ".bashrc")):
            shell_rc = os.path.join(home, ".bashrc")
        elif path_exists(os.path.join(home, ".bash_profile")):
            shell_rc = os.path.join(home, ".bash_profile")

        if shell_rc:
            # ANDROID_HOME이 설정되어 있는지 확인
            if "export ANDROID_HOME" not in _read_text(shell_rc):
                _append_text(
                    shell_rc,
                    "\n# Android SDK (자동 추가됨 by playstore-wizard)\n"
                    f"export ANDROID_HOME=\"{android_home}\"\n"
                    "export PATH=\"$PATH:$ANDROID_HOME/platform-tools\"\n"
                    "export PATH=\"$PATH:$ANDROID_HOME/cmdline-tools/latest/bin\"\n",
                )
                env_message = f"ANDROID_HOME을 {shell_rc}에 자동 추가했습니다. 터미널을 다시 열거나 source {shell_rc} 실행"

        # 현재 세션에도 적용
        os.environ["ANDROID_HOME"] = android_home
        os.environ["PATH"] = (
            os.environ.get("PATH", "")
            + os.pathsep + os.path.join(android_home, "platform-tools")
            + os.pathsep + os.path.join(android_home, "cmdline-tools", "latest", "bin")
        )
    else:
        env_status = "warning"
        env_message = "Android SDK를 찾을 수 없습니다. Android Studio에서 SDK Manager를 열어 설치하세요."

    return env_status, env_message


def _detect_android_env_windows():
    """sh/ps1 분기: sh의 SDK 경로는 mac/linux 전용이라 Windows에서는 ps1 로직을 채택
    (LOCALAPPDATA 경로 탐색 + 사용자 환경 변수 영구 등록)."""
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
        # 환경 변수 설정 (현재 세션)
        os.environ["ANDROID_HOME"] = android_home

        # 사용자 환경 변수에 추가 (영구적) - 없는 경우만 (ps1의 SetEnvironmentVariable 대응)
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
                    env_message = "ANDROID_HOME을 사용자 환경 변수에 추가했습니다. 터미널을 다시 열어주세요."
        except OSError:
            pass
    else:
        env_status = "warning"
        env_message = "Android SDK를 찾을 수 없습니다. Android Studio에서 SDK Manager를 열어 설치하세요."

    return env_status, env_message


def cmd_detect_app_id(project_path):
    # 프로젝트 경로 확인
    if not project_path:
        print('{"error": "프로젝트 경로를 입력하세요", "env": "error"}')
        sys.exit(1)

    if not os.path.isdir(project_path):
        print('{"error": "프로젝트 경로가 존재하지 않습니다", "env": "error"}')
        sys.exit(1)

    # 1. Android SDK 환경 검사 및 자동 설정
    if os.name == "nt":
        env_status, env_message = _detect_android_env_windows()
    else:
        env_status, env_message = _detect_android_env_posix()

    # 2. keytool 명령어 확인
    keytool_status = "ok"
    if shutil.which("keytool") is None:
        # Java가 설치되어 있는지 확인
        if shutil.which("java") is None:
            keytool_status = "error"
            env_status = "error"
            if os.name == "nt":
                # sh/ps1 분기: sh 메시지의 brew 안내는 mac 전용이라 Windows는 ps1 문구 채택
                env_message = "Java가 설치되어 있지 않습니다. JDK를 설치하세요."
            else:
                env_message = "Java가 설치되어 있지 않습니다. JDK를 설치하세요: brew install openjdk"
        else:
            keytool_status = "warning"

    # 3. Application ID 추출
    if path_exists(os.path.join(project_path, "android", "app", "build.gradle.kts")):
        gradle_file = os.path.join(project_path, "android", "app", "build.gradle.kts")
        gradle_type = "kts"
    elif path_exists(os.path.join(project_path, "android", "app", "build.gradle")):
        gradle_file = os.path.join(project_path, "android", "app", "build.gradle")
        gradle_type = "groovy"
    else:
        print('{"error": "build.gradle 파일을 찾을 수 없습니다", "env": "error"}')
        sys.exit(1)

    gradle_lines = _read_text(gradle_file).splitlines()
    application_id = ""

    # Kotlin DSL (build.gradle.kts)
    if gradle_type == "kts":
        matched = [l for l in gradle_lines if re.search(r'applicationId\s*=', l)]
        if matched:
            # sed 's/.*"\([^"]*\)".*/\1/' 대응 (매치 없으면 라인 그대로 — sh 동작 보존)
            application_id = re.sub(r'.*"([^"]*)".*', r'\1', matched[0], count=1)

    # Groovy (build.gradle)
    if not application_id:
        matched = [l for l in gradle_lines
                   if re.search(r'applicationId\s+', l) and "=" not in l]
        if matched:
            line = re.sub(r'.*"([^"]*)".*', r'\1', matched[0], count=1)
            line = re.sub(r".*'([^']*)'.*", r'\1', line, count=1)
            application_id = line

    # namespace에서 추출 시도
    if not application_id:
        matched = [l for l in gradle_lines if re.search(r'namespace\s*=', l)]
        if matched:
            application_id = re.sub(r'.*"([^"]*)".*', r'\1', matched[0], count=1)

    if not application_id:
        print('{"error": "applicationId를 찾을 수 없습니다", "env": "error"}')
        sys.exit(1)

    # 4. 결과 출력 (JSON) — 구 sh와 동일한 수동 포맷 유지
    if env_message:
        print(f'{{"applicationId": "{application_id}", "env": "{env_status}", "keytool": "{keytool_status}", "message": "{env_message}", "gradleType": "{gradle_type}"}}')
    else:
        print(f'{{"applicationId": "{application_id}", "env": "{env_status}", "keytool": "{keytool_status}", "gradleType": "{gradle_type}"}}')


# ===================================================================
# 엔트리포인트
# ===================================================================


def build_parser():
    parser = argparse.ArgumentParser(
        prog="playstore-wizard.py",
        description="Flutter Android Play Store 마법사 로컬 실행 스크립트",
    )
    sub = parser.add_subparsers(dest="command")

    # setup은 구 sh처럼 -h/--help와 위치 인자를 자체 처리한다 (argparse 개입 차단)
    p_setup = sub.add_parser(
        "setup", add_help=False,
        help="Play Store 배포 초기 설정 (keystore, key.properties, build.gradle.kts, Fastfile, Gemfile)",
    )
    p_setup.add_argument("params", nargs=argparse.REMAINDER)

    p_apply = sub.add_parser(
        "apply", add_help=False,
        help="생성된 설정을 Flutter 프로젝트에 적용 (프로젝트 루트에서 실행)",
    )
    p_apply.add_argument("params", nargs=argparse.REMAINDER)

    p_detect = sub.add_parser(
        "detect-app-id", add_help=False,
        help="환경 검사 + applicationId 자동 감지 (JSON 출력)",
    )
    p_detect.add_argument("params", nargs=argparse.REMAINDER)

    return parser


def main():
    # 서브커맨드 뒤의 인자는 구 sh처럼 원문 그대로 각 커맨드가 처리한다.
    # (argparse REMAINDER는 "-h" 선행 인자를 삼키지 못해 수동 디스패치를 쓴다)
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
