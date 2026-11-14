"""Remembers the interaction methods that actually worked on this computer (per-computer learning notes).

Design: docs/superpowers/specs/2026-10-10-agent-memory-design.md (#833)
 - Reading is not left to the agent — launch_cli attaches it to command responses as `memory`
 - Verified successes are recorded by the CLI itself (auto_record). Failures and missing installs are not auto-recorded
 - Before writing, similar entries across all repos and this computer are found and merged (learn_smart)

  ~/.projectops/launch/<owner__repo>/knowledge.json   this repo + this computer
  ~/.projectops/launch/_machine/knowledge.json        this whole computer

**App screens and coordinates do not go here** — pro-agent-test `note` (learned.json) owns those.
This only covers tools and methods (Maestro for iOS, --headed for Google sign-in, etc.).

Reinforcement is a counter. Reported success is ok+1, failure is fail+1, and recall orders by (ok-fail).
Recall size (count and characters) is capped to save tokens.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
from pathlib import Path

from common import memory
from common.access import find_secret_spans
from common.state import base_dir, state_dir

FILE = "knowledge.json"
SCHEMA = 1
AREAS = ("ios", "android", "web", "server", "desktop")
SCOPES = ("repo", "machine")
MAX_ENTRIES = 30        # cap per scope — lowest-scoring entries are removed first when exceeded
MAX_HOW = 200           # max characters per entry (keeps one recall to a few hundred tokens)
MAX_DETAIL = 4000       # max characters of a --detail note — long lessons like history or reasons that do not fit one line (#863)
NOTES_DIR = "notes"     # note location: <memory file folder>/notes/<key>.md
MAX_KEY = 60
DEFAULT_LIMIT = 5
STALE_DAYS = memory.STALE_DAYS

# Forbidden methods memory can never override: moving the host mouse to click screen coordinates (#640).
# Blocked on both save and recall — must also be filtered when it comes from hand-edited or old files.
FORBIDDEN = re.compile(
    r"(?i)\bcliclick\b|\bxdotool\b|CGEvent|System\s*Events.*(click|keystroke)|osascript.*click")


def _machine_dir() -> Path:
    return base_dir() / "launch" / "_machine"


def store_path(scope: str, root: Path) -> Path:
    if scope == "machine":
        return _machine_dir() / FILE
    return state_dir("launch", root) / FILE


def _today(today: str | None) -> str:
    return today or dt.date.today().isoformat()


def load(path: Path) -> list[dict]:
    """On read failure continue with empty notes — work must not stop because memory is broken."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = data.get("entries") if isinstance(data, dict) else None
    out = []
    for r in rows or []:
        if isinstance(r, dict) and r.get("key") and r.get("how") and r.get("area") in AREAS:
            row = {"key": str(r["key"]), "area": r["area"], "how": str(r["how"]),
                   "ok": int(r.get("ok") or 0), "fail": int(r.get("fail") or 0),
                   "last_seen": str(r.get("last_seen") or "")}
            if r.get("detail"):
                row["detail"] = str(r["detail"])
            # Version at record time · superseded marker (#932)
            for extra in ("plugin_version", "superseded_by", "superseded_reason"):
                if r.get(extra):
                    row[extra] = str(r[extra])
            out.append(row)
    return out


def save(path: Path, entries: list[dict]) -> None:
    """Write to a temp file and swap — no half-written file even with concurrent sessions."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps({"schema": SCHEMA, "entries": entries},
                              ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def current_plugin_version() -> str | None:
    """Skill version to record. None outside pro_launch (tests, other skills)."""
    try:
        from pro_launch.runtime.plugin_version import UNKNOWN_VERSION, plugin_version
    except ImportError:
        return None
    version = plugin_version()
    return None if version == UNKNOWN_VERSION else version


def norm_key(key: str) -> str:
    return re.sub(r"[^a-z0-9._-]+", "-", (key or "").strip().lower()).strip("-")[:MAX_KEY]


def _score(e: dict) -> int:
    return e["ok"] - e["fail"]


def _stale(e: dict, today: str) -> bool:
    return memory.stale(e["last_seen"], today, STALE_DAYS)


def note_path(store: Path, key: str) -> Path:
    """Long lesson note > <memory file folder>/notes/<key>.md"""
    return store.parent / NOTES_DIR / f"{norm_key(key)}.md"


def _secret_error(text: str) -> dict | None:
    """Rejection result when secrets are present (with the offending span masked — so the agent can rewrite it, #882)."""
    spans = find_secret_spans(text)
    if not spans:
        return None
    return {"error": "secret_detected",
            "message": "Not saved: it contains what looks like a secret: "
                       + ", ".join(f"{s['label']}({s['matched_span']})" for s in spans),
            "matched_span": [s["matched_span"] for s in spans]}


def learn(path: Path, area: str, key: str, how: str, result: str,
          today: str | None = None, detail: str | None = None) -> dict:
    """Insert or update an entry. On failure {"error": code, "message": ...}.

    If how exceeds the cap it is rejected as too_long rather than truncated — silent truncation loses the conclusion mid-sentence (#863).
    """
    if area not in AREAS:
        return {"error": "bad_area", "message": f"area must be one of {'/'.join(AREAS)}"}
    if result not in ("ok", "fail"):
        return {"error": "bad_result", "message": "result must be ok or fail"}
    k = norm_key(key)
    how = " ".join((how or "").split())
    if not k or not how:
        return {"error": "empty", "message": "key and how are empty"}
    if FORBIDDEN.search(how):
        return {"error": "forbidden_method",
                "message": "Methods that click coordinates with the host mouse are not remembered — use the project E2E"}
    if len(how) > MAX_HOW:
        return {"error": "too_long", "length": len(how), "limit": MAX_HOW,
                "message": f"how is {len(how)} chars, over the {MAX_HOW}-char limit — keep only the one-line conclusion in how "
                           "and pass the background·reason with --detail"}
    detail = (detail or "").strip()
    if len(detail) > MAX_DETAIL:
        return {"error": "too_long", "length": len(detail), "limit": MAX_DETAIL,
                "message": f"detail is {len(detail)} chars, over the {MAX_DETAIL}-char limit — keep only the essentials"}
    secret = _secret_error(k + " " + how + " " + detail)
    if secret:
        return secret
    now = _today(today)
    entries = load(path)
    cur = next((e for e in entries if e["key"] == k and e["area"] == area), None)
    if cur is None:
        cur = {"key": k, "area": area, "how": how, "ok": 0, "fail": 0, "last_seen": now}
        entries.append(cur)
    elif cur["how"] != how:
        # If the method changed, do not inherit the old method's record
        cur.update(how=how, ok=0, fail=0)
        # A new method invalidates the old superseded marker
        cur.pop("superseded_by", None)
        cur.pop("superseded_reason", None)
    cur[result] += 1
    cur["last_seen"] = now
    version = current_plugin_version()
    if version:
        cur["plugin_version"] = version
    if detail:
        # Notes are overwritten — the latest history for the same key is the right one
        note = note_path(path, k)
        note.parent.mkdir(parents=True, exist_ok=True)
        note.write_text(f"# {k} ({area}, {now})\n\n{cur['how']}\n\n{detail}\n", encoding="utf-8")
        cur["detail"] = note.name
    if len(entries) > MAX_ENTRIES:
        entries.sort(key=lambda e: (_score(e), e["last_seen"]), reverse=True)
        del entries[MAX_ENTRIES:]
    save(path, entries)
    return {"entry": cur, "total": len(entries)}


def forget(path: Path, key: str, area: str | None = None) -> int:
    k = norm_key(key)
    entries = load(path)
    keep = [e for e in entries if not (e["key"] == k and (area is None or e["area"] == area))]
    if len(keep) != len(entries):
        save(path, keep)
    return len(entries) - len(keep)


def _matches(entry: dict, note: Path | None, match: str) -> bool:
    """Does the word appear in the key, method or note body (case-insensitive)."""
    needle = match.lower()
    if needle in (entry["key"] + " " + entry["how"]).lower():
        return True
    try:
        return bool(note) and needle in note.read_text(encoding="utf-8").lower()
    except OSError:
        return False


def recall(paths: dict[str, Path], area: str | None, limit: int = DEFAULT_LIMIT,
           today: str | None = None, match: str | None = None) -> list[dict]:
    """Return only the top entries. Forbidden methods are filtered out; doubtful ones are marked verify.

    match: only entries whose key, method or note contains this word (e.g. swipe). If a note exists its path is given as detail_path.
    """
    now = _today(today)
    rows = []
    for scope, p in paths.items():
        for e in load(p):
            if area and e["area"] != area:
                continue
            if FORBIDDEN.search(e["how"]):
                continue
            note = note_path(p, e["key"]) if e.get("detail") else None
            if note is not None and not note.is_file():
                note = None
            if match and not _matches(e, note, match):
                continue
            e = {k: v for k, v in e.items() if k != "detail"}
            if note is not None:
                e["detail_path"] = str(note)
            stale = _stale(e, now)
            is_superseded = bool(e.get("superseded_by"))
            # Superseded entries go last (-1), stale ones just before them (0)
            rows.append({**e, "scope": scope,
                         "verify": bool(e["fail"] and e["fail"] >= e["ok"]) or stale or is_superseded,
                         "_rank": (-1 if is_superseded else 0 if stale else 1, _score(e), e["last_seen"])})
    rows.sort(key=lambda r: r["_rank"], reverse=True)
    for r in rows:
        del r["_rank"]
    return rows[:max(1, limit)]


def area_summary(paths: dict[str, Path]) -> dict[str, dict]:
    """Memory count and last use per area > {area: {count, last_seen}} (doctor one-line summary, #863)."""
    summary = {area: {"count": 0, "last_seen": None} for area in AREAS}
    for store in paths.values():
        for entry in load(store):
            row = summary[entry["area"]]
            row["count"] += 1
            if entry["last_seen"] and (row["last_seen"] or "") < entry["last_seen"]:
                row["last_seen"] = entry["last_seen"]
    return summary


# ── Dedup · scope promotion · exposure log (#833) ──────────────────────────────
#
# The same knowledge piled up per repo under different keys (observed: ASC iframe sign-in in 4 places). Repo-independent
# knowledge must live in one place at this-computer scope (_machine) so other repos can use it right away.

# Similarity and exposure-cap rules must match pro-agent-test note, so common/memory.py is the single source (#837).
# Keep this module's public names (SIMILAR·RELATED·overlap·similar …) — launch_cli and tests use them.
SIMILAR = memory.SIMILAR
RELATED = memory.RELATED
_GENERIC = memory._GENERIC
HIDE_FAILS_OVER = memory.HIDE_FAILS_OVER
_WORD = memory._WORD
_words = memory.words


def overlap(a: dict, b: dict) -> float:
    return memory.overlap(a, b, field="how", group="area", key="key")


def similar(a: dict, b: dict) -> bool:
    """Is this surely the same knowledge to merge automatically (same key, or 60%+ overlap of distinctive words)."""
    return overlap(a, b) >= SIMILAR


def related_entries(probe: dict, exclude: Path | None = None) -> list[dict]:
    """Vaguely similar memories — the agent decides whether to merge (Hermes' "search before adding")."""
    out = []
    machine = _machine_dir() / FILE
    for p in [machine, *all_repo_paths()]:
        if exclude is not None and p.resolve() == exclude.resolve():
            continue
        for e in load(p):
            sc = overlap(e, probe)
            if RELATED <= sc < SIMILAR:
                out.append({"key": e["key"], "how": e["how"], "score": round(sc, 2),
                            "scope": "machine" if p == machine else p.parent.name})
    return sorted(out, key=lambda r: -r["score"])[:3]


def all_repo_paths() -> list[Path]:
    """All repo-scope memory files on this computer."""
    base = base_dir() / "launch"
    if not base.is_dir():
        return []
    return sorted(p for p in base.glob(f"*/{FILE}") if p.parent.name != "_machine")


def _merge(into: dict, other: dict) -> None:
    """Combine records and keep the more recent method."""
    into["ok"] += other["ok"]
    into["fail"] += other["fail"]
    if other["last_seen"] > into["last_seen"]:
        into["how"], into["last_seen"] = other["how"], other["last_seen"]


def learn_smart(repo_path: Path | None, area: str, key: str, how: str, result: str,
                scope: str = "repo", today: str | None = None, detail: str | None = None) -> dict:
    """Default path for learn. Finds and merges similar entries; promotes to this computer if they span repos.

    Returns: learn() result + scope (scope actually written) + promoted_from (number of repo files merged).
    """
    machine = _machine_dir() / FILE
    probe = {"area": area, "key": norm_key(key), "how": " ".join((how or "").split())}
    # Already at this-computer scope: reinforce it there
    if any(similar(e, probe) for e in load(machine)):
        hit = next(e for e in load(machine) if similar(e, probe))
        r = learn(machine, area, hit["key"], how, result, today, detail)
        return {**r, "scope": "machine", "promoted_from": 0}
    if scope == "machine" or repo_path is None:
        return {**learn(machine, area, key, how, result, today, detail), "scope": "machine", "promoted_from": 0}
    # Same knowledge in another repo: promote to this-computer scope
    others = []
    for p in all_repo_paths():
        if p.resolve() == repo_path.resolve():
            continue
        hits = [e for e in load(p) if similar(e, probe)]
        if hits:
            others.append((p, hits))
    if not others:
        r = learn(repo_path, area, key, how, result, today, detail)
        return {**r, "scope": "repo", "promoted_from": 0,
                "related": related_entries(probe, exclude=repo_path) if "error" not in r else []}
    r = learn(machine, area, key, how, result, today, detail)
    if "error" in r:
        return r
    entries = load(machine)
    cur = next(e for e in entries if e["key"] == r["entry"]["key"] and e["area"] == area)
    moved = 0
    for p in others_and_self(others, repo_path, probe):
        keep = []
        for e in load(p):
            if similar(e, probe):
                _merge(cur, e)
                moved += 1
            else:
                keep.append(e)
        save(p, keep)
    save(machine, entries)
    return {"entry": cur, "total": len(entries), "scope": "machine", "promoted_from": moved}


def others_and_self(others, repo_path: Path, probe: dict) -> list[Path]:
    paths = [p for p, _ in others]
    if any(similar(e, probe) for e in load(repo_path)):
        paths.append(repo_path)
    return paths


def auto_record(area: str, key: str, how: str, today: str | None = None) -> dict | None:
    """Record a CLI-confirmed success at this-computer scope. Raised once per day only (avoids inflating the record)."""
    machine = _machine_dir() / FILE
    now = _today(today)
    k = norm_key(key)
    cur = next((e for e in load(machine) if e["key"] == k and e["area"] == area), None)
    if cur and cur["last_seen"] == now and cur["how"] == " ".join(how.split()):
        return None
    return learn(machine, area, key, how, "ok", today)


def tidy(today: str | None = None, junk_buckets: tuple = ("scripts", "pro-launch")) -> dict:
    """Tidy memories that are already scattered.

    - Entries in buckets wrongly named after skill folders (scripts, etc.) → this-computer scope
    - Similar entries spanning two or more repos → merged into this-computer scope, repo copies removed
    Only moves, never deletes.
    """
    machine = _machine_dir() / FILE
    m_entries = load(machine)
    files = {p: load(p) for p in all_repo_paths()}
    moved, merged = 0, 0

    def put(e: dict):
        nonlocal merged
        hit = next((x for x in m_entries if similar(x, e)), None)
        if hit:
            _merge(hit, e)
            merged += 1
        else:
            m_entries.append(dict(e))

    for p, entries in files.items():
        if p.parent.name in junk_buckets:
            for e in entries:
                put(e)
                moved += 1
            files[p] = []
    # Entries spanning several repos
    for p, entries in list(files.items()):
        keep = []
        for e in entries:
            spread = sum(1 for q, es in files.items() if q != p and any(similar(e, x) for x in es))
            in_machine = any(similar(e, x) for x in m_entries)
            if spread or in_machine:
                put(e)
                moved += 1
            else:
                keep.append(e)
        files[p] = keep
    for p, entries in files.items():
        save(p, entries)
    if m_entries:
        save(machine, m_entries)
    return {"moved_to_machine": moved, "merged": merged, "machine_total": len(m_entries)}


def surface(paths: dict[str, Path], area: str, seen_file: Path, limit: int = 3,
            today: str | None = None, key_prefix: str | None = None) -> list[dict]:
    """Memory to attach to a command response. Returned once per day per repo and area (saves tokens).

    With key_prefix, only keys starting with that prefix are included, and exposure is counted per prefix
    (so viewing server A does not hide server B's memory that day — `server.<name}.` is for this).

    Entries whose fail clearly outweighs ok are not included — wrong memories are not pushed every time.
    """
    now = _today(today)
    seen_key = f"{area}:{key_prefix}" if key_prefix else area
    # Mark as shown today at check time (computed once a day even when there is nothing to attach)
    if memory.seen_today(seen_file, seen_key, now):
        return []
    # Apply the prefix filter before capping — other servers' memories must not take the slots
    rows = [r for r in recall(paths, area, limit=1000, today=now)
            if r["fail"] < r["ok"] + HIDE_FAILS_OVER and not r.get("superseded_by")
            and (not key_prefix or r["key"].startswith(key_prefix))]
    out, kept = [], []
    for r in rows:
        if any(similar(r, k) for k in kept):
            continue
        kept.append(r)
        out.append({k: r[k] for k in ("key", "how", "scope", "ok", "fail", "verify", "detail_path") if k in r})
        if len(out) >= limit:
            break
    return out
