"""기억 요약·응답 싣기: 순위, 화면 요약, 하루 한 번 싣기, 쓰기 전 비슷한 항목 찾기"""
from __future__ import annotations

from pathlib import Path

from common import memory as _memory
from common.state import base_dir as _base_dir

from pro_agent_test.notes.store import _load_notes, _locator, _machine_note_path, _note_path, _read_notes
from pro_agent_test.storage import _NOTE_MIN_WORDS, _SEEN_FILE, _SHOW_CHARS, _SURFACE_CHARS, _home_dir


# ── 항목 요약 · 응답에 싣기 ─────────────────────────────────────────────

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
    """화면 대상은 성적이 생긴 뒤에만 낡음을 따진다 — 갓 적은 대상을 '오래됨'으로 보지 않는다."""
    if t.get("verify"):
        return True
    return ("ok" in t or "fail" in t) and _memory.needs_verify(t, now)


def _screen_view(entry: dict, full: bool) -> dict:
    """화면 기록. 요약에서는 누를 대상만 보여 준다 — 원본 픽셀은 --all 에서만."""
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


# 타겟별로 맥락에 더하는 말 — 함정 문장과 겹칠 만한 것
_TARGET_WORDS = {
    "app": "앱 화면 에뮬레이터 기기 adb 스크롤 좌표 Flutter",
    "web": "웹 브라우저 페이지 화면 viewport",
    "server": "서버 API DB 로그 요청 응답 토큰",
    "other": "명령 실행 파일 출력",
}


def _surface(root: Path, slot: str, context: str, now: str | None = None) -> dict | None:
    """응답에 실을 기억 — 제약 2 · 함정 2 · 이 컴퓨터 범위 함정 1 까지.

    agent 가 `note show` 를 부르지 않아도 보이게 한다(원칙 1). slot(영역)마다 하루 한 번만
    싣는다 — 매번 실으면 토큰만 쓰고 아무도 읽지 않는다. 실패가 크게 앞서는 것은 싣지 않는다.
    """
    # HOME 이 상대 경로면 작업 폴더 아래에 기록이 생긴다 — 쓰지 않는다
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
    # 이 컴퓨터 범위는 맥락과 겹칠 때만 — 모든 레포에 모든 플랫폼 함정을 들이밀지 않는다
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


# ── 쓰기 전에 비슷한 것 찾기 ────────────────────────────────────────────

def _find_dup(text: str, lists: dict[str, list]) -> tuple[tuple[str, int] | None, list[dict]]:
    """(합칠 자리 (범위, 위치) 또는 None, 애매하게 비슷한 것들). 범위 순서대로 먼저 찾은 것이 이긴다."""
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
    """새 항목. 겪어서 적는 것이므로 한 번 확인된 것(ok=1)으로 시작한다."""
    e = {"text": text, **{k: v for k, v in extra.items() if v is not None}, "added": today}
    _memory.bump(e, "ok", today)
    return e
