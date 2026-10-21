"""기억의 낡음 처리: 대체 표시(superseded_by) · 알려진 낡은 항목 표 (#932).

기억은 기록 당시의 방식이다. 이후 공식 KB·신기능이 생기면 옛 항목이 현행과 어긋난다.
지우지 않고 대체 표시를 달면 recall 이 맨 뒤로 보내고 응답에는 싣지 않는다.
"""
from __future__ import annotations

from pathlib import Path

import knowledge

# (key, area, superseded_by, 이유). superseded_by: "kb:<id>" 공식 KB · "feature:<명령>" 신기능
STALE_TABLE = (
    ("web.file_upload_cdp", "web", "feature:web upload", "the web upload command was added (#876)"),
    ("web.sticky_header_click", "web", "feature:web click --dom-click", "auto-recovery and --dom-click were added (#879)"),
    ("web.shared_browser_hijack", "web", "feature:web tab", "web tab new · LAUNCH_TAB were added (#878)"),
    ("web.asc.login", "web", "feature:web --frame", "duplicates web.apple_login_iframe; --frame was added (#877)"),
    ("web.apple_login_iframe", "web", "feature:web --frame", "the --frame option was added (#877)"),
    ("android.swipe.midstate", "android", "kb:app.md gesture playbook",
     "contradicts the #862 measured finding that mid-gesture frames cannot be captured by device control"),
    ("android.maestro.driver", "android", "feature:app flow",
     "pkill maestro kills other sessions — app flow does not kill the host maestro"),
)
# 검증용 자격증명이 자동 학습으로 남은 테스트 오염 — 접두사로 지운다
LEAKED_KEY_PREFIXES = ("server.zz-verify.",)


def mark_superseded(path: Path, key: str, by: str, area: str | None = None, reason: str | None = None) -> int:
    """key 항목에 대체 표시를 단다 > 표시한 건수."""
    normalized = knowledge.norm_key(key)
    entries = knowledge.load(path)
    marked = 0
    for entry in entries:
        if entry["key"] == normalized and (area is None or entry["area"] == area):
            entry["superseded_by"] = by
            if reason:
                entry["superseded_reason"] = reason
            marked += 1
    if marked:
        knowledge.save(path, entries)
    return marked


def stale_matches(path: Path) -> list[dict]:
    """이 파일에서 낡은 항목 표에 걸리는 것: [{key, action: supersede|delete, by?, reason}] (표시가 이미 있으면 뺀다)."""
    found = []
    for entry in knowledge.load(path):
        if entry["key"].startswith(LEAKED_KEY_PREFIXES):
            found.append({"key": entry["key"], "action": "delete", "reason": "test pollution from a verification credential"})
            continue
        for key, area, by, reason in STALE_TABLE:
            if entry["key"] == key and entry["area"] == area and not entry.get("superseded_by"):
                found.append({"key": key, "action": "supersede", "by": by, "reason": reason})
    return found


def apply_stale_table(path: Path) -> list[dict]:
    """낡은 항목 표를 적용한다 (대체 표시 · 테스트 오염 삭제) > 처리한 항목."""
    done = []
    for match in stale_matches(path):
        if match["action"] == "delete":
            knowledge.forget(path, match["key"])
        else:
            mark_superseded(path, match["key"], match["by"], reason=match["reason"])
        done.append(match)
    return done
