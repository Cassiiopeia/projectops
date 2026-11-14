"""learned.json read/write: schema upgrades (pixels > ratios), keeping broken files, atomic save"""
from __future__ import annotations

import re
from pathlib import Path

from common.state import base_dir as _base_dir

from pro_agent_test.storage import _MACHINE, _NOTE_FILE, _scenario_dir


# =========================================================================
# Learning notes — accumulate what only holds for this project
# =========================================================================
#
# Memory principles: skills/references/memory-principles.md (#833 · #837)
#  - Reading is not left to agent calls → a few entries ride on detect · scenario show responses (_surface)
#  - Look for similar entries before writing → merge when certain, show as related when unsure
#  - Scores (ok·fail·last_seen) and staleness → never delete; mark verify and push back
#  - Repo-independent things (flutter·platform) live in one machine-scope place


def _note_path(root: Path, create: bool = False) -> Path:
    return _scenario_dir(root, create) / _NOTE_FILE


def _machine_note_path() -> Path:
    return _base_dir() / "agent-test" / _MACHINE / _NOTE_FILE


# Schema version of this file. Bump only for changes that remove fields.
# 2: added the variants axis to screens (#583)
# 3: variants taps (pixels) → targets (elements·ratios), originals kept as legacy_taps (#838)
_NOTE_SCHEMA = 3


def _variant_key(role: str | None, screen_size: str | None) -> str:
    """Key that identifies one set of coordinates.

    Even at the same resolution, **a different build means a different screen.** Different builds per role
    are common (sometimes only one side is reinstalled), so the role is in the key. Role names are only
    used as JSON keys, so Korean or spaces are safe — they are never used as shell variable names.
    """
    return "%s@%s" % (role or "default", screen_size or "?")


def _promote_screen(entry: dict) -> dict:
    """Upgrade the old format (one coordinate set per screen) into a single variant.

    Upgraded on read; the file is updated on the next write. It must not break records
    existing projects have built up — nobody would use it if told to delete and re-measure.
    """
    if "variants" in entry:
        return entry
    legacy = {k: entry.pop(k) for k in ("taps", "measured_on") if k in entry}
    entry["variants"] = ({_variant_key(None, legacy.get("measured_on")): legacy}
                         if legacy else {})
    return entry


_SIZE = re.compile(r"(\d{2,5})x(\d{2,5})")
_LOCATORS = ("text", "id", "desc")


def _fmt_ratio(v: float) -> str:
    """Short like 0.815. Four decimals stay within 1px even at 1080 width."""
    return f"{round(v, 4):.4f}".rstrip("0").rstrip(".") or "0"


def _px_to_at(xy: str, size: str | None) -> str | None:
    """'540,1956' @ '1080x2400' → '0.5,0.815'. None if it cannot convert."""
    m = _SIZE.fullmatch(size or "")
    p = re.fullmatch(r"\s*(\d+)\s*,\s*(\d+)\s*", xy or "")
    if not (m and p):
        return None
    w, h = int(m.group(1)), int(m.group(2))
    x, y = int(p.group(1)), int(p.group(2))
    if not (0 <= x <= w and 0 <= y <= h):
        return None
    return f"{_fmt_ratio(x / w)},{_fmt_ratio(y / h)}"


def _migrate_variant(v: dict) -> dict:
    """Convert pixel taps to ratio targets (#838).

    `launch_cli app tap` rejects pixels (#826). Old records left as is are unusable.
    Converted values are only computed, not confirmed, so verify is attached and originals are kept as legacy_taps.
    Converted in memory on every read; the file is updated on the next write.
    """
    taps = v.get("taps")
    if not isinstance(taps, dict):
        return v
    v.pop("taps")
    targets = v.setdefault("targets", {})
    unconverted = []
    for label, xy in taps.items():
        if label in targets:
            continue
        at = _px_to_at(str(xy), v.get("measured_on"))
        if at:
            targets[label] = {"at": at, "verify": True}
        else:
            unconverted.append(label)
    v["legacy_taps"] = {**(v.get("legacy_taps") or {}), **taps}
    if unconverted:
        # Without a resolution it cannot convert to ratios — do not delete; ask to re-measure
        v["unconverted"] = sorted(set((v.get("unconverted") or []) + unconverted))
    return v


def _migrate_screens(notes: dict) -> None:
    screens = notes.get("screens")
    if not isinstance(screens, dict):
        return
    for entry in screens.values():
        if not isinstance(entry, dict):
            continue
        _promote_screen(entry)
        for v in (entry.get("variants") or {}).values():
            if isinstance(v, dict):
                _migrate_variant(v)


def _read_notes(f: Path) -> tuple[dict, str | None]:
    """Read the accumulated records. Even if unreadable, **never delete them.**

    Returns: (content, warning). If there is a warning, the caller must tell the user.

    Overwriting a broken file with an empty value silently loses everything built up. It can break
    through edit conflicts or partial writes, so keep the original aside and start fresh.
    """
    import json
    from datetime import datetime

    empty = {"schema": _NOTE_SCHEMA, "constraints": [], "screens": {},
             "pitfalls": [], "runs": []}
    if not f.exists():
        return empty, None
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("top level is not an object")
    except (json.JSONDecodeError, ValueError, OSError) as e:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = f.with_suffix(f".broken-{stamp}.json")
        try:
            backup.write_bytes(f.read_bytes())
            where = str(backup.name)
        except OSError:
            where = "(backup failed)"
        return empty, f"Could not read {f.name} ({e}). Moved the original to {where}"

    # Unknown fields are left alone — another harness or a later version may have written them
    for k, v in empty.items():
        data.setdefault(k, v)
    for k in ("constraints", "pitfalls", "runs"):
        if not isinstance(data.get(k), list):
            data[k] = []
    _migrate_screens(data)
    return data, None


def _load_notes(root: Path) -> tuple[dict, str | None]:
    return _read_notes(_note_path(root))


def _save_notes(f: Path, notes: dict) -> None:
    """Write atomically — the existing file survives even if writing stops midway.

    Bump the schema version on write — structures converted on read (targets etc.) go into the file now.
    """
    import json
    import os
    notes["schema"] = _NOTE_SCHEMA
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_name(f"{f.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(notes, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    os.replace(tmp, f)      # atomic within one filesystem


def _locator(t: dict) -> dict:
    return {k: t[k] for k in (*_LOCATORS, "index", "at") if k in t}
