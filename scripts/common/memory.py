"""Shared skill memory logic: similarity, track record, staleness, exposure cap (#833 · #837).

pro-launch knowledge (tools, methods) and pro-agent-test notes (app screens, pitfalls) follow the same rules.
Principles: skills/references/memory-principles.md

 - Before writing, look for similar memories. Merge only sure matches (same key, 60%+ distinct words);
   show ambiguous ones (25~60%) as related and let the agent decide.
 - Success ok+1, failure fail+1. The same result on the same day counts once (no inflation).
 - Old (90 days) or failure-leading entries are not deleted; they are marked verify and pushed back.
 - Memories go into a response once per day per area; adding them every time burns tokens nobody reads.

Standard library only (mac, Windows, air-gapped networks).
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

SIMILAR = 0.6            # Overlap sure enough to merge automatically (measured: same knowledge in different sentences scores 0.13~0.37)
RELATED = 0.25           # At or above this, show as 'similar memory' and let the agent decide whether to merge
STALE_DAYS = 90
HIDE_FAILS_OVER = 2      # Not loaded automatically when fail >= ok + this value

# English function words: CLI output is English, so 'did not' alone matched unrelated troubleshooting entries.
# Error words (failed, timeout, out, start, etc.) are not listed; they are real match evidence
_ENGLISH_STOPWORDS = {"a", "an", "the", "is", "are", "was", "were", "be", "been", "to", "of", "in",
                      "on", "at", "by", "for", "from", "with", "and", "or", "not", "no", "did", "does",
                      "do", "can", "could", "this", "that", "it", "me"}
# Words found in any knowledge; overlaps on these misjudged entries as the same (measured: Google popup <-> Apple iframe)
_GENERIC = {"web", "ios", "android", "server", "open", "goto", "type", "input", "click", "로그인",
            "입력", "통과", "있다", "있다.", "앞에", "폼은", "launch_cli", "--headed", "headed", "이메일",
            "비밀번호", "cdp", "app", "tap"} | _ENGLISH_STOPWORDS
_WORD = re.compile(r"[0-9A-Za-z가-힣_.#-]{2,}")


def today(value: str | None = None) -> str:
    return value or dt.date.today().isoformat()


def words(text: str) -> set[str]:
    """Distinct words used for comparison. Common words (_GENERIC) are dropped."""
    return {w.lower() for w in _WORD.findall(text or "")} - _GENERIC


def overlap(a: dict, b: dict, field: str = "how", group: str = "area", key: str = "key",
            min_words: int = 1) -> float:
    """How much two memories are the same knowledge (0~1).

    If both have a group (area) and they differ: 0; if both have a key and it matches: 1.
    Otherwise distinct-word overlap / word count of the shorter one; a short sentence contained in a long one counts as the same.
    min_words: 0 if the shorter one has fewer distinct words than this; stops sentences that leave a single word
    (like 'first', 'second') from merging at 1.0 (for keyless note entries).
    """
    ga, gb = a.get(group), b.get(group)
    if ga is not None and gb is not None and ga != gb:
        return 0.0
    ka, kb = a.get(key), b.get(key)
    if ka and kb and ka == kb:
        return 1.0
    wa, wb = words(str(a.get(field) or "")), words(str(b.get(field) or ""))
    if not wa or not wb or min(len(wa), len(wb)) < min_words:
        return 0.0
    return len(wa & wb) / min(len(wa), len(wb))


def similar(a: dict, b: dict, **kw) -> bool:
    """Whether it is surely the same knowledge, safe to merge automatically."""
    return overlap(a, b, **kw) >= SIMILAR


def find_similar(probe: dict, entries: list[dict], **kw) -> tuple[int | None, list[tuple[int, float]]]:
    """(index of the entry to merge or None, top 3 ambiguous similar [(index, score)]).

    The entry to merge is the single highest score. Ambiguous ones are only returned for the agent to judge.
    """
    best, best_sc, rel = None, 0.0, []
    for i, e in enumerate(entries):
        if not isinstance(e, dict):
            continue
        sc = overlap(e, probe, **kw)
        if sc >= SIMILAR and sc > best_sc:
            best, best_sc = i, sc
        elif RELATED <= sc < SIMILAR:
            rel.append((i, round(sc, 2)))
    rel.sort(key=lambda r: -r[1])
    return best, rel[:3]


# ── Track record · staleness ────────────────────────────────────────────

def stats(e: dict) -> tuple[int, int, str]:
    """(ok, fail, last_seen). Old entries (no record) read as 0, 0, date added; the file is not modified."""
    def num(v):
        try:
            return int(v or 0)
        except (TypeError, ValueError):
            return 0
    last = str(e.get("last_seen") or e.get("updated") or e.get("added") or "")
    return num(e.get("ok")), num(e.get("fail")), last


def stale(last_seen: str, now: str | None = None, days: int = STALE_DAYS) -> bool:
    try:
        d = dt.date.fromisoformat(last_seen)
        return (dt.date.fromisoformat(today(now)) - d).days > days
    except (TypeError, ValueError):
        return True


def needs_verify(e: dict, now: str | None = None) -> bool:
    """Whether to re-verify before use: failures lead (ties included), it is old, or it is marked."""
    ok, fail, last = stats(e)
    return bool(e.get("verify")) or bool(fail and fail >= ok) or stale(last, now)


def hidden(e: dict) -> bool:
    """Memories where failures lead by a wide margin are not loaded automatically."""
    ok, fail, _ = stats(e)
    return fail >= ok + HIDE_FAILS_OVER


def rank(e: dict, now: str | None = None) -> tuple:
    """Sort key (larger first). Trusted > score > most recent."""
    ok, fail, last = stats(e)
    return (0 if needs_verify(e, now) else 1, ok - fail, last)


def bump(e: dict, result: str, now: str | None = None) -> bool:
    """Bump the record. The same result on the same day counts once. True if bumped.

    The verify mark is cleared when successes lead failures; the memory has been re-confirmed.
    """
    if result not in ("ok", "fail"):
        raise ValueError("result must be ok or fail")
    d = today(now)
    ok, fail, _ = stats(e)
    e["ok"], e["fail"] = ok, fail
    counted = not (e.get("last_seen") == d and e.get("last_result") == result)
    if counted:
        e[result] += 1
    e["last_seen"], e["last_result"] = d, result
    if e.get("verify") and e["ok"] > e["fail"]:
        e.pop("verify", None)
    return counted


def clip(text: str, n: int) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[: n - 1] + "…"


# ── Exposure cap ────────────────────────────────────────────────────────

def seen_today(seen_file: Path, slot: str, now: str | None = None, mark: bool = True) -> bool:
    """Whether memories were already loaded today for this slot (area, etc.). With mark, record it as loaded now.

    Never raises if the file cannot be read or written; memory is auxiliary.
    """
    d = today(now)
    try:
        seen = json.loads(seen_file.read_text(encoding="utf-8"))
        if not isinstance(seen, dict):
            seen = {}
    except (OSError, json.JSONDecodeError):
        seen = {}
    if seen.get(slot) == d:
        return True
    if mark:
        seen[slot] = d
        try:
            seen_file.parent.mkdir(parents=True, exist_ok=True)
            seen_file.write_text(json.dumps(seen, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
    return False
