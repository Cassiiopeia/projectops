"""iOS 시뮬레이터 앱 크래시 리포트 찾기 · 읽기 (#923).

시뮬레이터 앱이 죽으면 맥의 ~/Library/Logs/DiagnosticReports/<실행파일>-<시각>.ips 에 남는다.
.ips 는 첫 줄이 머리 JSON(bundleID · app_name), 나머지가 본문 JSON(exception · termination · asi · procPath)이다.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

# None 이면 홈 아래 기본 자리 (테스트가 바꾼다)
DIAGNOSTIC_REPORTS_FOLDER: Path | None = None
# 리포트 파일 시각과 띄운 시각 비교 여유 (초) — 파일 시각은 크래시보다 조금 뒤다
LAUNCH_TIME_TOLERANCE_SECONDS = 2
# 예외 백트레이스에서 보여 줄 앱 쪽 심볼 수
EXCEPTION_SYMBOL_COUNT = 5
# 시스템 쪽 프레임 — 원인 줄로는 쓸모가 없다
_SYSTEM_SYMBOL_PREFIXES = ("_", "objc_", "abort", "pthread_", "std::", "start", "UIApplicationMain")
_SYSTEM_SYMBOL_PARTS = ("NSException", "NSAssertionHandler", "CFRunLoop")
_UDID_PATTERN = re.compile(r"^[0-9A-Fa-f-]{36}$")


def diagnostic_reports_folder() -> Path:
    return DIAGNOSTIC_REPORTS_FOLDER or (Path.home() / "Library" / "Logs" / "DiagnosticReports")


def _read_report(path: Path) -> tuple[dict, dict] | None:
    """(머리, 본문). 읽지 못하거나 모양이 다르면 None."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        header_line, _, body_text = text.partition("\n")
        header, body = json.loads(header_line), json.loads(body_text)
    except (OSError, json.JSONDecodeError):
        return None
    return (header, body) if isinstance(header, dict) and isinstance(body, dict) else None


def _is_system_symbol(symbol: str) -> bool:
    return symbol.startswith(_SYSTEM_SYMBOL_PREFIXES) or any(part in symbol for part in _SYSTEM_SYMBOL_PARTS)


def parse_crash_report(path: Path) -> dict | None:
    """.ips > {path, bundle_id, captured_at, exception, termination, reason, symbols, exception_line}."""
    report = _read_report(path)
    if report is None:
        return None
    header, body = report
    exception = body.get("exception") or {}
    termination = body.get("termination") or {}
    # asi: {"CoreFoundation": ["*** Terminating app due to uncaught exception ..."]} — 원인 문장이 있으면 여기다
    reasons = [line for lines in (body.get("asi") or {}).values() if isinstance(lines, list)
               for line in lines if isinstance(line, str)]
    symbols = [frame.get("symbol") for frame in body.get("lastExceptionBacktrace") or []
               if isinstance(frame, dict) and frame.get("symbol")
               and not _is_system_symbol(frame["symbol"])][:EXCEPTION_SYMBOL_COUNT]
    exception_text = " ".join(x for x in (exception.get("type"), f"({exception['signal']})"
                                          if exception.get("signal") else None) if x)
    exception_line = (reasons[0] if reasons else
                      " · ".join(x for x in (exception_text, termination.get("indicator"),
                                             symbols[0] if symbols else None) if x))
    return {"path": str(path), "bundle_id": header.get("bundleID"), "captured_at": body.get("captureTime"),
            "exception": exception_text or None, "termination": termination.get("indicator"),
            "reason": reasons[0] if reasons else None, "symbols": symbols,
            "exception_line": exception_line[:300] or None}


def newest_crash_report(bundle_id: str, udid: str | None, since_epoch: float) -> dict | None:
    """그 앱(번들 ID)의 since 이후 가장 새 리포트. udid 가 UUID 면 그 시뮬레이터 것만 (procPath 에 UDID 가 들어 있다)."""
    folder = diagnostic_reports_folder()
    if not folder.is_dir():
        return None
    candidates = []
    for path in folder.glob("*.ips"):
        try:
            modified = path.stat().st_mtime
        except OSError:
            continue
        if modified >= since_epoch - LAUNCH_TIME_TOLERANCE_SECONDS:
            candidates.append((modified, path))
    for _, path in sorted(candidates, reverse=True):
        report = _read_report(path)
        if report is None or report[0].get("bundleID") != bundle_id:
            continue
        if udid and _UDID_PATTERN.match(udid) and udid not in str(report[1].get("procPath") or ""):
            continue
        return parse_crash_report(path)
    return None
