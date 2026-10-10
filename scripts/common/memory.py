"""스킬 기억 공통 로직 — 유사도 · 성적 · 낡음 · 노출 상한 (#833 · #837).

pro-launch knowledge(도구·방식)와 pro-agent-test note(앱 화면·함정)가 같은 규칙을 쓴다.
원칙: skills/references/memory-principles.md

 - 쓰기 전에 비슷한 기억을 찾는다. 확실한 것(같은 키, 고유어 60% 이상)만 합치고,
   애매한 것(25~60%)은 related 로 보여 주고 agent 가 판단한다.
 - 성공 ok+1, 실패 fail+1. 같은 날 같은 결과는 한 번만 센다(부풀리기 방지).
 - 오래됐거나(90일) 실패가 앞서면 지우지 않고 verify 로 표시해 뒤로 민다.
 - 응답에 싣는 기억은 하루·영역당 한 번만 — 매번 실으면 토큰만 쓰고 아무도 안 읽는다.

표준 라이브러리만 쓴다 (mac·Windows·폐쇄망 공통).
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

SIMILAR = 0.6            # 자동으로 합칠 만큼 확실한 겹침 (실측: 같은 지식도 문장이 달라 0.13~0.37)
RELATED = 0.25           # 이 이상이면 '비슷한 기억'으로 보여 주고 합칠지는 agent 가 판단한다
STALE_DAYS = 90
HIDE_FAILS_OVER = 2      # fail >= ok + 이 값이면 자동으로 싣지 않는다

# 어느 지식에나 나오는 말 — 이것끼리 겹쳐서 같은 지식으로 오판했다(실측: Google 팝업 ↔ Apple iframe)
_GENERIC = {"web", "ios", "android", "server", "open", "goto", "type", "input", "click", "로그인",
            "입력", "통과", "있다", "있다.", "앞에", "폼은", "launch_cli", "--headed", "headed", "이메일",
            "비밀번호", "cdp", "app", "tap"}
_WORD = re.compile(r"[0-9A-Za-z가-힣_.#-]{2,}")


def today(value: str | None = None) -> str:
    return value or dt.date.today().isoformat()


def words(text: str) -> set[str]:
    """비교에 쓰는 고유어 집합. 흔한 말(_GENERIC)은 뺀다."""
    return {w.lower() for w in _WORD.findall(text or "")} - _GENERIC


def overlap(a: dict, b: dict, field: str = "how", group: str = "area", key: str = "key",
            min_words: int = 1) -> float:
    """두 기억이 얼마나 같은 지식인가 (0~1).

    group 값(영역)이 둘 다 있고 다르면 0, key 가 둘 다 있고 같으면 1.
    나머지는 고유어 겹침 / 짧은 쪽 단어 수 — 짧은 문장이 긴 문장에 담기면 같은 지식으로 본다.
    min_words: 짧은 쪽 고유어가 이보다 적으면 0 — '첫 번째'·'두 번째' 처럼 한 단어만 남는
    문장이 1.0 으로 합쳐지는 것을 막는다 (키가 없는 note 항목용).
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
    """자동으로 합쳐도 될 만큼 확실히 같은 지식인가."""
    return overlap(a, b, **kw) >= SIMILAR


def find_similar(probe: dict, entries: list[dict], **kw) -> tuple[int | None, list[tuple[int, float]]]:
    """(합칠 항목 위치 또는 None, 애매하게 비슷한 [(위치, 점수)] 상위 3).

    합칠 항목은 가장 높은 점수 하나다. 애매한 것은 agent 가 판단하도록 돌려주기만 한다.
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


# ── 성적 · 낡음 ─────────────────────────────────────────────────────────

def stats(e: dict) -> tuple[int, int, str]:
    """(ok, fail, last_seen). 옛 항목(성적 없음)은 0·0·추가한 날로 읽는다 — 파일은 고치지 않는다."""
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
    """다시 확인하고 써야 하는가 — 실패가 앞서거나(동률 포함) 오래됐거나, 표시가 붙었거나."""
    ok, fail, last = stats(e)
    return bool(e.get("verify")) or bool(fail and fail >= ok) or stale(last, now)


def hidden(e: dict) -> bool:
    """틀린 것이 크게 앞서는 기억은 자동으로 싣지 않는다."""
    ok, fail, _ = stats(e)
    return fail >= ok + HIDE_FAILS_OVER


def rank(e: dict, now: str | None = None) -> tuple:
    """정렬 키 (큰 것이 앞). 믿을 만한 것 → 점수 → 최근 순."""
    ok, fail, last = stats(e)
    return (0 if needs_verify(e, now) else 1, ok - fail, last)


def bump(e: dict, result: str, now: str | None = None) -> bool:
    """성적을 올린다. 같은 날 같은 결과는 한 번만 센다. 올렸으면 True.

    verify 표시는 성공이 실패를 앞서면 내린다 — 다시 확인된 기억이다.
    """
    if result not in ("ok", "fail"):
        raise ValueError("result 는 ok 또는 fail")
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


# ── 노출 상한 ───────────────────────────────────────────────────────────

def seen_today(seen_file: Path, slot: str, now: str | None = None, mark: bool = True) -> bool:
    """이 slot(영역 등)에 오늘 이미 기억을 실었는가. mark 면 지금 실은 것으로 적는다.

    파일을 못 읽거나 못 써도 예외를 내지 않는다 — 기억은 보조다.
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
