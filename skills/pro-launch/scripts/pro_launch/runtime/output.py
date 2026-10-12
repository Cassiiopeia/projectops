"""모든 명령이 결과를 내는 한 곳 — `out()` 이 결과에 공통 후처리를 덧붙인다."""
from __future__ import annotations

import json
import time
from pathlib import Path

from common.access import needs_verify, record_result
from common.emit import emit
from common.state import repo_unknown

import knowledge

from pro_launch.runtime.context import ACCESS_CTX, MEMORY_CTX, MIGRATION, ROOT_CTX


def out(payload: dict) -> int:
    """emit 에 이전 결과를 덧붙인다. 옮긴 것이 있으면 사용자가 알아야 한다."""
    moved = [m for r in MIGRATION.values() for m in r.get("moved", [])]
    warns = [w for r in MIGRATION.values() for w in r.get("warnings", [])]
    if moved:
        payload["migrated"] = moved
    if warns:
        payload["migration_warnings"] = warns
    # summary 는 언제나 문자열이다 (#825) — None 이 섞이면 부르는 쪽 파싱이 깨진다(실측).
    if not payload.get("summary"):
        act = payload.get("action")
        payload["summary"] = payload.get("error") or (f"{act} 완료" if act else "완료")
    _root_warning(payload)
    _grade_access(payload)
    _memory_hooks(payload)
    return emit(payload)


def _root_warning(payload: dict) -> None:
    if not ROOT_CTX.get("unknown"):
        return
    payload["root_unknown"] = True
    payload["root_warning"] = (f"프로젝트를 알 수 없는 폴더({ROOT_CTX.get('path')})에서 불렸다 — "
                               "상태는 이 컴퓨터 공용 자리에 쓰고, 레포 기억은 쓰지 않는다")
    fix = "--root <프로젝트 경로> 를 붙여 다시 부른다 (또는 PROJECT_ROOT 환경변수)"
    nxt = payload.get("next")
    if not nxt:
        payload["next"] = fix
    elif isinstance(nxt, str) and fix not in nxt:
        payload["next"] = f"{fix}. 그 다음: {nxt}"


_ACCESS_FAIL_CODES = {"db_query_failed", "db_timeout", "logs_failed", "logs_timeout",
                      "request_failed"}


# http 는 응답만 받으면 붙는 법은 맞다 — 기대 상태코드가 다른 것은 시나리오 판정이다
_ACCESS_OK_CODES = {"ok", "unexpected_status"}


def use_access(root: Path, key: str) -> None:
    """이번 명령이 access 의 key 로 적힌 방법을 쓴다고 표시한다. out() 이 결과를 기록한다."""
    ACCESS_CTX.update(root=root, key=key)


def _grade_access(payload: dict) -> None:
    key = ACCESS_CTX.pop("key", None)
    root = ACCESS_CTX.pop("root", None)
    if not key or root is None:
        return
    code = payload.get("code")
    ok = payload.get("ok", True) is not False and code in (None, *_ACCESS_OK_CODES)
    if not ok and code not in _ACCESS_FAIL_CODES:
        return
    try:
        prev = record_result(root, key, ok, code)
    except Exception:   # noqa: BLE001 — 성적은 보조다
        return
    if needs_verify(prev):
        lf = prev.get("last_fail") or {}
        payload["verify"] = True
        payload["verify_note"] = (f"access '{key}' 는 지난번({lf.get('date')}, {lf.get('code')}) 실패했던 방법이다 — "
                                  + ("이번에는 먹혔다" if ok else
                                     "이번에도 실패했다. 코드를 다시 읽어 access set 으로 고친다"))


_FIX_WINDOW_SEC = 30 * 60   # 실패 뒤 이 안에 같은 영역이 성공하면 '새로 알게 된 방식'일 수 있다


def set_area(area: str | None, root: Path | None = None, key_prefix: str | None = None) -> None:
    """key_prefix: 이 접두사의 기억만 싣는다 (예: 서버 이름별 `server.<이름>.`)."""
    if area in knowledge.AREAS:
        MEMORY_CTX.update(area=area, root=root or MEMORY_CTX.get("root") or Path(".").resolve(),
                           key_prefix=key_prefix)


def _memory_hooks(payload: dict) -> None:
    """기억 싣기 · 실패 뒤 성공이면 learn_hint. 어떤 오류도 명령 결과를 망치지 않는다."""
    area = MEMORY_CTX.get("area")
    # HOME 이 상대 경로면 작업 폴더 아래에 기록이 생긴다 — 쓰지 않는다 (테스트가 실제로 그렇게 만들었다)
    if not area or not knowledge.base_dir().is_absolute():
        return
    try:
        root = MEMORY_CTX["root"]
        unknown = repo_unknown(root)
        paths = {"machine": knowledge.store_path("machine", root)}
        if not unknown:
            paths["repo"] = knowledge.store_path("repo", root)
        seen_dir = knowledge.store_path("machine" if unknown else "repo", root).parent
        mem = knowledge.surface(paths, area, seen_dir / "memory_seen.json",
                                key_prefix=MEMORY_CTX.get("key_prefix"))
        if mem:
            payload["memory"] = mem
            payload["memory_note"] = ("이 컴퓨터에서 먹혔던 방식이다. 쓴 것이 있으면 결과를 "
                                      f"learn --area {area} --key <key> --how <how> --result ok|fail 로 남긴다")
        hint = _track_attempt(seen_dir / "attempts.json", area, payload)
        if hint:
            payload["learn_hint"] = hint
    except Exception:   # noqa: BLE001 — 기억은 보조다. 실패해도 본 명령 결과는 그대로 낸다
        pass


def _track_attempt(f: Path, area: str, payload: dict) -> str | None:
    """같은 영역에서 실패한 뒤 성공하면 '새로 알게 된 방식이면 기록하라'고 알려 준다.

    agent 가 기억을 남길 가장 좋은 순간은 막혔다 풀린 직후다. 그 순간을 도구가 짚어 준다.
    """
    ok = payload.get("ok", True) is not False and payload.get("code") in (None, "ok")
    try:
        last = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        last = {}
    now = time.time()
    prev = last.get(area) or {}
    if ok:
        last.pop(area, None)
    else:
        last[area] = {"code": payload.get("code"), "at": now}
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(last), encoding="utf-8")
    except OSError:
        pass
    if ok and prev and now - prev.get("at", 0) < _FIX_WINDOW_SEC:
        return (f"방금 '{prev.get('code')}' 실패를 다른 방식으로 넘겼다. 다음에도 쓸 방식이면 "
                f"learn --area {area} --key <짧은키> --how '<무엇을 어떻게>' --result ok 로 남긴다 "
                "(미설치·일회성·비밀값은 남기지 않는다)")
    return None
