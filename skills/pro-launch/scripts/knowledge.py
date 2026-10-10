"""이 컴퓨터에서 실제로 먹힌 조작 방식을 기억한다 (컴퓨터별 학습 메모).

설계: docs/superpowers/specs/2026-10-10-agent-memory-design.md (#833)
 - 읽기는 agent 호출에 맡기지 않는다 — launch_cli 가 명령 응답에 `memory` 로 싣는다
 - 검증된 성공은 CLI 가 직접 기록한다 (auto_record). 실패·미설치는 자동 기록하지 않는다
 - 쓰기 전에 모든 레포·이 컴퓨터 범위에서 비슷한 항목을 찾아 합친다 (learn_smart)

  ~/.projectops/launch/<owner__repo>/knowledge.json   이 레포 + 이 컴퓨터
  ~/.projectops/launch/_machine/knowledge.json        이 컴퓨터 전체

**앱 화면·좌표는 여기 두지 않는다** — 그건 pro-agent-test 의 `note`(learned.json)가 맡는다.
여기는 '도구·방식'(iOS 는 Maestro, Google 로그인은 --headed 등)만 다룬다.

강화 = 카운터다. 성공을 알리면 ok+1, 실패하면 fail+1 이고, 꺼낼 때 (ok-fail) 순으로 준다.
토큰을 아끼려고 꺼내는 양(개수·글자 수)에 상한을 둔다.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
from pathlib import Path

from common.access import find_secrets
from common.state import base_dir, state_dir

FILE = "knowledge.json"
SCHEMA = 1
AREAS = ("ios", "android", "web", "server")
SCOPES = ("repo", "machine")
MAX_ENTRIES = 30        # 범위별 상한 — 넘으면 점수 낮은 것부터 지운다
MAX_HOW = 200           # 한 항목 글자 수 상한 (recall 한 번이 수백 토큰에 머물게)
MAX_KEY = 60
DEFAULT_LIMIT = 5
STALE_DAYS = 90

# 기억이 뒤집을 수 없는 금지 방법. 호스트 마우스를 움직여 화면 좌표를 누르는 것(#640).
# 저장도, 꺼내기도 막는다 — 손으로 고친 파일이나 옛 파일에서 들어와도 걸러야 한다.
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
    """못 읽으면 빈 메모로 계속한다 — 기억이 깨졌다고 작업이 멈추면 안 된다."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = data.get("entries") if isinstance(data, dict) else None
    out = []
    for r in rows or []:
        if isinstance(r, dict) and r.get("key") and r.get("how") and r.get("area") in AREAS:
            out.append({"key": str(r["key"]), "area": r["area"], "how": str(r["how"]),
                        "ok": int(r.get("ok") or 0), "fail": int(r.get("fail") or 0),
                        "last_seen": str(r.get("last_seen") or "")})
    return out


def save(path: Path, entries: list[dict]) -> None:
    """임시 파일에 쓰고 바꿔치기한다 — 여러 세션이 동시에 써도 반쯤 쓴 파일이 남지 않는다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps({"schema": SCHEMA, "entries": entries},
                              ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def norm_key(key: str) -> str:
    return re.sub(r"[^a-z0-9._-]+", "-", (key or "").strip().lower()).strip("-")[:MAX_KEY]


def _score(e: dict) -> int:
    return e["ok"] - e["fail"]


def _stale(e: dict, today: str) -> bool:
    try:
        d = dt.date.fromisoformat(e["last_seen"])
        return (dt.date.fromisoformat(today) - d).days > STALE_DAYS
    except ValueError:
        return True


def learn(path: Path, area: str, key: str, how: str, result: str,
          today: str | None = None) -> dict:
    """항목을 넣거나 갱신한다. 실패하면 {"error": 코드, "message": ...}."""
    if area not in AREAS:
        return {"error": "bad_area", "message": f"area 는 {'/'.join(AREAS)} 중 하나"}
    if result not in ("ok", "fail"):
        return {"error": "bad_result", "message": "result 는 ok 또는 fail"}
    k = norm_key(key)
    how = " ".join((how or "").split())
    if not k or not how:
        return {"error": "empty", "message": "key 와 how 가 비어 있다"}
    if FORBIDDEN.search(how):
        return {"error": "forbidden_method",
                "message": "호스트 마우스로 좌표를 누르는 방법은 기억하지 않는다 — 프로젝트 E2E 를 쓴다"}
    secrets = find_secrets(k + " " + how)
    if secrets:
        return {"error": "secret_detected",
                "message": "비밀값으로 보이는 것이 있어 저장하지 않았다: " + ", ".join(secrets)}
    how = how[:MAX_HOW]
    now = _today(today)
    entries = load(path)
    cur = next((e for e in entries if e["key"] == k and e["area"] == area), None)
    if cur is None:
        cur = {"key": k, "area": area, "how": how, "ok": 0, "fail": 0, "last_seen": now}
        entries.append(cur)
    elif cur["how"] != how:
        # 방법이 바뀌었으면 옛 방법의 성적을 물려받지 않는다
        cur.update(how=how, ok=0, fail=0)
    cur[result] += 1
    cur["last_seen"] = now
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


def recall(paths: dict[str, Path], area: str | None, limit: int = DEFAULT_LIMIT,
           today: str | None = None) -> list[dict]:
    """상위 항목만 돌려준다. 금지된 방법은 걸러내고, 믿기 어려운 것은 verify 로 표시한다."""
    now = _today(today)
    rows = []
    for scope, p in paths.items():
        for e in load(p):
            if area and e["area"] != area:
                continue
            if FORBIDDEN.search(e["how"]):
                continue
            stale = _stale(e, now)
            rows.append({**e, "scope": scope,
                         "verify": bool(e["fail"] and e["fail"] >= e["ok"]) or stale,
                         "_rank": (0 if stale else 1, _score(e), e["last_seen"])})
    rows.sort(key=lambda r: r["_rank"], reverse=True)
    for r in rows:
        del r["_rank"]
    return rows[:max(1, limit)]


# ── 중복 통합 · 범위 승격 · 노출 기록 (#833) ──────────────────────────────
#
# 같은 지식이 레포마다 키만 다르게 쌓였다(실측: ASC iframe 로그인 4곳). 레포에 상관없는
# 지식은 이 컴퓨터 범위(_machine) 한 곳에 있어야 다른 레포에서도 바로 쓰인다.

SIMILAR = 0.6            # 자동으로 합칠 만큼 확실한 겹침 (실측: 같은 지식도 문장이 달라 0.13~0.37)
RELATED = 0.25           # 이 이상이면 '비슷한 기억'으로 보여 주고 합칠지는 agent 가 판단한다
# 어느 지식에나 나오는 말 — 이것끼리 겹쳐서 같은 지식으로 오판했다(실측: Google 팝업 ↔ Apple iframe)
_GENERIC = {"web", "ios", "android", "server", "open", "goto", "type", "input", "click", "로그인",
            "입력", "통과", "있다", "있다.", "앞에", "폼은", "launch_cli", "--headed", "headed", "이메일",
            "비밀번호", "cdp", "app", "tap"}
HIDE_FAILS_OVER = 2      # fail >= ok + 이 값이면 자동으로 싣지 않는다
_WORD = re.compile(r"[0-9A-Za-z가-힣_.#-]{2,}")


def _words(text: str) -> set[str]:
    return {w.lower() for w in _WORD.findall(text or "")} - _GENERIC


def overlap(a: dict, b: dict) -> float:
    if a["area"] != b["area"]:
        return 0.0
    if a["key"] == b["key"]:
        return 1.0
    wa, wb = _words(a["how"]), _words(b["how"])
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / min(len(wa), len(wb))


def similar(a: dict, b: dict) -> bool:
    """자동으로 합쳐도 될 만큼 확실히 같은 지식인가 (같은 키, 또는 고유어가 60% 이상 겹침)."""
    return overlap(a, b) >= SIMILAR


def related_entries(probe: dict, exclude: Path | None = None) -> list[dict]:
    """애매하게 비슷한 기억 — 합칠지는 agent 가 판단한다 (Hermes 의 '추가 전에 먼저 찾아본다')."""
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
    """이 컴퓨터에 있는 모든 레포 범위 기억 파일."""
    base = base_dir() / "launch"
    if not base.is_dir():
        return []
    return sorted(p for p in base.glob(f"*/{FILE}") if p.parent.name != "_machine")


def _merge(into: dict, other: dict) -> None:
    """성적을 합치고 더 최근 것의 방법을 남긴다."""
    into["ok"] += other["ok"]
    into["fail"] += other["fail"]
    if other["last_seen"] > into["last_seen"]:
        into["how"], into["last_seen"] = other["how"], other["last_seen"]


def learn_smart(repo_path: Path | None, area: str, key: str, how: str, result: str,
                scope: str = "repo", today: str | None = None) -> dict:
    """learn 의 기본 경로. 비슷한 항목을 찾아 합치고, 여러 레포에 걸치면 이 컴퓨터로 올린다.

    돌려주는 값: learn() 결과 + scope(실제로 쓴 범위) + promoted_from(합친 레포 파일 수).
    """
    machine = _machine_dir() / FILE
    probe = {"area": area, "key": norm_key(key), "how": " ".join((how or "").split())}
    # 이미 이 컴퓨터 범위에 있으면 거기를 강화한다
    if any(similar(e, probe) for e in load(machine)):
        hit = next(e for e in load(machine) if similar(e, probe))
        r = learn(machine, area, hit["key"], how, result, today)
        return {**r, "scope": "machine", "promoted_from": 0}
    if scope == "machine" or repo_path is None:
        return {**learn(machine, area, key, how, result, today), "scope": "machine", "promoted_from": 0}
    # 다른 레포에 같은 지식이 있으면 이 컴퓨터 범위로 올린다
    others = []
    for p in all_repo_paths():
        if p.resolve() == repo_path.resolve():
            continue
        hits = [e for e in load(p) if similar(e, probe)]
        if hits:
            others.append((p, hits))
    if not others:
        r = learn(repo_path, area, key, how, result, today)
        return {**r, "scope": "repo", "promoted_from": 0,
                "related": related_entries(probe, exclude=repo_path) if "error" not in r else []}
    r = learn(machine, area, key, how, result, today)
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
    """CLI 가 확인한 성공을 이 컴퓨터 범위에 남긴다. 하루에 한 번만 올린다(성적 부풀리기 방지)."""
    machine = _machine_dir() / FILE
    now = _today(today)
    k = norm_key(key)
    cur = next((e for e in load(machine) if e["key"] == k and e["area"] == area), None)
    if cur and cur["last_seen"] == now and cur["how"] == " ".join(how.split()):
        return None
    return learn(machine, area, key, how, "ok", today)


def tidy(today: str | None = None, junk_buckets: tuple = ("scripts", "pro-launch")) -> dict:
    """이미 흩어진 기억을 정리한다.

    - 스킬 폴더 이름으로 잘못 생긴 버킷(scripts 등)의 항목 → 이 컴퓨터 범위
    - 두 개 이상 레포에 걸친 비슷한 항목 → 이 컴퓨터 범위로 합치고 레포 사본 제거
    지우지 않고 옮기기만 한다.
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
    # 여러 레포에 걸친 것
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
            today: str | None = None) -> list[dict]:
    """명령 응답에 실을 기억. 레포·영역마다 하루 한 번만 돌려준다 (토큰 절약).

    fail 이 ok 보다 크게 앞서는 것은 싣지 않는다 — 틀린 기억을 매번 들이밀지 않는다.
    """
    now = _today(today)
    try:
        seen = json.loads(seen_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        seen = {}
    if seen.get(area) == now:
        return []
    rows = [r for r in recall(paths, area, limit=limit * 3, today=now)
            if r["fail"] < r["ok"] + HIDE_FAILS_OVER]
    out, kept = [], []
    for r in rows:
        if any(similar(r, k) for k in kept):
            continue
        kept.append(r)
        out.append({k: r[k] for k in ("key", "how", "scope", "ok", "fail", "verify")})
        if len(out) >= limit:
            break
    seen[area] = now
    try:
        seen_file.parent.mkdir(parents=True, exist_ok=True)
        seen_file.write_text(json.dumps(seen), encoding="utf-8")
    except OSError:
        pass
    return out
