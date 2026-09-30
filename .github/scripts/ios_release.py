#!/usr/bin/env python3
"""
ios_release.py

iOS 테스트 빌드와 릴리스의 버전 판단과 Apple 업로드 오류 해석 (이슈 #643).
Apple 오류 해석의 유일한 위치다. 새 오류 코드는 여기 패턴과 test_ios_release.py의
실제 문구 샘플을 함께 추가한다.

버전 닫힘 규칙: 앱 버전(train)은 승인되는 순간 닫히고, 이후 개발자 반려로도 다시 열리지 않는다.
닫힌 버전으로 올리면 12~18분 빌드 뒤 업로드에서 거부되므로, 테스트 빌드는 빌드 전에
다음 패치 버전으로 바꾸고 릴리스는 즉시 실패시킨다.

  - 커맨드: precheck-version | classify-error
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
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import asc_client  # noqa: E402

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
                   re.compile(r"\bDUPLICATE\b"), re.compile(r"-19232")]),
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
            f.write(f"{k}={v}\n")


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


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="iOS 릴리스 판단 로직")
    sub = p.add_subparsers(dest="cmd", required=True)
    pc = sub.add_parser("precheck-version", help="닫힌 버전 사전 점검")
    pc.add_argument("--mode", choices=["test", "release"], required=True)
    pc.add_argument("--version", required=True)
    pc.add_argument("--bundle-id", required=True)
    ce = sub.add_parser("classify-error", help="업로드 로그 분류")
    ce.add_argument("--log", required=True)
    args = p.parse_args(argv)
    return cmd_precheck(args) if args.cmd == "precheck-version" else cmd_classify(args)


if __name__ == "__main__":
    sys.exit(main())
