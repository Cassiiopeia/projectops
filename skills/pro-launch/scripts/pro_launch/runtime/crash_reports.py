"""Finding · reading iOS simulator app crash reports (#923).

When a simulator app dies it is left in the Mac's ~/Library/Logs/DiagnosticReports/<executable>-<time>.ips.
In .ips the first line is the header JSON (bundleID · app_name) and the rest is the body JSON (exception · termination · asi · procPath).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

# None means the default spot under home (tests change it)
DIAGNOSTIC_REPORTS_FOLDER: Path | None = None
# Slack comparing report file time with launch time (s) — the file time is slightly after the crash
LAUNCH_TIME_TOLERANCE_SECONDS = 2
# Number of app-side symbols shown from the exception backtrace
EXCEPTION_SYMBOL_COUNT = 5
# System-side frames — useless as cause lines
_SYSTEM_SYMBOL_PREFIXES = ("_", "objc_", "abort", "pthread_", "std::", "start", "UIApplicationMain")
_SYSTEM_SYMBOL_PARTS = ("NSException", "NSAssertionHandler", "CFRunLoop")
_UDID_PATTERN = re.compile(r"^[0-9A-Fa-f-]{36}$")


def diagnostic_reports_folder() -> Path:
    return DIAGNOSTIC_REPORTS_FOLDER or (Path.home() / "Library" / "Logs" / "DiagnosticReports")


def _read_report(path: Path) -> tuple[dict, dict] | None:
    """(header, body). None if unreadable or shaped differently."""
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
    # asi: {"CoreFoundation": ["*** Terminating app due to uncaught exception ..."]} — the cause sentence is here if any
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
    """Newest report of that app (bundle ID) since since. If udid is a UUID, only that simulator's (procPath contains the UDID)."""
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
