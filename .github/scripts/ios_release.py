#!/usr/bin/env python3
"""
ios_release.py

iOS 테스트 빌드와 릴리스의 버전 판단과 Apple 업로드 오류 해석 (이슈 #643).
Apple 오류 해석의 유일한 위치다. 새 오류 코드는 여기 패턴과 test_ios_release.py의
실제 문구 샘플을 함께 추가한다.

버전 닫힘 규칙: 앱 버전(train)은 승인되는 순간 닫히고, 이후 개발자 반려로도 다시 열리지 않는다.
닫힌 버전으로 올리면 12~18분 빌드 뒤 업로드에서 거부되므로, 테스트 빌드는 빌드 전에
다음 패치 버전으로 바꾸고 릴리스는 즉시 실패시킨다.

  - 커맨드: precheck-version | classify-error | archive-upload
  - 출력: 언제나 JSON (ok / 데이터 / summary / next), 로그와 ::error:: 는 stderr
  - ASC 조회가 안 되는 환경(시크릿 누락, 권한 부족)은 version.yml 버전으로 진행한다

사용 예:
  python3 ios_release.py precheck-version --mode test --version 2.1.2 --bundle-id com.a.b
  python3 ios_release.py classify-error --log build/upload_attempt_1.log
"""

from __future__ import annotations

import argparse
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from xml.parsers.expat import ExpatError

sys.path.insert(0, str(Path(__file__).resolve().parent))
import asc_client  # noqa: E402
import build_number  # noqa: E402

# 대기는 모듈 수준으로 두어 테스트에서 0초로 바꾼다
sleep = time.sleep

# 승인 이후 상태. DEVELOPER_REJECTED는 승인 전 철회와 승인 후 반려를 구분할 수 없어 열림으로 본다.
CLOSED_VERSION_STATES = {
    "ACCEPTED", "PENDING_DEVELOPER_RELEASE", "PENDING_APPLE_RELEASE",
    "PROCESSING_FOR_DISTRIBUTION", "READY_FOR_DISTRIBUTION", "REPLACED_WITH_NEW_VERSION",
}
# 구형 appStoreState 값. 신형과 같은 의미에 판매 관련 상태가 더해진다.
CLOSED_STORE_STATES = CLOSED_VERSION_STATES | {
    "READY_FOR_SALE", "PROCESSING_FOR_APP_STORE", "PREORDER_READY_FOR_SALE",
    "DEVELOPER_REMOVED_FROM_SALE", "REMOVED_FROM_SALE",
}

_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_NO_REASON = "업로드 실패 (사유를 로그에서 찾지 못함)"


# ── 버전 ──────────────────────────────────────────────────────────────
def parse_version(s: str | None) -> tuple[int, int, int] | None:
    """정수 1~3개를 점으로 이은 문자열만 인정한다. 부족한 자리는 0, 그 외는 None."""
    if not s:
        return None
    parts = str(s).strip().split(".")
    if not 1 <= len(parts) <= 3 or not all(p.isdigit() for p in parts):
        return None
    nums = [int(p) for p in parts] + [0] * (3 - len(parts))
    return nums[0], nums[1], nums[2]


def format_version(t: tuple[int, int, int]) -> str:
    return f"{t[0]}.{t[1]}.{t[2]}"


def next_patch(s: str) -> str:
    """다음 패치 버전. 파싱할 수 없는 문자열이면 ValueError."""
    t = parse_version(s)
    if t is None:
        raise ValueError(f"버전 형식을 해석할 수 없습니다: {s!r}")
    return format_version((t[0], t[1], t[2] + 1))


def closed_max(versions: list[dict]) -> str | None:
    """닫힌 버전 중 최대. 신형과 구형 상태 필드를 모두 보고, 파싱할 수 없는 버전은 제외한다."""
    best: tuple[int, int, int] | None = None
    for v in versions:
        closed = (v.get("appVersionState") in CLOSED_VERSION_STATES
                  or v.get("appStoreState") in CLOSED_STORE_STATES)
        t = parse_version(v.get("version")) if closed else None
        if t is not None and (best is None or t > best):
            best = t
    return format_version(best) if best else None


def decide_version(current: str, closed: str | None, mode: str) -> dict:
    """사용할 버전 결정. 릴리스는 닫힌 버전이면 바꾸지 않고 실패(ok False)로 알린다."""
    cur_t, closed_t = parse_version(current), parse_version(closed)
    base = {"ok": True, "version": current, "changed": False, "closed_max": closed}
    if closed_t is None:
        return {**base, "reason": "출시되어 닫힌 버전 없음"}
    if cur_t is None:
        # 판단할 수 없는 버전 문자열은 손대지 않는다 (사후 복구가 받쳐준다)
        return {**base, "reason": f"현재 버전 {current!r}을 해석할 수 없어 그대로 진행"}
    if cur_t > closed_t:
        return {**base, "reason": f"{current}는 열려 있음 (출시 최대 {closed})"}
    if mode == "release":
        return {**base, "ok": False,
                "reason": f"{current}는 이미 출시되어 닫힌 버전입니다. version.yml 버전을 올리세요"}
    nxt = next_patch(closed)
    # 숫자 뒤 조사(는/은, 로/으로)는 받침에 따라 달라지므로 조사 없는 문구로 쓴다
    why = (f"{current} 출시되어 닫힘" if cur_t == closed_t
           else f"{current}이(가) 출시된 {closed}보다 낮음")
    return {"ok": True, "version": nxt, "changed": True, "closed_max": closed,
            "reason": f"{why}, 빌드 버전 {nxt}"}


# ── 업로드 오류 분류 ──────────────────────────────────────────────────
def _code(n: str) -> str:
    """오류 코드가 더 긴 숫자의 일부로 오인되지 않게 경계를 둔다."""
    return rf"(?<!\d){n}(?!\d)"


_TRAIN_VERSION = re.compile(r"train version '(?P<v>[\d.]+)' is closed", re.I)
_APPROVED_VERSION = re.compile(r"previously approved version \[(?P<v>[\d.]+)\]", re.I)
_TOO_LOW_NUMBERS = [
    re.compile(r"must (?:contain a )?higher version than that of the previously uploaded version \[(?P<n>\d+)", re.I),
    re.compile(r"bundle version must be higher than the previously uploaded version: '(?P<n>\d+)'", re.I),
]

# 종류별 패턴. 앞에 있는 종류가 우선한다 (train_closed > too_low > duplicate)
_KIND_PATTERNS: list[tuple[str, list[re.Pattern]]] = [
    ("train_closed", [re.compile(_code("90186")), _TRAIN_VERSION,
                      re.compile(_code("90062")), _APPROVED_VERSION,
                      re.compile(_code("90478")), re.compile(r"later version has been closed", re.I)]),
    ("too_low", [re.compile(_code("90061")), *_TOO_LOW_NUMBERS]),
    ("duplicate", [re.compile(_code("90189")), re.compile(r"Redundant Binary Upload", re.I),
                   re.compile(r"INVALID\.DUPLICATE"), re.compile(r"(?<!\d)-19232(?!\d)")]),
]
_FALLBACK_LINE = re.compile(r"ITMS-\d+|ERROR|error|실패|\[!\]")


def _first_group(patterns: list[re.Pattern], text: str, group: str) -> str | None:
    for p in patterns:
        m = p.search(text)
        if m and m.groupdict().get(group):
            return m.group(group)
    return None


def _clean_line(line: str) -> str:
    return line.strip()[:300]


def classify_upload_error(log: str) -> dict:
    """fastlane 업로드 로그를 분류한다. 색상 코드는 먼저 걷어낸다."""
    text = _ANSI.sub("", log or "")
    kind, hit_patterns = "other", []
    for k, pats in _KIND_PATTERNS:
        matched = [p for p in pats if p.search(text)]
        if matched:
            kind, hit_patterns = k, matched
            break

    required = closed_version = None
    if kind == "train_closed":
        closed_version = _first_group([_TRAIN_VERSION, _APPROVED_VERSION], text, "v")
    elif kind == "too_low":
        n = _first_group(_TOO_LOW_NUMBERS, text, "n")
        required = int(n) if n else None

    reason = ""
    lines = text.splitlines()
    if hit_patterns:
        reason = next((_clean_line(l) for l in lines if any(p.search(l) for p in hit_patterns)), "")
    else:
        hits = [l for l in lines if _FALLBACK_LINE.search(l)]
        reason = _clean_line(hits[-1]) if hits else ""
    return {"kind": kind, "required_build": required, "closed_version": closed_version,
            "reason_line": reason or _NO_REASON}


# ── CLI ───────────────────────────────────────────────────────────────
def _write_github_output(pairs: dict) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as f:
        for k, v in pairs.items():
            # 값에 개행이 있으면 GITHUB_OUTPUT 형식이 깨져 뒤 줄이 다른 키로 해석된다
            f.write(f"{k}={_one_line(v)}\n")


def _emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False))


def _precheck_fallback(version: str, why: str) -> int:
    reason = f"ASC 조회 불가: {why} (version.yml 버전으로 진행)"
    print(f"경고: {reason}", file=sys.stderr)
    _write_github_output({"version": version, "changed": "false", "reason": reason})
    _emit({"ok": True, "version": version, "changed": False, "closed_max": None,
           "reason": reason, "fallback": True, "summary": reason, "next": None})
    return 0


def cmd_precheck(args: argparse.Namespace) -> int:
    token = asc_client.token_from_env()
    if not token:
        return _precheck_fallback(args.version, "ASC 인증 정보 없음")
    try:
        app_id = asc_client.find_app_id(args.bundle_id, token)
        if not app_id:
            return _precheck_fallback(args.version, f"번들 ID {args.bundle_id} 앱을 찾지 못함")
        closed = closed_max(asc_client.list_app_store_versions(app_id, token))
    except asc_client.AscError as e:
        return _precheck_fallback(args.version, str(e))

    d = decide_version(args.version, closed, args.mode)
    _write_github_output({"version": d["version"], "changed": str(d["changed"]).lower(), "reason": d["reason"]})
    _emit({**d, "fallback": False, "summary": d["reason"],
           "next": None if d["ok"] else "version.yml 버전을 올린 뒤 다시 실행"})
    if not d["ok"]:
        print(f"::error::{d['reason']}", file=sys.stderr)
        return 1
    return 0


def cmd_classify(args: argparse.Namespace) -> int:
    try:
        log = Path(args.log).read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        print(f"경고: 로그를 읽지 못했습니다: {e}", file=sys.stderr)
        log = ""
    r = classify_upload_error(log)
    _emit({"ok": True, **r, "summary": f"{r['kind']}: {r['reason_line']}", "next": None})
    return 0


# ── archive-upload ────────────────────────────────────────────────────
STATE_NAME = "ios_release_state.json"
_REEXIST_CHECKS = 3
_REEXIST_INTERVAL = 20
# 본체 앱과 그 안에 중첩된 확장/워치/App Clip 번들의 Info.plist
_BUNDLE_PLIST = re.compile(
    r"^Payload/[^/]+\.app(?:/(?:PlugIns|Watch|AppClips)/[^/]+\.(?:appex|app))*/Info\.plist$")
_SECRET_ENV = re.compile(r"KEY|TOKEN|SECRET|PASSWORD", re.I)


class _Fail(Exception):
    """archive-upload 실패. 메시지가 그대로 reason_line이 된다."""


def _one_line(v) -> str:
    """개행과 색상 코드를 걷어 한 줄로 만든다."""
    return " ".join(_ANSI.sub("", str(v)).split())


def _scrub(text: str) -> str:
    """환경변수에 들어 있는 비밀값이 로그나 사유에 섞여 나가지 않게 가린다."""
    for k, v in os.environ.items():
        if _SECRET_ENV.search(k) and len(v) >= 8:
            text = text.replace(v, "***")
    return text


def _reason(text: str) -> str:
    return _scrub(_one_line(text))[:300]


def run_cmd(cmd: list[str], cwd: str, env: dict) -> tuple[int, str]:
    """명령을 실행하며 출력을 stderr로 실시간 흘리고, 합친 출력을 돌려준다.
    stdout은 JSON 한 줄 전용이라 자식 출력은 절대 stdout으로 보내지 않는다."""
    try:
        proc = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace", bufsize=1)
    except OSError as e:
        return 127, f"실행 실패: {cmd[0]}: {e}"
    lines: list[str] = []
    assert proc.stdout is not None
    for line in proc.stdout:
        sys.stderr.write(line)
        sys.stderr.flush()
        lines.append(line)
    return proc.wait(), "".join(lines)


def write_runtime_export_options(src: Path, dst: Path) -> Path:
    """원본은 건드리지 않고 사본에만 번호 자동 관리를 끈다 (Xcode가 export 중 번호를 바꾸지 못하게)."""
    with open(src, "rb") as f:
        data = plistlib.load(f)
    data["manageAppVersionAndBuildNumber"] = False
    dst.parent.mkdir(parents=True, exist_ok=True)
    with open(dst, "wb") as f:
        plistlib.dump(data, f)
    return dst


def verify_ipa(ipa: Path, version: str, build: int) -> list[str]:
    """IPA 안 모든 앱/확장 번들의 버전과 빌드 번호가 기대값과 같은지 본다. 비면 통과."""
    problems: list[str] = []
    try:
        zf = zipfile.ZipFile(ipa)
    except (OSError, zipfile.BadZipFile) as e:
        return [f"{ipa.name}: IPA를 열 수 없습니다 ({e})"]
    with zf:
        names = [n for n in zf.namelist() if _BUNDLE_PLIST.match(n)]
        if not any(n.count("/") == 2 for n in names):  # Payload/X.app/Info.plist
            return ["Payload/*.app/Info.plist를 IPA에서 찾지 못했습니다"]
        for n in sorted(names):
            rel = n[len("Payload/"):-len("/Info.plist")]
            try:
                info = plistlib.loads(zf.read(n))
            except (ExpatError, plistlib.InvalidFileException, ValueError, KeyError) as e:
                problems.append(f"{rel}: Info.plist를 읽을 수 없습니다 ({e})")
                continue
            got_b, got_v = info.get("CFBundleVersion"), info.get("CFBundleShortVersionString")
            if str(got_b) != str(build) or str(got_v) != str(version):
                problems.append(f"{rel}: CFBundleVersion={got_b} (기대 {build}), "
                                f"CFBundleShortVersionString={got_v} (기대 {version})")
    return problems


def _last_error_line(out: str) -> str:
    """실패 사유로 보일 한 줄. 진짜 원인은 `error: ...` 줄이고 마지막의 `** ARCHIVE FAILED **`
    배너는 원인이 아니라 결과라, 배너는 error 줄이 없을 때만 쓴다 (E2E에서 배너만 보이던 결함)."""
    lines = [l for l in _ANSI.sub("", out or "").splitlines() if l.strip()]
    errors = [l for l in lines if "error:" in l]
    if errors:
        # 앞의 파일 경로는 떼고 원인 문장만 남긴다
        return _clean_line(errors[-1].split("error:", 1)[1])
    hits = [l for l in lines if re.search(r"\*\* .* FAILED|실행 실패", l)]
    return _clean_line((hits or lines or ["출력 없음"])[-1])


def _int_env(name: str, default: int | None) -> int | None:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        print(f"경고: {name}={raw!r}은 정수가 아니어서 무시합니다", file=sys.stderr)
        return default


class _Cfg:
    """환경변수 입력. 빈 문자열은 없음으로 취급한다 (Actions는 없는 시크릿을 빈 값으로 넣는다)."""

    def __init__(self) -> None:
        e = os.environ
        self.app_root = Path(e.get("APP_ROOT", "").strip() or ".")
        self.workspace = e.get("IOS_WORKSPACE", "").strip() or "Runner.xcworkspace"
        self.scheme = e.get("IOS_SCHEME", "").strip() or "Runner"
        self.version = e.get("VERSION", "").strip()
        self.mode = e.get("MODE", "").strip()
        self.app_identifier = e.get("APP_IDENTIFIER", "").strip()
        self.profile = e.get("IOS_PROVISIONING_PROFILE_NAME", "")
        self.floor = _int_env("BUILD_NUMBER_FLOOR", None)
        self.max_attempts = max(1, _int_env("MAX_ATTEMPTS", 5) or 5)
        self.ios_dir = self.app_root / "ios"
        self.state_path = self.ios_dir / "build" / STATE_NAME

    def validate(self) -> None:
        if not self.version:
            raise _Fail("VERSION 환경변수가 필요합니다")
        if self.mode not in ("test", "release"):
            raise _Fail("MODE는 test 또는 release여야 합니다")


def _asc_context(cfg: _Cfg) -> tuple[str, str]:
    """(토큰, 앱 ID). 하나라도 못 구하면 _Fail이 아니라 AscError로 알린다."""
    token = asc_client.token_from_env()
    if not token:
        raise asc_client.AscError("ASC 인증 정보 없음")
    if not cfg.app_identifier:
        raise asc_client.AscError("APP_IDENTIFIER 없음")
    app_id = asc_client.find_app_id(cfg.app_identifier, token)
    if not app_id:
        raise asc_client.AscError(f"번들 ID {cfg.app_identifier} 앱을 찾지 못함")
    return token, app_id


def _asc_floor(cfg: _Cfg) -> int | None:
    """ASC 최근 빌드 번호 + 1. 조회가 안 되면 하한 없이 진행한다."""
    try:
        token, app_id = _asc_context(cfg)
        latest = asc_client.recent_max_build(app_id, token)
    except asc_client.AscError as e:
        print(f"경고: ASC 최근 번호 조회 불가, 시각 번호로 진행합니다: {e}", file=sys.stderr)
        return None
    return latest + 1 if latest else None


def _archive_and_export(cfg: _Cfg, version: str, number: int) -> Path:
    """아카이브, 런타임 ExportOptions로 export, IPA 번호 검증. 통과한 IPA 경로를 돌려준다."""
    env = dict(os.environ)
    ios = str(cfg.ios_dir)
    build_dir = cfg.ios_dir / "build"
    # 재시도 시 이전 산출물이 섞이지 않게 비운다
    shutil.rmtree(build_dir / "Runner.xcarchive", ignore_errors=True)
    shutil.rmtree(build_dir / "ipa", ignore_errors=True)

    rc, out = run_cmd([
        "xcodebuild", "-workspace", cfg.workspace, "-scheme", cfg.scheme,
        "-archivePath", "build/Runner.xcarchive", "-destination", "generic/platform=iOS", "archive",
        "CODE_SIGN_STYLE=Manual", f"PROVISIONING_PROFILE_SPECIFIER={cfg.profile}",
        "CODE_SIGN_IDENTITY=Apple Distribution",
        # 확장 타깃이 어느 변수를 쓰든 맞도록 네 개를 함께 넘긴다
        f"FLUTTER_BUILD_NUMBER={number}", f"CURRENT_PROJECT_VERSION={number}",
        f"FLUTTER_BUILD_NAME={version}", f"MARKETING_VERSION={version}",
    ], ios, env)
    if rc != 0:
        raise _Fail(_reason(f"xcodebuild archive 실패 (종료 코드 {rc}): {_last_error_line(out)}"))

    try:
        write_runtime_export_options(cfg.ios_dir / "ExportOptions.plist", build_dir / "ExportOptions.runtime.plist")
    except (OSError, plistlib.InvalidFileException, ExpatError, ValueError) as e:
        raise _Fail(_reason(f"ios/ExportOptions.plist를 읽지 못했습니다: {e}"))
    rc, out = run_cmd([
        "xcodebuild", "-exportArchive", "-archivePath", "build/Runner.xcarchive",
        "-exportPath", "build/ipa", "-exportOptionsPlist", "build/ExportOptions.runtime.plist",
    ], ios, env)
    if rc != 0:
        raise _Fail(_reason(f"xcodebuild -exportArchive 실패 (종료 코드 {rc}): {_last_error_line(out)}"))

    ipas = sorted((build_dir / "ipa").glob("*.ipa"))
    if not ipas:
        raise _Fail("export 결과에서 IPA를 찾지 못했습니다")
    if len(ipas) > 1:
        print(f"경고: IPA가 {len(ipas)}개여서 {ipas[0].name}을 사용합니다", file=sys.stderr)
    problems = verify_ipa(ipas[0], version, number)
    if problems:
        more = f" 외 {len(problems) - 1}건" if len(problems) > 1 else ""
        raise _Fail(_reason(f"번들 번호 불일치, 업로드하지 않습니다: {problems[0]}{more}. "
                            "앱 확장의 버전/빌드 번호가 본체와 달라 Apple이 거부합니다"))
    return ipas[0].resolve()


def _save_state(cfg: _Cfg, version: str, number: int, attempt: int, ipa: Path) -> None:
    cfg.state_path.parent.mkdir(parents=True, exist_ok=True)
    cfg.state_path.write_text(json.dumps(
        {"version": version, "build_number": number, "attempt": attempt, "ipa_path": str(ipa)},
        ensure_ascii=False), encoding="utf-8")


def _load_state(cfg: _Cfg) -> dict:
    try:
        st = json.loads(cfg.state_path.read_text(encoding="utf-8"))
        state = {"version": str(st["version"]), "build_number": int(st["build_number"]),
                 "attempt": int(st["attempt"]), "ipa_path": str(st["ipa_path"])}
    except FileNotFoundError:
        raise _Fail(f"상태 파일이 없습니다: {cfg.state_path}. 먼저 --phase build를 실행해야 합니다")
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise _Fail(f"상태 파일이 손상되었습니다: {cfg.state_path} ({type(e).__name__}). --phase build부터 다시 실행하세요")
    if not Path(state["ipa_path"]).is_file():
        raise _Fail(f"상태 파일이 가리키는 IPA가 없습니다: {state['ipa_path']}")
    return state


def _confirm_not_uploaded(cfg: _Cfg, number: int, reason: str) -> None:
    """재업로드 직전 ASC에 이번 번호가 이미 있는지 확인한다. 못 믿겠으면 재시도하지 않는다."""
    unknown = "ASC 조회 불가로 재업로드 여부를 확인할 수 없어 중단"
    try:
        token, app_id = _asc_context(cfg)
        for i in range(_REEXIST_CHECKS):
            if asc_client.build_exists(app_id, number, token):
                # 업로드 후 단계 실패일 수도, 같은 초에 번호가 겹친 동시 빌드일 수도 있어 둘을 구분하지 않고 멈춘다
                raise _Fail(_reason("같은 번호의 빌드가 이미 App Store Connect에 있어 재업로드하지 않습니다"
                                    f"(업로드 후 단계 실패 또는 동시 빌드와 번호 충돌). 다시 실행하면 새 번호를 씁니다: {reason}"))
            if i < _REEXIST_CHECKS - 1:
                sleep(_REEXIST_INTERVAL)  # 방금 올린 빌드는 목록 반영이 늦을 수 있다
    except asc_client.AscError as e:
        raise _Fail(_reason(f"{unknown} ({e}). 원래 사유: {reason}"))


def _next_closed_version(cfg: _Cfg, closed_version: str | None, reason: str) -> str:
    """train이 닫혔을 때 다음 패치 버전. 버전을 모르면(90478) ASC로 구한다."""
    if not closed_version:
        try:
            token, app_id = _asc_context(cfg)
            closed_version = closed_max(asc_client.list_app_store_versions(app_id, token))
        except asc_client.AscError as e:
            raise _Fail(_reason(f"닫힌 버전을 알 수 없어 재시도하지 않습니다 ({e}). 원래 사유: {reason}"))
    if not closed_version:
        raise _Fail(_reason(f"닫힌 버전을 알 수 없어 재시도하지 않습니다. 원래 사유: {reason}"))
    try:
        return next_patch(closed_version)
    except ValueError as e:
        raise _Fail(_reason(f"{e}. 원래 사유: {reason}"))


def _phase_build(cfg: _Cfg, info: dict) -> None:
    floors = [cfg.floor, _asc_floor(cfg)]
    nb = build_number.next_build_number(floors=floors)
    number = nb["build_number"]
    info.update(build_number=number, version=cfg.version, attempts=0, built_at_utc=nb["built_at_utc"])
    ipa = _archive_and_export(cfg, cfg.version, number)
    _save_state(cfg, cfg.version, number, 1, ipa)
    info.update(attempts=1, ipa_path=str(ipa))


def _phase_upload(cfg: _Cfg, info: dict) -> None:
    st = _load_state(cfg)
    version, number, attempt, ipa = st["version"], st["build_number"], st["attempt"], Path(st["ipa_path"])
    info.update(build_number=number, version=version, attempts=attempt, ipa_path=str(ipa),
                built_at_utc=build_number.describe(number))
    while True:
        env = dict(os.environ)
        env.update(IPA_PATH=str(ipa), BUILD_NUMBER=str(number), APP_VERSION=version)
        if cfg.mode == "test":
            # 테스트 빌드가 심사 제출까지 가지 않도록 이미 다른 값이 들어와 있어도 못 박는다 (#601)
            env["DEPLOY_MODE"] = "store_only"
        rc, out = run_cmd(["bundle", "exec", "fastlane", "deploy"], str(cfg.ios_dir), env)
        try:
            (cfg.ios_dir / "build" / f"upload_attempt_{attempt}.log").write_text(_scrub(out), encoding="utf-8")
        except OSError as e:
            print(f"경고: 업로드 로그를 저장하지 못했습니다: {e}", file=sys.stderr)
        if rc == 0:
            return

        r = classify_upload_error(out)
        reason = _reason(r["reason_line"])
        kind = r["kind"]
        if kind == "other":
            raise _Fail(reason)
        if kind == "train_closed" and cfg.mode == "release":
            raise _Fail(_reason(f"이미 닫힌 버전이라 릴리스는 재시도하지 않습니다: {reason}"))
        if attempt >= cfg.max_attempts:
            raise _Fail(_reason(f"{cfg.max_attempts}회 시도 후 실패: {reason}"))

        new_version = _next_closed_version(cfg, r["closed_version"], reason) if kind == "train_closed" else version
        _confirm_not_uploaded(cfg, number, reason)

        floors = [cfg.floor, number + 1]
        if kind == "too_low" and r["required_build"]:
            floors.append(r["required_build"] + 1)
        number = build_number.next_build_number(floors=floors)["build_number"]
        version = new_version
        attempt += 1
        info.update(build_number=number, version=version, attempts=attempt,
                    built_at_utc=build_number.describe(number))
        # Flutter 빌드는 다시 하지 않고 아카이브부터 다시 한다
        ipa = _archive_and_export(cfg, version, number)
        info["ipa_path"] = str(ipa)
        _save_state(cfg, version, number, attempt, ipa)


def cmd_archive_upload(args: argparse.Namespace) -> int:
    info: dict = {}
    try:
        cfg = _Cfg()
        cfg.validate()
        (_phase_build if args.phase == "build" else _phase_upload)(cfg, info)
    except _Fail as e:
        reason = _reason(str(e))
        print(f"::error::{reason}", file=sys.stderr)
        _write_github_output({**info, "reason_line": reason})
        _emit({"ok": False, **info, "reason_line": reason, "summary": reason,
               "next": "사유를 확인하고 필요하면 워크플로를 다시 실행"})
        return 1
    done = "빌드 완료" if args.phase == "build" else "업로드 완료"
    summary = f"{done}: 빌드 번호 {info.get('build_number')}, 버전 {info.get('version')}, 시도 {info.get('attempts')}회"
    _write_github_output(info)
    _emit({"ok": True, **info, "summary": summary,
           "next": "archive-upload --phase upload" if args.phase == "build" else None})
    return 0


def _status_fail(reason: str) -> int:
    print(f"::error::{reason}", file=sys.stderr)
    _emit({"ok": False, "reason": reason, "summary": reason, "next": None})
    return 1


def _status_markdown(bundle_id: str, versions: list[dict], closed: str | None, recent: int | None) -> str:
    """실행 요약용 표. 값은 버전 문자열과 상태 이름뿐이라 비밀값이 섞일 수 없다."""
    lines = [f"## App Store Connect 상태 ({bundle_id})", "",
             f"- 닫힌 버전 중 최대: `{closed or '없음'}`",
             f"- 최근 올라간 빌드 번호: `{recent if recent is not None else '조회 안 됨'}`", "",
             "| 버전 | 상태 | 닫힘 |", "|---|---|---|"]
    for v in versions:
        state = v.get("appVersionState") or v.get("appStoreState") or "-"
        lines.append(f"| {v['version']} | {state} | {'예' if v['closed'] else '아니오'} |")
    return "\n".join(lines) + "\n"


def cmd_asc_status(args: argparse.Namespace) -> int:
    """앱 버전 상태와 최근 빌드 번호를 조회만 한다 (#651). 무언가를 올리거나 바꾸지 않는다.
    사전 점검과 달리 조회가 목적이라 조회가 안 되면 폴백하지 않고 실패로 알린다."""
    token = asc_client.token_from_env()
    if not token:
        return _status_fail("ASC 인증 정보 없음 (APP_STORE_CONNECT_API_KEY_ID, ISSUER_ID, API_KEY_BASE64 시크릿 확인)")
    try:
        app_id = asc_client.find_app_id(args.bundle_id, token)
        if not app_id:
            return _status_fail(f"번들 ID {args.bundle_id} 앱을 찾지 못함")
        rows = asc_client.list_app_store_versions(app_id, token)
    except asc_client.AscError as e:
        return _status_fail(f"ASC 조회 실패: {e}")
    try:
        recent = asc_client.recent_max_build(app_id, token)
    except asc_client.AscError as e:
        print(f"경고: 최근 빌드 번호 조회 실패: {e}", file=sys.stderr)
        recent = None

    closed = closed_max(rows)
    versions = []
    for r in rows:
        t = parse_version(r.get("version"))
        is_closed = (r.get("appVersionState") in CLOSED_VERSION_STATES
                     or r.get("appStoreState") in CLOSED_STORE_STATES)
        versions.append({"version": r.get("version"), "appVersionState": r.get("appVersionState"),
                         "appStoreState": r.get("appStoreState"), "closed": is_closed, "_key": t or (0, 0, 0)})
    versions.sort(key=lambda v: v["_key"], reverse=True)  # 최신 버전이 위로
    for v in versions:
        del v["_key"]

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as f:
            f.write(_status_markdown(args.bundle_id, versions, closed, recent))
    _write_github_output({"closed_max": closed or "", "recent_max_build": "" if recent is None else recent})
    _emit({"ok": True, "app_id": app_id, "versions": versions, "closed_max": closed,
           "recent_max_build": recent, "summary": f"닫힌 버전 최대 {closed or '없음'}, 최근 빌드 번호 {recent}", "next": None})
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="iOS 릴리스 판단 로직")
    sub = p.add_subparsers(dest="cmd", required=True)
    pc = sub.add_parser("precheck-version", help="닫힌 버전 사전 점검")
    pc.add_argument("--mode", choices=["test", "release"], required=True)
    pc.add_argument("--version", required=True)
    pc.add_argument("--bundle-id", required=True)
    ce = sub.add_parser("classify-error", help="업로드 로그 분류")
    ce.add_argument("--log", required=True)
    st = sub.add_parser("asc-status", help="앱 버전 상태와 최근 빌드 번호 조회 (조회 전용)")
    st.add_argument("--bundle-id", required=True)
    au = sub.add_parser("archive-upload", help="아카이브, 검증, 업로드와 재시도")
    au.add_argument("--phase", choices=["build", "upload"], required=True)
    args = p.parse_args(argv)
    if args.cmd == "archive-upload":
        return cmd_archive_upload(args)
    if args.cmd == "asc-status":
        return cmd_asc_status(args)
    return cmd_precheck(args) if args.cmd == "precheck-version" else cmd_classify(args)


if __name__ == "__main__":
    sys.exit(main())
