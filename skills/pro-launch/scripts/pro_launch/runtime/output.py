"""모든 명령이 결과를 내는 한 곳 — `out()` 이 결과에 공통 후처리를 덧붙인다."""
from __future__ import annotations

import json
import time
from pathlib import Path

from common import troubleshoot
from common.access import needs_verify, record_result
from common.emit import emit
from common.state import repo_unknown

import journal
import knowledge

from pro_launch.runtime.context import ACCESS_CTX, MEMORY_CTX, MIGRATION, OUTPUT_CTX, ROOT_CTX

# skills/pro-launch — 공식 트러블슈팅(troubleshooting/)이 있는 곳
SKILL_DIR = Path(__file__).resolve().parents[3]


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
    attach_known_fix(payload)
    _memory_hooks(payload)
    return emit_shaped(payload)


# 맨 앞 4필드 — 잘라 읽어도 다음 행동이 남게 언제나 먼저 · 언제나 남긴다
HEAD_KEYS = ("ok", "code", "summary", "next")
# 실패 원인 한 줄 (render 의 묻힌 첫 오류 등) — 머리 바로 뒤 · --brief 에도 남긴다
CAUSE_KEYS = ("first_error",)
# 이 실패·영역에 맞춘 해결과 기억 — 원인 뒤 · 줄여도 남긴다
GUIDANCE_KEYS = ("known_fix", "known_fix_note", "memory", "memory_note", "learn_hint")
# --brief 가 남기는 키: 머리 + error + 원인 + 안내
BRIEF_KEYS = (*HEAD_KEYS, "error", *CAUSE_KEYS, *GUIDANCE_KEYS)


def shape_payload(payload: dict) -> dict:
    """출력 모양 정리: 4필드 기본값 > 순서(머리 > 원인 > 안내 > 나머지) > --brief · --fields 거르기.

    값은 바꾸지 않는다. 플래그가 없으면 키 집합은 그대로이고 순서만 바뀐다.
    """
    # 기본값 (emit 과 같은 규칙) — emit 이 뒤에 붙이면 순서가 다시 어긋난다
    payload.setdefault("ok", True)
    payload.setdefault("code", "ok" if payload["ok"] else "error")
    payload.setdefault("summary", None)
    payload.setdefault("next", None)
    leading = [k for k in (*HEAD_KEYS, *CAUSE_KEYS, *GUIDANCE_KEYS) if k in payload]
    ordered = {k: payload[k] for k in leading}
    ordered.update((k, v) for k, v in payload.items() if k not in ordered)
    kept_names = _kept_key_names()
    if kept_names is None:
        return ordered
    return {k: v for k, v in ordered.items() if k in kept_names}


def _kept_key_names() -> set[str] | None:
    """--brief · --fields 로 남길 키 이름. 둘 다 없으면 None (전부 남김), 둘 다면 합집합."""
    is_brief = bool(OUTPUT_CTX.get("is_brief"))
    field_names = OUTPUT_CTX.get("field_names")
    if not is_brief and not field_names:
        return None
    kept_names = {*HEAD_KEYS, *GUIDANCE_KEYS}
    if is_brief:
        kept_names.update(BRIEF_KEYS)
    if field_names:
        kept_names.update(field_names)
    return kept_names


def emit_shaped(payload: dict) -> int:
    """모양을 정리해 JSON 하나로 낸다. out() 을 거치지 않는 인자 오류·예외 경로도 이것을 쓴다."""
    return emit(shape_payload(payload))


def attach_known_fix(payload: dict) -> None:
    """실패면 공식 트러블슈팅 요약(최대 2건)을 known_fix 로 싣는다. 맞는 것이 없으면 필드 없음.

    기억(memory)과 달리 하루 상한이 없다 — 이 실패에 맞춘 검증된 해결이라 매번 보여야 한다.
    어떤 오류도 명령 결과를 망치지 않는다.
    """
    if payload.get("ok", True) is not False:
        return
    try:
        causes = payload.get("causes") if isinstance(payload.get("causes"), list) else []
        text = " ".join(str(v) for v in (payload.get("error"), payload.get("hint"), *causes) if v)
        fixes = troubleshoot.find_known_fixes(SKILL_DIR, payload.get("code"), text)
        if fixes:
            payload["known_fix"] = fixes
            payload["known_fix_note"] = "검증된 공식 해결이다. 먼저 시도하고, 전체는 kb show <id>"
    except Exception:   # noqa: BLE001 — 공식 지식은 보조다
        pass


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
        _journal_hooks(payload, area, root, unknown, seen_dir)
    except Exception:   # noqa: BLE001 — 기억은 보조다. 실패해도 본 명령 결과는 그대로 낸다
        pass


def _journal_hooks(payload: dict, area: str, root: Path, unknown: bool, seen_dir: Path) -> None:
    """작업 일지 — 같은 영역에 돌아오면 최근 기록을 싣고, 작업을 마치면 적어 둘지 묻게 한다."""
    path = journal.store_path(root)
    rows = journal.surface(path, area, seen_dir / "journal_seen.json")
    if rows:
        payload["journal"] = rows
        payload["journal_note"] = ("전에 이 영역에서 했던 작업 기록이다. 참고만 한다 — 같은 작업을 다시 할 때 "
                                   "순서와 판단 기준을 이어 쓰되, 변경하는 동작은 사용자 확인을 거친다. "
                                   "달라진 점은 journal --add 로 덧붙인다")
    # 작업을 마치는 순간(창을 닫는 때)이 적어 둘 가장 좋은 때다 — 사용자에게 먼저 묻는다
    if payload.get("action") == "close" and payload.get("ok", True) is not False and not unknown:
        payload["journal_hint"] = (
            "이번에 한 작업이 다음에도 반복될 만하면 사용자에게 \"이 작업을 기록해 둘까요?\" 라고 묻고, 동의하면 "
            f"journal --add \"<무엇을 왜 했는지·순서·판단 기준·결과·다음에 헷갈릴 점>\" --title <제목> --area {area} "
            "--site <주소 일부> 로 적는다. 사용자가 먼저 기록해 달라고 하면 묻지 않고 바로 적는다 (비밀값은 적지 않는다)")


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
