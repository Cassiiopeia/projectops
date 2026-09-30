#!/usr/bin/env python3
"""
build_number.py

앱 빌드 번호 규칙 (이슈 #643). 번호 규칙의 유일한 위치다.

  빌드 번호 = max(현재 UTC 시각 - 2024-01-01 00:00:00 UTC (초), 하한들)

시간은 거꾸로 가지 않으므로 나중에 뽑은 번호가 항상 더 크다. 동시 빌드, 빌드 순서,
이슈 번호와 무관하게 우상향하고 번호를 정하는 데 외부 API가 필요 없다.
하한(--floor)은 호출하는 쪽이 넣는다 (ASC 최근 번호 + 1, Apple 거부 메시지가 요구한 번호 + 1 등).

2026년 기준 약 8,700만이며 Android versionCode 상한(2,100,000,000)에는 2090년에 닿는다.
그 전에 EPOCH_2024를 새 기준 시각으로 교체해야 한다.

  - 커맨드: next | describe
  - 출력: 언제나 JSON (ok / 데이터 / summary / next)

사용 예:
  python3 build_number.py next --floor 86677591
  python3 build_number.py describe 86677440
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone

# 2024-01-01 00:00:00 UTC
EPOCH_2024 = 1704067200


def time_based_number(now: float | None = None) -> int:
    """기준 시각으로부터 지난 초."""
    if now is None:
        now = time.time()
    return int(now) - EPOCH_2024


def describe(number: int) -> str:
    """번호를 UTC ISO 문자열로 되돌린다 (디버깅용)."""
    ts = EPOCH_2024 + int(number)
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def next_build_number(floors: list[int] | None = None, now: float | None = None) -> dict:
    """시각 번호와 하한 중 큰 값. None과 0 이하 하한은 조회 실패나 값 없음이므로 무시한다."""
    t = time_based_number(now)
    valid = [int(f) for f in (floors or []) if f is not None and int(f) > 0]
    top = max(valid) if valid else None
    if top is not None and top > t:
        number, source = top, "floor"
    else:
        number, source = t, "time"
    return {"build_number": number, "source": source, "built_at_utc": describe(number)}


def _write_github_output(pairs: dict) -> None:
    """GITHUB_OUTPUT이 있을 때만 key=value를 덧붙인다."""
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as f:
        for k, v in pairs.items():
            f.write(f"{k}={v}\n")


def _emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="앱 빌드 번호 규칙")
    sub = p.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("next", help="다음 빌드 번호 계산")
    n.add_argument("--floor", type=int, action="append", default=[], help="번호 하한 (여러 번 가능)")
    d = sub.add_parser("describe", help="번호를 UTC 시각으로 되돌림")
    d.add_argument("number", type=int)
    args = p.parse_args(argv)

    if args.cmd == "next":
        r = next_build_number(floors=args.floor)
        _write_github_output({"build_number": r["build_number"]})
        _emit({
            "ok": True, **r,
            "summary": f"빌드 번호 {r['build_number']} ({r['source']}, {r['built_at_utc']})",
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
