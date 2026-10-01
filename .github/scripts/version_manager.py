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

# macOS 기본 python3(3.9)에서도 `str | None` 주석이 평가되지 않고 기동되도록 한다 (#695)
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

# \Z: `$`는 끝 개행("1.2.3\n")을 허용하므로 쓰지 않는다. 앞자리 0(01.02.03)도 거부한다 (#685)
VERSION_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)\Z")
VERSION_YML = Path("version.yml")


class VersionError(Exception):
    """갱신·읽기 실패. 성공 로그 대신 오류 메시지와 exit 1로 끝내기 위해 쓴다 (#678)."""


# ── 로그 (stderr — .sh 이모지 동일) ─────────────────────────────────
def log_info(msg): print(f"ℹ️  {msg}", file=sys.stderr)
def log_success(msg): print(f"✅ {msg}", file=sys.stderr)
def log_error(msg): print(f"❌ {msg}", file=sys.stderr)
def log_warning(msg): print(f"⚠️  {msg}", file=sys.stderr)
def log_debug(msg):
    if os.environ.get("DEBUG") == "true":
        print(f"🔍 DEBUG: {msg}", file=sys.stderr)


# ── 파일 읽기/쓰기 (바이트 보존 — 줄바꿈·인코딩을 건드리지 않는다, #675 #682) ──
def read_text(path: Path) -> str:
    """줄바꿈 변환 없이 읽는다 (CRLF 그대로). BOM 문자도 그대로 남는다."""
    try:
        return path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError) as e:
        raise VersionError(f"{path.as_posix()}을(를) 읽지 못했습니다: {e}")


def write_text(path: Path, content: str) -> bool:
    """줄바꿈 변환 없이 쓴다. 내용이 이미 같으면 쓰지 않고 False (멱등 — mtime·diff 오염 방지)."""
    data = content.encode("utf-8")
    try:
        if path.is_file() and path.read_bytes() == data:
            return False
        path.write_bytes(data)
    except OSError as e:
        raise VersionError(f"{path.as_posix()}을(를) 쓰지 못했습니다: {e} (파일 권한을 확인하세요)")
    return True


def detect_eol(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def split_lines(text: str) -> list:
    """줄바꿈을 줄 끝에 붙인 채로 나눈다. ''.join(결과) == text 가 항상 성립한다."""
    return [p for p in re.split(r"(?<=\n)", text) if p != ""]


def split_eol(piece: str):
    """한 줄 조각을 (본문, 줄바꿈)으로 가른다."""
    if piece.endswith("\r\n"):
        return piece[:-2], "\r\n"
    if piece.endswith("\n"):
        return piece[:-1], "\n"
    return piece, ""


def yml_lines():
    # 줄바꿈과 첫 줄 BOM은 읽기에서만 제거 (쓸 때는 각 쓰기 함수가 보존)
    text = read_text(VERSION_YML)
    if text.startswith("\ufeff"):
        text = text[1:]
    return [split_eol(p)[0] for p in split_lines(text)]


def _unquote(value: str) -> str:
    """앞뒤 공백과 한 겹의 따옴표(" 또는 ')를 제거한다."""
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def parse_project_types() -> list:
    """project_types를 읽는다. 지원 형식: 인라인 ["a","b"] 와 블록 리스트(- a). 없으면 [].

    지원하지 않는 표기는 basic으로 조용히 대체하지 않고 오류로 알린다 (#684).
    """
    if not VERSION_YML.is_file():
        return []
    lines = yml_lines()
    for idx, line in enumerate(lines):
        if line.lstrip().startswith("#"):
            continue
        m = re.match(r"^project_types:[ \t]*(.*?)[ \t]*$", line)
        if not m:
            continue
        rest = m.group(1)
        if rest.startswith("["):
            inline = re.match(r"^\[([^\]]*)\][ \t]*(#.*)?$", rest)
            if not inline:
                raise VersionError("version.yml의 project_types는 한 줄 배열([\"a\", \"b\"]) 또는 블록 리스트(- a)만 지원합니다.")
            return [_unquote(t) for t in inline.group(1).split(",") if t.strip()]
        if rest and not rest.startswith("#"):
            raise VersionError(f"version.yml의 project_types 형식은 지원하지 않는 표기입니다: '{rest}' (배열 또는 블록 리스트로 쓰세요)")
        # 값이 비어 있으면 다음 줄들의 블록 리스트를 읽는다
        types = []
        for nxt in lines[idx + 1:]:
            if not nxt.strip() or nxt.lstrip().startswith("#"):
                continue
            item = re.match(r"^\s*-[ \t]+(.*?)[ \t]*$", nxt)
            if not item:
                break
            raw = item.group(1)
            # 따옴표 값 뒤의 줄 끝 주석("node"  # 설명)과 무따옴표 값 뒤 주석을 모두 제거
            qm = re.match(r"^(\"[^\"]*\"|'[^']*')[ \t]*(#.*)?$", raw)
            types.append(_unquote(qm.group(1)) if qm else re.sub(r"[ \t]+#.*$", "", raw).strip())
        return [t for t in types if t]
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
    """project_paths.<type> — 키 없으면 '.' (legacy: 루트 기준). 값은 "큰따옴표"·'작은따옴표'·무따옴표 모두 허용."""
    in_paths = False
    for line in yml_lines():
        if line.lstrip().startswith("#") or not line.strip():
            continue
        pm = re.match(r"^project_paths:[ \t]*(.*?)[ \t]*$", line)
        if pm:
            rest = pm.group(1)
            if rest and not rest.startswith("#"):
                raise VersionError(f"version.yml의 project_paths 형식은 지원하지 않는 표기입니다: '{rest}' (블록 맵 '타입: 경로'로 쓰세요)")
            in_paths = True
            continue
        if in_paths:
            if re.match(r"^\S", line):
                break
            m = re.match(r"^\s+([A-Za-z0-9_-]+):[ \t]*(\"[^\"]*\"|'[^']*'|[^#\s]*)[ \t]*(#.*)?$", line)
            if not m:
                raise VersionError(f"version.yml의 project_paths 항목을 읽지 못했습니다: '{line.strip()}' (타입: 경로 형식으로 쓰세요)")
            if m.group(1) == t:
                return _unquote(m.group(2)) or "."
    return "."


def get_yml_version():
    """version: 값을 읽는다. v 접두사는 허용(정규화), 읽지 못하면 None (0.0.0으로 대체하지 않는다 — #678)."""
    for line in yml_lines():
        if line.lstrip().startswith("#"):
            continue
        m = re.match(r"^version:\s*[\"']?[vV]?([0-9][0-9.]*)", line)
        if m:
            return m.group(1)
    return None


def set_yml_field(pattern: str, new_line_fn):
    """pattern에 걸리는 첫 라인을 new_line_fn(match)로 교체. 매칭 여부 반환. 줄바꿈·BOM은 보존."""
    text = read_text(VERSION_YML)
    # 첫 줄 BOM은 매칭에서만 빼고 그대로 되돌려 쓴다
    bom = "\ufeff" if text.startswith("\ufeff") else ""
    pieces = split_lines(text[len(bom):])
    for i, piece in enumerate(pieces):
        body, eol = split_eol(piece)
        if body.lstrip().startswith("#"):
            continue
        m = re.match(pattern, body)
        if m:
            pieces[i] = new_line_fn(m) + eol
            write_text(VERSION_YML, bom + "".join(pieces))
            return True
    return False


# ── 설정 읽기 (.sh read_version_config 등가, v4.1.0 SSOT) ───────────
class Config:
    def __init__(self, require_version=True):
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

        current = get_yml_version()
        if current is None:
            if require_version:
                log_error('version.yml에서 version 값을 읽지 못했습니다. `version: "x.y.z"` 줄이 있어야 합니다.')
                sys.exit(1)
            current = "0.0.0"  # version_code만 다루는 명령에서는 쓰이지 않는 자리표시값
        self.current_version = current
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
            # Kotlin DSL(build.gradle.kts)만 있는 프로젝트도 읽는다 (#680)
            if not Path(f"{p}/build.gradle").is_file() and Path(f"{p}/build.gradle.kts").is_file():
                return f"{p}/build.gradle.kts"
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
    text = read_text(VERSION_YML)
    bom = "\ufeff" if text.startswith("\ufeff") else ""
    body_text = text[len(bom):]
    eol = detect_eol(body_text)
    new_line = "version_code: 1 # app build number" + eol
    pieces = split_lines(body_text)
    for i, piece in enumerate(pieces):
        if not piece.lstrip().startswith("#") and re.match(r"^version:", piece):
            if not piece.endswith("\n"):  # 마지막 줄에 개행이 없으면 앞 줄에 붙지 않게 먼저 개행
                pieces[i] = piece + eol
            pieces.insert(i + 1, new_line)
            break
    else:
        if pieces and not pieces[-1].endswith("\n"):
            pieces[-1] += eol
        pieces.append(new_line)
    write_text(VERSION_YML, bom + "".join(pieces))
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
    """JSON 객체를 읽는다. BOM은 허용하고, 깨진 JSON·객체가 아닌 최상위는 VersionError로 알린다 (#683)."""
    text = read_text(path)
    try:
        obj = json.loads(text.lstrip("\ufeff"))
    except ValueError as e:
        raise VersionError(f"{path.as_posix()}을(를) 읽지 못했습니다: {e} (JSON 문법·머지 충돌 마커를 확인하세요)")
    if not isinstance(obj, dict):
        raise VersionError(f"{path.as_posix()}을(를) 읽지 못했습니다: 최상위가 JSON 객체가 아닙니다")
    return obj


# JSON은 json.dumps로 다시 쓰지 않고 version 값의 문자열 구간만 교체한다.
# 다시 쓰면 탭·4칸 들여쓰기, 한 줄 배열, 끝 개행 유무, CRLF가 모두 바뀐다 (#682).
def _json_ws(t: str, i: int) -> int:
    while i < len(t) and t[i] in " \t\r\n":
        i += 1
    return i


def _json_string_end(t: str, i: int) -> int:
    i += 1
    while t[i] != '"':
        i += 2 if t[i] == "\\" else 1
    return i + 1


def _json_value_end(t: str, i: int) -> int:
    """i에서 시작하는 값의 끝 위치. 이미 json.loads로 검증된 텍스트에만 쓴다."""
    i = _json_ws(t, i)
    c = t[i]
    if c == '"':
        return _json_string_end(t, i)
    if c in "{[":
        close = "}" if c == "{" else "]"
        i += 1
        while True:
            i = _json_ws(t, i)
            if t[i] == close:
                return i + 1
            if t[i] == ",":
                i += 1
                continue
            if c == "{":
                i = _json_ws(t, _json_string_end(t, i)) + 1  # 키와 콜론 건너뜀
            i = _json_value_end(t, i)
    j = i
    while j < len(t) and t[j] not in ",}] \t\r\n":
        j += 1
    return j


def _json_member_span(t: str, obj_start: int, key: str):
    """obj_start의 객체에서 key 값의 (시작, 끝). 중복 키는 json.loads처럼 마지막 것을 쓴다."""
    i = _json_ws(t, obj_start) + 1
    found = None
    while True:
        i = _json_ws(t, i)
        if t[i] == "}":
            return found
        if t[i] == ",":
            i += 1
            continue
        key_end = _json_string_end(t, i)
        name = json.loads(t[i:key_end])
        i = _json_ws(t, key_end) + 1
        vs = _json_ws(t, i)
        ve = _json_value_end(t, vs)
        if name == key:
            found = (vs, ve)
        i = ve


def json_set_string(text: str, keys: list, new_value: str):
    """keys 경로의 문자열 값을 바꾼 새 텍스트. 경로가 없거나 문자열이 아니면 None."""
    vs = _json_ws(text, 1 if text.startswith("\ufeff") else 0)
    ve = vs
    for key in keys:
        if text[vs] != "{":
            return None
        span = _json_member_span(text, vs, key)
        if span is None:
            return None
        vs, ve = span
    if text[vs] != '"':
        return None
    return text[:vs] + json.dumps(new_value, ensure_ascii=False) + text[ve:]


def json_rebuild(text: str, obj) -> str:
    """키를 새로 넣어야 할 때만 쓰는 대체 경로. 원본의 들여쓰기·줄바꿈·끝 개행·BOM을 최대한 따른다."""
    bom = "\ufeff" if text.startswith("\ufeff") else ""
    body = text[len(bom):]
    indents = re.findall(r"^([ \t]+)\S", body, re.MULTILINE)
    indent = min(indents, key=len) if indents else "  "
    eol = detect_eol(body)
    out = json.dumps(obj, indent=indent, ensure_ascii=False)
    if eol != "\n":
        out = out.replace("\n", eol)
    if body.endswith("\n"):
        out += eol
    return bom + out


def set_json_version(path: Path, keys: list, new_version: str) -> bool:
    """JSON 파일의 keys 경로(예: ["version"], ["expo", "version"])를 new_version으로 바꾼다. 변경 여부 반환."""
    obj = read_json(path)  # 깨진 JSON은 여기서 오류로 끝낸다 (이후 스캔은 유효한 JSON을 전제)
    text = read_text(path)
    new_text = json_set_string(text, keys, new_version)
    if new_text is None:
        node = obj
        for key in keys[:-1]:
            node = node.setdefault(key, {})
            if not isinstance(node, dict):
                raise VersionError(f"{path.as_posix()}의 '{key}'가 객체가 아니라 version을 쓸 수 없습니다")
        node[keys[-1]] = new_version
        new_text = json_rebuild(text, obj)
    return write_text(path, new_text)


SAME, CHANGED, NO_MATCH = "same", "changed", "nomatch"


def sub_file(path: Path, pattern: str, repl, count=0, flags=re.MULTILINE) -> str:
    """정규식 치환. CHANGED(바뀜) / SAME(매치했지만 이미 같음, 쓰지 않음) / NO_MATCH 반환."""
    text = read_text(path)
    new_text, n = re.subn(pattern, repl, text, count=count, flags=flags)
    if not n:
        return NO_MATCH
    return CHANGED if write_text(path, new_text) else SAME


def plist_set_version(path: Path, new_version: str) -> str:
    """CFBundleShortVersionString 키 뒤 <string> 값을 교체 (키와 값이 같은 줄이든 다음 줄이든)."""
    return sub_file(
        path,
        r"(<key>CFBundleShortVersionString</key>\s*<string>)[^<]*(</string>)",
        lambda m: f"{m.group(1)}{new_version}{m.group(2)}",
        flags=0,
    )


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
    except (OSError, ValueError, VersionError) as e:
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
            candidates = sorted(
                set(base.glob("build.gradle")) | set(base.glob("*/build.gradle"))
                | set(base.glob("build.gradle.kts")) | set(base.glob("*/build.gradle.kts"))
            )
            if not candidates:
                log_warning(f"spring: {p}에 build.gradle(.kts) 없음 — 건너뜀")
            for gradle in candidates:
                # 줄 시작의 `version = '...'`(프로젝트 버전 대입)만 고친다. 앵커가 없으면
                # ext.kotlin_version = '1.9.0' 같은 다른 대입이나 주석까지 덮어써 빌드가 깨진다 (#680).
                results = {
                    sub_file(gradle, r"^([ \t]*version[ \t]*=[ \t]*)'[^']*'", lambda m: f"{m.group(1)}'{new_version}'"),
                    sub_file(gradle, r'^([ \t]*version[ \t]*=[ \t]*)"[^"]*"', lambda m: f'{m.group(1)}"{new_version}"'),
                }
                if CHANGED in results:
                    log_success(f"업데이트: {gradle.as_posix()}")
                elif results == {NO_MATCH}:
                    log_warning(f"spring: {gradle.as_posix()}에서 version 대입을 찾지 못했습니다 — 동기화하지 못함")
        else:
            log_warning(f"spring: {p} 디렉토리 없음 — 건너뜀")
    elif t == "flutter":
        pubspec = base / "pubspec.yaml"
        if pubspec.is_file():
            code = get_version_code()
            # 값만 교체하고 줄 끝 주석(version: 1.2.3+7 # rel)은 보존한다
            status = sub_file(
                pubspec, r"^(version:[ \t]*)[^\s#]*([ \t]*#[^\r\n]*)?",
                lambda m: f"{m.group(1)}{new_version}+{code}{m.group(2) or ''}", count=1)
            if status == CHANGED:
                log_success(f"업데이트: {pubspec.as_posix()}")
        else:
            log_warning(f"flutter: {p}/pubspec.yaml 없음 — 건너뜀")
    elif t in ("react", "node"):
        pkg = base / "package.json"
        if pkg.is_file():
            if set_json_version(pkg, ["version"], new_version):
                log_success(f"업데이트: {pkg.as_posix()}")
        else:
            log_warning(f"{t}: {p}/package.json 없음 — 건너뜀")
    elif t == "python":
        toml = base / "pyproject.toml"
        if toml.is_file():
            if sub_file(toml, r'^version = "[^"]*"', f'version = "{new_version}"') == CHANGED:
                log_success(f"업데이트: {toml.as_posix()}")
        else:
            log_warning(f"python: {p}/pyproject.toml 없음 — 건너뜀")
    elif t == "react-native":
        ios_dir = base / "ios"
        if ios_dir.is_dir():
            for plist in sorted(ios_dir.rglob("Info.plist")):
                if plist_set_version(plist, new_version) == CHANGED:
                    log_success(f"업데이트: {plist.as_posix()}")
        else:
            log_warning(f"react-native: {p}/ios 디렉토리 없음 — 건너뜀")
        gradle = base / "android" / "app" / "build.gradle"
        if gradle.is_file():
            if sub_file(gradle, r'versionName "[^"]*"', f'versionName "{new_version}"') == CHANGED:
                log_success(f"업데이트: {gradle.as_posix()}")
        else:
            log_warning(f"react-native: {p}/android/app/build.gradle 없음 — 건너뜀")
    elif t == "react-native-expo":
        app_json = base / "app.json"
        if app_json.is_file():
            if set_json_version(app_json, ["expo", "version"], new_version):
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

    if get_yml_version() == new_version:
        # 이미 같은 버전이면 타임스탬프까지 포함해 파일을 건드리지 않는다 (멱등)
        log_info(f"version.yml은 이미 {new_version} — 변경 없음")
        cfg.current_version = new_version
        return
    log_debug(f"version.yml 업데이트: {new_version}")
    # 값은 따옴표 유무·v 접두사·프리릴리스 접미사 무엇이든 통째로 교체하고 줄 끝 주석만 보존한다.
    replaced = set_yml_field(
        r"^version:[ \t]*(?:\"[^\"]*\"|'[^']*'|[^#\s]*)([ \t]*#.*)?[ \t]*$",
        lambda m: f'version: "{new_version}"' + (m.group(1) or ""),
    )
    if not replaced:
        # 성공 로그와 새 버전을 내보내면 릴리스는 새 번호로 나가는데 version.yml은 그대로 남는다
        raise VersionError("version.yml의 version 줄을 갱신하지 못했습니다. `version: \"x.y.z\"` 형식으로 고친 뒤 다시 실행하세요.")
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


def preflight_json_files(cfg: Config):
    """JSON 버전 파일을 쓰기 전에 먼저 읽어 본다. 일부만 갱신된 채 중단되는 것을 막는다 (#683)."""
    for t in (cfg.types or [cfg.primary]):
        name = {"react": "package.json", "node": "package.json", "react-native-expo": "app.json"}.get(t)
        if not name:
            continue
        f = Path(get_type_path(t)) / name
        if f.is_file():
            read_json(f)


def update_all_versions(cfg: Config, new_version: str):
    log_info(f"모든 버전 파일 업데이트: {new_version}")
    preflight_json_files(cfg)
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
    try:
        return _main(argv)
    except VersionError as e:
        log_error(str(e))
        return 1


def _main(argv):
    command = argv[1] if len(argv) > 1 else "get"

    if command not in ("get", "get-code", "increment", "increment-code", "set", "sync", "validate"):
        print(USAGE, file=sys.stderr)
        return 1

    # version_code만 다루는 명령은 version 키가 없어도 동작해야 한다 (기존 계약)
    # validate는 인자로 버전을 직접 주면 version.yml의 version 값 없이도 검증할 수 있다
    needs_yml_version = command not in ("get-code", "increment-code") and not (command == "validate" and len(argv) > 2)
    cfg = Config(require_version=needs_yml_version)

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
