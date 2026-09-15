#!/usr/bin/env python3
# ===================================================================
# version_manager.py — 프로젝트 버전 관리 (version_manager.sh의 Python 포팅)
# ===================================================================
#
# 크로스 플랫폼(Windows/macOS/Linux) 표준 라이브러리 전용 — yq/jq 불필요.
# 기존 version_manager.sh는 이 파일로 위임하는 shim이며, 호출 계약은 동일하다:
#   - 결과값은 stdout 마지막 줄, 로그는 stderr (워크플로우의 `| tail -n 1` 호환)
#   - 커맨드: get | get-code | increment | increment-code | set | sync | validate
#
# version.yml 스키마 (v4.1.0 SSOT):
#   - project_types 배열이 유일한 소스 (첫 항목이 primary)
#   - 단수 project_type 키는 제거됨 — 잔존 시 무시(경고), 단수-only legacy는 명시적 실패
#   - project_paths 맵으로 모노레포 서브폴더 지원
# ===================================================================

import json
import os
import re
import sys
from pathlib import Path

VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
VERSION_YML = Path("version.yml")


# ── 로그 (stderr — .sh 이모지 동일) ─────────────────────────────────
def log_info(msg): print(f"ℹ️  {msg}", file=sys.stderr)
def log_success(msg): print(f"✅ {msg}", file=sys.stderr)
def log_error(msg): print(f"❌ {msg}", file=sys.stderr)
def log_warning(msg): print(f"⚠️  {msg}", file=sys.stderr)
def log_debug(msg):
    if os.environ.get("DEBUG") == "true":
        print(f"🔍 DEBUG: {msg}", file=sys.stderr)


# ── version.yml 읽기/쓰기 (라인 단위 — 주석·서식 보존) ────────────────
def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str):
    path.write_text(content, encoding="utf-8", newline="\n")


def yml_lines():
    return read_text(VERSION_YML).split("\n")


def parse_project_types() -> list:
    """project_types: ["a","b"] → ["a","b"] (주석 라인 제외). 없으면 []."""
    if not VERSION_YML.is_file():
        return []
    for line in yml_lines():
        if line.lstrip().startswith("#"):
            continue
        m = re.match(r"^project_types:\s*(\[[^\]]*\])", line)
        if m:
            return [t.strip().strip('"').strip("'") for t in m.group(1)[1:-1].split(",") if t.strip()]
    return []


def parse_legacy_single_type() -> str:
    """v4.1.0 이전 단수 project_type 키 (감지용 — 값은 쓰지 않음)."""
    for line in yml_lines():
        if line.lstrip().startswith("#"):
            continue
        m = re.match(r"^project_type:\s*[\"']?([A-Za-z0-9_-]+)", line)
        if m:
            return m.group(1)
    return ""


def get_type_path(t: str) -> str:
    """project_paths.<type> — 키 없으면 '.' (legacy: 루트 기준)."""
    in_paths = False
    for line in yml_lines():
        if re.match(r"^project_paths:", line):
            in_paths = True
            continue
        if in_paths:
            m = re.match(r'^\s+([A-Za-z0-9_-]+):\s*"([^"]*)"', line)
            if m:
                if m.group(1) == t:
                    return m.group(2) or "."
            elif re.match(r"^\S", line):
                break
    return "."


def get_yml_version() -> str:
    for line in yml_lines():
        if line.lstrip().startswith("#"):
            continue
        m = re.match(r"^version:\s*[\"']?([0-9][0-9.]*)[\"']?", line)
        if m:
            return m.group(1)
    return "0.0.0"


def set_yml_field(pattern: str, new_line_fn):
    """pattern에 걸리는 첫 라인을 new_line_fn(match)로 교체. 교체 여부 반환."""
    lines = yml_lines()
    for i, line in enumerate(lines):
        if line.lstrip().startswith("#"):
            continue
        m = re.match(pattern, line)
        if m:
            lines[i] = new_line_fn(m)
            write_text(VERSION_YML, "\n".join(lines))
            return True
    return False


# ── 설정 읽기 (.sh read_version_config 등가, v4.1.0 SSOT) ───────────
class Config:
    def __init__(self):
        if not VERSION_YML.is_file():
            log_error("version.yml 파일을 찾을 수 없습니다!")
            sys.exit(1)

        log_debug("version.yml 파싱 시작 (stdlib 사용)")

        self.types = parse_project_types()
        legacy = parse_legacy_single_type()

        if self.types:
            if legacy:
                log_warning("project_type 단수 키는 v4.1.0부터 무시됩니다 — version.yml에서 해당 라인을 제거하세요 (project_types 배열이 유일한 소스)")
            self.primary = self.types[0]
        elif legacy:
            log_error("version.yml이 v4.1.0 이전 형식입니다 (project_type 단수 키만 존재).")
            log_error("전환 절차: project_type 라인을 삭제하고 project_types 배열로 교체하세요.")
            log_error(f'  예) project_type: "{legacy}"  →  project_types: ["{legacy}"]')
            sys.exit(1)
        else:
            self.primary = "basic"

        self.current_version = get_yml_version()
        self.version_file = self._resolve_version_file()

        log_info("프로젝트 설정:")
        if self.types:
            log_info(f"  타입(배열): {','.join(self.types)}")
        log_info(f"  타입(primary): {self.primary}")
        log_info(f"  버전 파일(primary): {self.version_file}")
        log_info(f"  현재 버전: {self.current_version}")

    def _resolve_version_file(self) -> str:
        p = get_type_path(self.primary)
        t = self.primary
        if t == "spring":
            return f"{p}/build.gradle"
        if t == "flutter":
            return f"{p}/pubspec.yaml"
        if t in ("react", "node"):
            return f"{p}/package.json"
        if t == "react-native":
            ios_dir = Path(p) / "ios"
            if ios_dir.is_dir():
                plists = sorted(ios_dir.rglob("Info.plist"))
                if plists:
                    return str(plists[0])
            return f"{p}/android/app/build.gradle"
        if t == "react-native-expo":
            return f"{p}/app.json"
        if t == "python":
            return f"{p}/pyproject.toml"
        return "version.yml"  # basic 및 그 외


# ── 버전 유틸 ────────────────────────────────────────────────────────
def validate_version(version: str) -> bool:
    if VERSION_RE.match(version or ""):
        return True
    log_error(f"잘못된 버전 형식: '{version}' (x.y.z 형식이어야 함)")
    return False


def increment_patch(version: str) -> str:
    major, minor, patch = version.split(".")
    return f"{major}.{minor}.{int(patch) + 1}"


def increment_version(version: str, bump: str = "patch") -> str:
    """bump: 'major'|'minor'|'patch'. 생략하면 기존과 동일하게 patch 증가(하위호환)."""
    major, minor, patch = version.split(".")
    if bump == "major":
        return f"{int(major) + 1}.0.0"
    if bump == "minor":
        return f"{major}.{int(minor) + 1}.0"
    return f"{major}.{minor}.{int(patch) + 1}"


def higher_version(v1: str, v2: str) -> str:
    a = [int(x) for x in v1.split(".")[:3]]
    b = [int(x) for x in v2.split(".")[:3]]
    return v1 if a >= b else v2


# ── version_code ─────────────────────────────────────────────────────
def get_version_code() -> int:
    if not VERSION_YML.is_file():
        log_warning("version.yml 파일이 없습니다. 기본값 1 반환")
        return 1
    for line in yml_lines():
        if line.lstrip().startswith("#"):
            continue
        m = re.match(r"^version_code:\s*([0-9]+)", line)
        if m:
            log_debug(f"현재 version_code: {m.group(1)}")
            return int(m.group(1))
    # 필드 없음 → version 라인 다음에 추가 (초기값 1)
    log_warning("version_code 필드가 없습니다. 자동으로 추가합니다 (초기값: 1)")
    lines = yml_lines()
    for i, line in enumerate(lines):
        if not line.lstrip().startswith("#") and re.match(r"^version:", line):
            lines.insert(i + 1, "version_code: 1 # app build number")
            write_text(VERSION_YML, "\n".join(lines))
            break
    else:
        lines.append("version_code: 1 # app build number")
        write_text(VERSION_YML, "\n".join(lines))
    log_success("version_code 필드 추가 완료: 1")
    return 1


def set_version_code(new_code: int):
    replaced = set_yml_field(
        r"^version_code:\s*[0-9]+",
        lambda m: f"version_code: {new_code} # app build number",
    )
    if not replaced:
        get_version_code()  # 필드 생성
        set_yml_field(r"^version_code:\s*[0-9]+", lambda m: f"version_code: {new_code} # app build number")


def increment_version_code() -> int:
    current = get_version_code()
    new_code = current + 1
    log_info(f"VERSION_CODE 증가: {current} → {new_code}")
    set_version_code(new_code)
    log_success(f"VERSION_CODE 업데이트 완료: {new_code}")
    return new_code


# ── 파일별 버전 읽기/쓰기 헬퍼 ────────────────────────────────────────
def read_json(path: Path):
    return json.loads(read_text(path))


def write_json(path: Path, obj):
    # jq 등가: 2-space indent + 마지막 개행
    write_text(path, json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def sub_file(path: Path, pattern: str, repl, count=0, flags=re.MULTILINE) -> bool:
    text = read_text(path)
    new_text, n = re.subn(pattern, repl, text, count=count, flags=flags)
    if n:
        write_text(path, new_text)
    return n > 0


def plist_set_version(path: Path, new_version: str) -> bool:
    """CFBundleShortVersionString 키 다음 <string> 값을 교체 (.sh sed 등가)."""
    lines = read_text(path).split("\n")
    changed = False
    for i, line in enumerate(lines):
        if "CFBundleShortVersionString" in line and i + 1 < len(lines):
            lines[i + 1] = re.sub(r"<string>[^<]*</string>", f"<string>{new_version}</string>", lines[i + 1])
            changed = True
    if changed:
        write_text(path, "\n".join(lines))
    return changed


def get_project_file_version(cfg: Config) -> str:
    vf = Path(cfg.version_file)
    if cfg.primary == "basic" or not vf.is_file():
        return cfg.current_version

    v = ""
    t = cfg.primary
    try:
        if t == "spring":
            m = re.search(r"^\s*version\s*=\s*['\"](\d+\.\d+\.\d+)['\"]", read_text(vf), re.MULTILINE)
            v = m.group(1) if m else ""
        elif t == "flutter":
            m = re.search(r"^version:\s*(\S+)", read_text(vf), re.MULTILINE)
            v = (m.group(1) if m else "").split("+")[0].strip('"').strip("'")
        elif t in ("react", "node"):
            v = str(read_json(vf).get("version", "") or "")
        elif t == "react-native":
            if cfg.version_file.endswith("Info.plist"):
                m = re.search(r"CFBundleShortVersionString</key>\s*<string>([^<]*)</string>", read_text(vf))
                v = m.group(1) if m else ""
            else:
                m = re.search(r'versionName\s*"([^"]+)"', read_text(vf))
                v = m.group(1) if m else ""
        elif t == "react-native-expo":
            v = str((read_json(vf).get("expo") or {}).get("version", "") or "")
        elif t == "python":
            m = re.search(r'^version\s*=\s*"(\d+\.\d+\.\d+)"', read_text(vf), re.MULTILINE)
            v = m.group(1) if m else ""
        else:
            v = cfg.current_version
    except (OSError, json.JSONDecodeError) as e:
        log_warning(f"프로젝트 파일 읽기 실패({vf}): {e}")
        v = ""

    if not v:
        v = cfg.current_version
    log_debug(f"프로젝트 파일 버전: '{v}'")
    return v


# ── 타입별 sync (.sh sync_for_type 등가) ─────────────────────────────
def sync_for_type(t: str, new_version: str):
    p = get_type_path(t)
    log_info(f"타입별 sync: {t} → {new_version} (경로: {p})")
    base = Path(p)

    if t == "spring":
        if base.is_dir():
            # find -maxdepth 2 -name build.gradle 등가
            candidates = sorted(set(base.glob("build.gradle")) | set(base.glob("*/build.gradle")))
            for gradle in candidates:
                changed = sub_file(gradle, r"version = '[^']*'", f"version = '{new_version}'")
                changed |= sub_file(gradle, r'version = "[^"]*"', f'version = "{new_version}"')
                if changed:
                    log_success(f"업데이트: {gradle.as_posix()}")
        else:
            log_warning(f"spring: {p} 디렉토리 없음 — 건너뜀")
    elif t == "flutter":
        pubspec = base / "pubspec.yaml"
        if pubspec.is_file():
            code = get_version_code()
            sub_file(pubspec, r"^version:.*$", f"version: {new_version}+{code}", count=1)
            log_success(f"업데이트: {pubspec.as_posix()}")
        else:
            log_warning(f"flutter: {p}/pubspec.yaml 없음 — 건너뜀")
    elif t in ("react", "node"):
        pkg = base / "package.json"
        if pkg.is_file():
            obj = read_json(pkg)
            obj["version"] = new_version
            write_json(pkg, obj)
            log_success(f"업데이트: {pkg.as_posix()}")
        else:
            log_warning(f"{t}: {p}/package.json 없음 — 건너뜀")
    elif t == "python":
        toml = base / "pyproject.toml"
        if toml.is_file():
            sub_file(toml, r'^version = "[^"]*"', f'version = "{new_version}"')
            log_success(f"업데이트: {toml.as_posix()}")
        else:
            log_warning(f"python: {p}/pyproject.toml 없음 — 건너뜀")
    elif t == "react-native":
        ios_dir = base / "ios"
        if ios_dir.is_dir():
            for plist in sorted(ios_dir.rglob("Info.plist")):
                if plist_set_version(plist, new_version):
                    log_success(f"업데이트: {plist.as_posix()}")
        else:
            log_warning(f"react-native: {p}/ios 디렉토리 없음 — 건너뜀")
        gradle = base / "android" / "app" / "build.gradle"
        if gradle.is_file():
            sub_file(gradle, r'versionName "[^"]*"', f'versionName "{new_version}"')
            log_success(f"업데이트: {gradle.as_posix()}")
        else:
            log_warning(f"react-native: {p}/android/app/build.gradle 없음 — 건너뜀")
    elif t == "react-native-expo":
        app_json = base / "app.json"
        if app_json.is_file():
            obj = read_json(app_json)
            obj.setdefault("expo", {})["version"] = new_version
            write_json(app_json, obj)
            log_success(f"업데이트: {app_json.as_posix()}")
        else:
            log_warning(f"react-native-expo: {p}/app.json 없음 — 건너뜀")
    elif t == "basic":
        pass
    else:
        log_warning(f"알 수 없는 타입: {t} — 건너뜀")


def sync_all_project_files(cfg: Config, new_version: str):
    if cfg.types:
        log_info(f"멀티타입 sync 시작: {','.join(cfg.types)}")
        for t in cfg.types:
            sync_for_type(t, new_version)
    else:
        # 배열이 없으면 basic 취급 (Config에서 이미 primary=basic) — 대상 파일 없음
        sync_for_type(cfg.primary, new_version)


# ── version.yml 갱신 (.sh update_version_yml 등가) ───────────────────
def update_version_yml(cfg: Config, new_version: str):
    from datetime import datetime, timezone

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    user = os.environ.get("GITHUB_ACTOR") or os.environ.get("USER") or os.environ.get("USERNAME") or "unknown"

    log_debug(f"version.yml 업데이트: {new_version}")
    set_yml_field(
        r"^version:\s*[\"']?[0-9][0-9.]*[\"']?(\s*#.*)?$",
        lambda m: f'version: "{new_version}"' + (m.group(1) or ""),
    )
    # metadata 필드는 존재할 때만 갱신 (.sh yq -e 가드 등가)
    set_yml_field(r"^(\s+last_updated:\s*).*$", lambda m: f'{m.group(1)}"{timestamp}"')
    set_yml_field(r"^(\s+last_updated_by:\s*).*$", lambda m: f'{m.group(1)}"{user}"')

    cfg.current_version = new_version
    log_success(f"version.yml 업데이트 완료: {new_version}")


# ── sync (.sh sync_versions 등가) ────────────────────────────────────
def sync_versions(cfg: Config) -> str:
    yml_version = cfg.current_version
    project_version = get_project_file_version(cfg)

    log_info("버전 동기화 검사")
    log_info(f"  version.yml: {yml_version}")
    log_info(f"  프로젝트 파일: {project_version}")

    if yml_version != project_version:
        if VERSION_RE.match(yml_version) and VERSION_RE.match(project_version):
            higher = higher_version(yml_version, project_version)
            log_info(f"버전 불일치 감지, 높은 버전으로 동기화: {higher}")
            if higher != yml_version:
                update_version_yml(cfg, higher)
            if higher != project_version:
                sync_all_project_files(cfg, higher)
            return higher
        log_warning("버전 형식 오류로 동기화 불가")
        return yml_version

    # primary는 일치 — 멀티타입이면 비-primary 파일 정합화
    if cfg.types:
        log_info(f"멀티타입 — 전 타입 파일을 version.yml 버전으로 정합화: {yml_version}")
        sync_all_project_files(cfg, yml_version)
    log_success(f"버전이 이미 동기화되어 있음: {yml_version}")
    return yml_version


def update_all_versions(cfg: Config, new_version: str):
    log_info(f"모든 버전 파일 업데이트: {new_version}")
    update_version_yml(cfg, new_version)
    sync_all_project_files(cfg, new_version)
    log_success(f"모든 버전 파일 업데이트 완료: {new_version}")


USAGE = """사용법: version_manager.py {get|get-code|increment|increment-code|set|sync|validate} [version]

Commands:
  get            - 현재 버전 가져오기 (동기화 포함)
  get-code       - 현재 VERSION_CODE 가져오기
  increment      - 버전 증가 + VERSION_CODE 증가
                   [--bump major|minor|patch] (기본 patch — 미지정 시 기존 동작)
  increment-code - VERSION_CODE만 증가
  set            - 특정 버전으로 설정
  sync           - 버전 파일 간 동기화
  validate       - 버전 형식 검증
"""


def parse_bump_flag(argv) -> str | None:
    """`increment --bump <level>` 파싱. 플래그가 없으면 'patch'(기존 동작), 값이 잘못되면 None.

    argparse를 쓰지 않는 이유: 이 CLI는 위치인자 기반 계약(`set 1.2.3` 등)을 그대로
    유지해야 하고, .sh shim이 인자를 그대로 통과시키므로 파싱을 단순하게 둔다.
    """
    if "--bump" not in argv:
        return "patch"
    idx = argv.index("--bump")
    if idx + 1 >= len(argv):
        return None
    value = argv[idx + 1]
    return value if value in ("major", "minor", "patch") else None


def main(argv):
    command = argv[1] if len(argv) > 1 else "get"

    if command not in ("get", "get-code", "increment", "increment-code", "set", "sync", "validate"):
        print(USAGE, file=sys.stderr)
        return 1

    cfg = Config()

    if command == "get":
        version = sync_versions(cfg)
        log_success(f"현재 버전: {version}")
        print(version)
    elif command == "get-code":
        code = get_version_code()
        log_success(f"현재 VERSION_CODE: {code}")
        print(code)
    elif command == "increment-code":
        print(increment_version_code())
    elif command == "increment":
        bump = parse_bump_flag(argv)
        if bump is None:
            log_error("--bump 값은 major|minor|patch 중 하나여야 합니다")
            return 1
        log_info("버전 동기화 확인")
        current = sync_versions(cfg)
        if not validate_version(current):
            return 1
        new_version = increment_version(current, bump)
        log_info(f"버전 업데이트({bump}): {current} → {new_version}")
        update_all_versions(cfg, new_version)
        increment_version_code()
        log_success(f"버전 업데이트 완료: {new_version}")
        print(new_version)
    elif command == "set":
        new_version = argv[2] if len(argv) > 2 else ""
        if not new_version:
            log_error("새 버전을 지정해주세요: version_manager.py set 1.2.3")
            return 1
        if not validate_version(new_version):
            return 1
        log_info(f"버전 설정: {new_version}")
        update_all_versions(cfg, new_version)
        log_success(f"버전 설정 완료: {new_version}")
        print(new_version)
    elif command == "sync":
        synced = sync_versions(cfg)
        log_success(f"버전 동기화 완료: {synced}")
        print(synced)
    elif command == "validate":
        version = argv[2] if len(argv) > 2 else cfg.current_version
        if not version:
            version = get_project_file_version(cfg)
        if validate_version(version):
            log_success(f"유효한 버전 형식: {version}")
            print(version)
            return 0
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    sys.exit(main(sys.argv))
