"""Free-form notes of past work, read again when you come back to the same place (work journal).

Where `knowledge` (learn) takes a one-line conclusion like "this method worked", this takes **the context of one task**.
What was done and why, in what order, how it turned out, what may confuse next time — no fixed format.
Whether and what to write is up to the agent and the user. The tool only stores and brings it back.

  ~/.projectops/launch/<owner__repo>/journal.jsonl

Reading is not left to the agent — when the same area is opened again launch_cli attaches it as `journal`.
It survives `--brief`·`--fields` and is not consumed by failed responses (projectops#1023).
What is written is **reference** only and never auto-run. Changes go through user confirmation.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

from common import memory
from common.access import find_secrets
from common.state import state_dir

import knowledge

FILE = "journal.jsonl"
MAX_TEXT = 1500      # max characters per entry — so reading does not flood tokens at once
MAX_TITLE = 80
MAX_ENTRIES = 40     # oldest removed first when exceeded
SURFACE_LIMIT = 2    # recent entries attached to a response
SURFACE_CHARS = 400  # characters per entry when attached to a response


def store_path(root: Path) -> Path:
    return state_dir("launch", root) / FILE


def load(path: Path) -> list[dict]:
    """On read failure continue with an empty journal — work must not stop because the journal is broken."""
    rows: list[dict] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return rows
    for ln in lines:
        try:
            r = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if isinstance(r, dict) and r.get("text"):
            rows.append({"at": str(r.get("at") or ""), "title": str(r.get("title") or ""),
                         "area": str(r.get("area") or ""), "site": str(r.get("site") or ""),
                         "text": str(r["text"])})
    return rows


def _save(path: Path, rows: list[dict]) -> None:
    """Write to a temp file and swap — no half-written file even with concurrent sessions."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    os.replace(tmp, path)


def add(path: Path, text: str, title: str = "", area: str = "", site: str = "",
        now: str | None = None) -> dict:
    """Add one entry to the journal. On failure {"error": code, "message": ...}."""
    text = (text or "").strip()
    title = " ".join((title or "").split())[:MAX_TITLE]
    if not text:
        return {"error": "empty", "message": "Nothing to write: the text is empty"}
    if area and area not in knowledge.AREAS:
        return {"error": "bad_area", "message": f"area must be one of {'/'.join(knowledge.AREAS)}"}
    if knowledge.FORBIDDEN.search(text):
        return {"error": "forbidden_method",
                "message": "Methods that click coordinates with the host mouse are not remembered — use the project E2E"}
    secrets = find_secrets(title + " " + text)
    if secrets:
        return {"error": "secret_detected",
                "message": "Not saved: it contains what looks like a secret: " + ", ".join(secrets)}
    row = {"at": now or dt.datetime.now().strftime("%Y-%m-%d %H:%M"), "title": title,
           "area": area, "site": " ".join((site or "").split()), "text": text[:MAX_TEXT]}
    rows = load(path)
    rows.append(row)
    if len(rows) > MAX_ENTRIES:
        del rows[:len(rows) - MAX_ENTRIES]
    _save(path, rows)
    return {"entry": row, "total": len(rows), "truncated": len(text) > MAX_TEXT}


def recent(path: Path, limit: int = SURFACE_LIMIT, area: str | None = None,
           site: str | None = None) -> list[dict]:
    """Newest first. site is a partial match (find by part of the URL)."""
    rows = load(path)
    if area:
        rows = [r for r in rows if r["area"] == area or not r["area"]]
    if site:
        rows = [r for r in rows if site.lower() in (r["site"] + " " + r["title"]).lower()]
    return list(reversed(rows))[:limit]


def forget(path: Path, title: str) -> int:
    """Remove entries whose title matches exactly."""
    rows = load(path)
    keep = [r for r in rows if r["title"] != title]
    if len(keep) != len(rows):
        _save(path, keep)
    return len(rows) - len(keep)


def surface(path: Path, area: str, seen_file: Path, limit: int = SURFACE_LIMIT,
            today: str | None = None, mark: bool = True) -> list[dict]:
    """Recent journal entries to attach to a command response. Once a day per repo and area (saves tokens).

    mark=False (failed command) attaches without counting as 'shown today' — it is attached again on the next success.
    Failed responses are easily discarded, so consuming it there meant it did not show again that day (projectops#1023).
    """
    now = today or dt.date.today().isoformat()
    if memory.seen_today(seen_file, area, now, mark=False):
        return []
    rows = recent(path, limit, area=area)
    if not rows:
        # Nothing shown does not count as 'shown today' — otherwise entries written later that day would be hidden
        return []
    if mark:
        memory.seen_today(seen_file, area, now)
    out = []
    for r in rows:
        t = r["text"] if len(r["text"]) <= SURFACE_CHARS else r["text"][:SURFACE_CHARS] + " …"
        out.append({"at": r["at"], "title": r["title"], "site": r["site"], "text": t})
    return out
