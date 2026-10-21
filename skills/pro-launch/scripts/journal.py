"""했던 작업을 자유롭게 적어 두고, 다음에 같은 곳으로 돌아오면 다시 읽히게 한다 (작업 일지).

`knowledge`(learn) 가 '이 방식이 먹혔다'는 한 줄 결론을 받는다면, 여기는 **작업 한 건의 맥락**을 받는다.
무엇을 왜 했고 어떤 순서였고 결과가 어땠는지, 다음에 헷갈릴 점이 무엇인지 — 형식은 정하지 않는다.
쓸지 말지, 무엇을 적을지는 agent 가 사용자와 정한다. 도구는 저장하고 다시 꺼내 줄 뿐이다.

  ~/.projectops/launch/<owner__repo>/journal.jsonl

읽기는 agent 호출에 맡기지 않는다 — 같은 영역을 다시 열면 launch_cli 가 응답에 `journal` 로 싣는다.
적힌 것은 **참고**일 뿐 자동 실행하지 않는다. 변경 작업은 사용자 확인을 거친다.
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
MAX_TEXT = 1500      # 한 건 글자 수 상한 — 읽을 때 토큰이 한 번에 쏟아지지 않게
MAX_TITLE = 80
MAX_ENTRIES = 40     # 넘으면 오래된 것부터 지운다
SURFACE_LIMIT = 2    # 응답에 싣는 최근 건수
SURFACE_CHARS = 400  # 응답에 실을 때 한 건당 글자 수


def store_path(root: Path) -> Path:
    return state_dir("launch", root) / FILE


def load(path: Path) -> list[dict]:
    """못 읽으면 빈 일지로 계속한다 — 일지가 깨졌다고 작업이 멈추면 안 된다."""
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
    """임시 파일에 쓰고 바꿔치기한다 — 여러 세션이 동시에 써도 반쯤 쓴 파일이 남지 않는다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    os.replace(tmp, path)


def add(path: Path, text: str, title: str = "", area: str = "", site: str = "",
        now: str | None = None) -> dict:
    """일지에 한 건을 더한다. 실패하면 {"error": 코드, "message": ...}."""
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
    """최근 것부터. site 는 부분 일치다 (주소 일부로 찾는다)."""
    rows = load(path)
    if area:
        rows = [r for r in rows if r["area"] == area or not r["area"]]
    if site:
        rows = [r for r in rows if site.lower() in (r["site"] + " " + r["title"]).lower()]
    return list(reversed(rows))[:limit]


def forget(path: Path, title: str) -> int:
    """제목이 정확히 같은 항목을 지운다."""
    rows = load(path)
    keep = [r for r in rows if r["title"] != title]
    if len(keep) != len(rows):
        _save(path, keep)
    return len(rows) - len(keep)


def surface(path: Path, area: str, seen_file: Path, limit: int = SURFACE_LIMIT,
            today: str | None = None) -> list[dict]:
    """명령 응답에 실을 최근 일지. 레포·영역마다 하루 한 번만 돌려준다 (토큰 절약)."""
    now = today or dt.date.today().isoformat()
    if memory.seen_today(seen_file, area, now, mark=False):
        return []
    rows = recent(path, limit, area=area)
    if not rows:
        # 보여 준 것이 없으면 '오늘 보여 줌'으로 치지 않는다 — 같은 날 나중에 적은 기록이 가려진다
        return []
    memory.seen_today(seen_file, area, now)
    out = []
    for r in rows:
        t = r["text"] if len(r["text"]) <= SURFACE_CHARS else r["text"][:SURFACE_CHARS] + " …"
        out.append({"at": r["at"], "title": r["title"], "site": r["site"], "text": t})
    return out
