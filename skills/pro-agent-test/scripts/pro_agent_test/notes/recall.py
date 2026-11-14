"""Memory summary and surfacing: ranking, screen summary, once-a-day surfacing, finding similar entries before writing"""
from __future__ import annotations

from pathlib import Path

from common import memory as _memory
from common.state import base_dir as _base_dir

from pro_agent_test.notes.store import _load_notes, _locator, _machine_note_path, _note_path, _read_notes
from pro_agent_test.storage import _NOTE_MIN_WORDS, _SEEN_FILE, _SHOW_CHARS, _SURFACE_CHARS, _home_dir


# ── Entry summary · surfacing in responses ─────────────────────────────────────────────

def _brief(i: int, e: dict, chars: int, now: str | None = None, scope: str | None = None) -> dict:
    ok, fail, last = _memory.stats(e)
    row = {"index": i, "text": _memory.clip(e.get("text"), chars)}
    if e.get("check"):
        row["check"] = _memory.clip(e["check"], chars)
    if scope:
        row["scope"] = scope
    if ok or fail:
        row["ok"], row["fail"] = ok, fail
    if _memory.needs_verify(e, now):
        row["verify"] = True
    return row


def _ranked(entries: list, now: str | None = None) -> list[tuple[int, dict]]:
    rows = [(i, e) for i, e in enumerate(entries) if isinstance(e, dict) and e.get("text")]
    rows.sort(key=lambda r: _memory.rank(r[1], now), reverse=True)
    return rows


def _target_verify(t: dict, now: str | None = None) -> bool:
    """Screen targets are judged stale only after they have a score — a freshly recorded target is not 'old'."""
    if t.get("verify"):
        return True
    return ("ok" in t or "fail" in t) and _memory.needs_verify(t, now)


def _screen_view(entry: dict, full: bool) -> dict:
    """Screen record. The summary shows only targets to press — raw pixels only with --all."""
    if full:
        return entry
    out = {"anchor": entry.get("anchor"), "variants": {}}
    for k, v in (entry.get("variants") or {}).items():
        if not isinstance(v, dict):
            continue
        tg = {}
        for label, t in (v.get("targets") or {}).items():
            if not isinstance(t, dict):
                continue
            tg[label] = _locator(t)
            if _target_verify(t):
                tg[label]["verify"] = True
        row = {"targets": tg}
        for kk in ("measured_on", "build", "unconverted"):
            if v.get(kk):
                row[kk] = v[kk]
        out["variants"][k] = row
    return out


# Words added to the context per target — likely to overlap with pitfall sentences
_TARGET_WORDS = {
    "app": "앱 화면 에뮬레이터 기기 adb 스크롤 좌표 Flutter",
    "web": "웹 브라우저 페이지 화면 viewport",
    "server": "서버 API DB 로그 요청 응답 토큰",
    "other": "명령 실행 파일 출력",
}


def _surface(root: Path, slot: str, context: str, now: str | None = None) -> dict | None:
    """Memory to include in responses — up to 2 constraints · 2 pitfalls · 1 machine-scope pitfall.

    Visible even if the agent never calls `note show` (principle 1). Included once a day per slot (area)
    — including it every time only burns tokens and nobody reads it. Entries with far more failures are skipped.
    """
    # A relative HOME would create records under the working folder — do not write
    if not _base_dir().is_absolute():
        return None
    seen_file = _home_dir(root) / _SEEN_FILE
    if _memory.seen_today(seen_file, slot, now, mark=False):
        return None
    if not _note_path(root).exists() and not _machine_note_path().exists():
        return None
    notes, _ = _load_notes(root)
    machine, _ = _read_notes(_machine_note_path())
    ctx = _memory.words(context)

    def pick(entries: list, n: int, scope: str | None = None, need_ctx: bool = False) -> list:
        rows = []
        for i, e in _ranked(entries, now):
            if _memory.hidden(e):
                continue
            rel = len(_memory.words(f"{e.get('text', '')} {e.get('check') or ''}") & ctx)
            if need_ctx and not rel:
                continue
            rows.append((rel, _memory.rank(e, now), i, e))
        rows.sort(key=lambda r: (r[0], r[1]), reverse=True)
        out, kept = [], []
        for _, _, i, e in rows:
            if any(_memory.similar(e, k, field="text", min_words=_NOTE_MIN_WORDS) for k in kept):
                continue
            kept.append(e)
            out.append(_brief(i, e, _SURFACE_CHARS, now, scope))
            if len(out) >= n:
                break
        return out

    constraints = pick(notes.get("constraints") or [], 2)
    pitfalls = pick(notes.get("pitfalls") or [], 2)
    # Machine scope only when it overlaps the context — do not push every platform pitfall onto every repo
    pitfalls += pick(machine.get("pitfalls") or [], 1, scope="machine", need_ctx=True)
    if not (constraints or pitfalls):
        return None
    _memory.seen_today(seen_file, slot, now, mark=True)
    out = {}
    if constraints:
        out["constraints"] = constraints
    if pitfalls:
        out["pitfalls"] = pitfalls
    out["note"] = ("Some rules and pitfalls learned about this app (once a day). All of them: note show --all. "
                   "If you re-checked one, record it with note pitfall|constraint --index N --result ok|fail")
    return out


# ── Find similar entries before writing ────────────────────────────────────────────

def _find_dup(text: str, lists: dict[str, list]) -> tuple[tuple[str, int] | None, list[dict]]:
    """(merge slot (scope, position) or None, loosely similar entries). In scope order, the first found wins."""
    probe = {"text": text}
    hit, related = None, []
    for scope, entries in lists.items():
        best, rel = _memory.find_similar(probe, entries, field="text", min_words=_NOTE_MIN_WORDS)
        if best is not None and hit is None:
            hit = (scope, best)
        for i, sc in rel:
            related.append({"scope": scope, "index": i, "score": sc,
                            "text": _memory.clip(entries[i].get("text"), _SHOW_CHARS)})
    related.sort(key=lambda r: -r["score"])
    return hit, related[:3]


def _new_entry(text: str, today: str, **extra) -> dict:
    """New entry. Recorded from experience, so it starts as confirmed once (ok=1)."""
    e = {"text": text, **{k: v for k, v in extra.items() if v is not None}, "added": today}
    _memory.bump(e, "ok", today)
    return e
