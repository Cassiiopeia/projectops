"""Memory staleness handling: superseded marker (superseded_by) · table of known stale entries (#932).

Memory is the method as of when it was recorded. Once an official KB entry or new feature appears, old entries drift from current practice.
Instead of deleting, a superseded marker makes recall put it last and keeps it out of responses.
"""
from __future__ import annotations

from pathlib import Path

import knowledge

# (key, area, superseded_by, reason). superseded_by: "kb:<id>" official KB · "feature:<command>" new feature
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
# Test pollution where verification credentials were left by auto-learning — removed by prefix
LEAKED_KEY_PREFIXES = ("server.zz-verify.",)


def mark_superseded(path: Path, key: str, by: str, area: str | None = None, reason: str | None = None) -> int:
    """Mark the key entry as superseded > number marked."""
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
    """Entries in this file hit by the stale table: [{key, action: supersede|delete, by?, reason}] (already marked ones are skipped)."""
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
    """Apply the stale table (superseded markers · delete test pollution) > handled entries."""
    done = []
    for match in stale_matches(path):
        if match["action"] == "delete":
            knowledge.forget(path, match["key"])
        else:
            mark_superseded(path, match["key"], match["by"], reason=match["reason"])
        done.append(match)
    return done
