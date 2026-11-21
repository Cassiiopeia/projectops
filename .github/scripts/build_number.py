#!/usr/bin/env python3
"""
build_number.py

App build number rule (issue #643). The only place the numbering rule lives.

  build number = max(current UTC time - 2024-01-01 00:00:00 UTC (seconds), floors)

Time never goes backward, so a later number is always larger. It increases regardless of concurrent builds,
build order or issue number, and needs no external API to decide.
The caller supplies floors (--floor) (latest ASC number + 1, number + 1 demanded by an Apple rejection, etc.).

About 87 million as of 2026; it reaches the Android versionCode limit (2,100,000,000) in 2090.
EPOCH_2024 must be replaced with a new base time before then.

  - Commands: next | describe
  - Output: always JSON (ok / data / summary / next)

Usage:
  python3 build_number.py next --floor 86677591
  python3 build_number.py describe 86677440
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from github_output import emit_json as _emit, write_github_output as _write_github_output  # noqa: E402

# 2024-01-01 00:00:00 UTC
EPOCH_2024 = 1704067200


def time_based_number(now: float | None = None) -> int:
    """Seconds elapsed since the base time."""
    if now is None:
        now = time.time()
    return int(now) - EPOCH_2024


def describe(number: int) -> str:
    """Turn a number back into a UTC ISO string (for debugging)."""
    ts = EPOCH_2024 + int(number)
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def next_build_number(floors: list[int] | None = None, now: float | None = None) -> dict:
    """The larger of the time number and the floors. None and floors <= 0 mean a failed lookup or no value, so they are ignored."""
    t = time_based_number(now)
    valid = [int(f) for f in (floors or []) if f is not None and int(f) > 0]
    top = max(valid) if valid else None
    if top is not None and top > t:
        number, source = top, "floor"
    else:
        number, source = t, "time"
    return {"build_number": number, "source": source, "built_at_utc": describe(number)}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="App build number rule")
    sub = p.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("next", help="Compute the next build number")
    n.add_argument("--floor", type=int, action="append", default=[], help="Lower bound for the number (repeatable)")
    d = sub.add_parser("describe", help="Convert a number back to UTC time")
    d.add_argument("number", type=int)
    args = p.parse_args(argv)

    if args.cmd == "next":
        r = next_build_number(floors=args.floor)
        _write_github_output({"build_number": r["build_number"]})
        _emit({
            "ok": True, **r,
            "summary": f"Build number {r['build_number']} ({r['source']}, {r['built_at_utc']})",
            "next": None,
        })
        return 0

    _emit({
        "ok": True, "number": args.number, "built_at_utc": describe(args.number),
        "summary": f"{args.number} = {describe(args.number)}", "next": None,
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())
