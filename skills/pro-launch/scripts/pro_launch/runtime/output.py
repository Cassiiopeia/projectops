"""모든 명령이 결과를 내는 한 곳 — `out()` 이 결과에 공통 후처리를 덧붙인다."""
from __future__ import annotations

import json
import shlex
import time
from pathlib import Path

from common import troubleshoot
from common.access import needs_verify, record_result
from common.emit import emit
from common.state import repo_unknown

import journal
import knowledge

from pro_launch.runtime.plugin_version import plugin_version, take_newer_installed
from pro_launch.runtime.recent_roots import root_candidates
from pro_launch.runtime.context import ACCESS_CTX, INPUT_CTX, MEMORY_CTX, MIGRATION, OUTPUT_CTX, ROOT_CTX

# skills/pro-launch — 공식 트러블슈팅(troubleshooting/)이 있는 곳
SKILL_DIR = Path(__file__).resolve().parents[3]


# 이 프로세스의 다음 응답에 붙일 필드 (디스패처 게이트의 남의 기기 경고 등) — 동작 코드가 몰라도 실린다
PENDING_RESPONSE_FIELDS: dict = {}


def add_response_fields(fields: dict) -> None:
    PENDING_RESPONSE_FIELDS.update(fields)


def out(payload: dict) -> int:
    """emit 에 이전 결과 · 대기 중인 응답 필드(게이트 경고 등)를 덧붙인다. 옮긴 것이 있으면 사용자가 알아야 한다."""
    for key, value in PENDING_RESPONSE_FIELDS.items():
        payload.setdefault(key, value)
    moved = [m for r in MIGRATION.values() for m in r.get("moved", [])]
    warns = [w for r in MIGRATION.values() for w in r.get("warnings", [])]
    if moved:
        payload["migrated"] = moved
    if warns:
        payload["migration_warnings"] = warns
    # summary 는 언제나 문자열이다 (#825) — None 이 섞이면 부르는 쪽 파싱이 깨진다(실측).
    if not payload.get("summary"):
        payload["summary"] = default_summary(payload)
    _root_warning(payload)
    _empty_value_warning(payload)
    _grade_access(payload)
    attach_known_fix(payload)
    _memory_hooks(payload)
    return emit_shaped(payload)


def default_summary(payload: dict) -> str:
    """summary 가 없을 때: 실패면 error > 첫 reason > code (실패를 "완료"로 적지 않는다, #972) · 성공이면 "<action> 완료"."""
    act = payload.get("action")
    if payload.get("ok", True) is False:
        reasons = payload.get("reasons") if isinstance(payload.get("reasons"), list) else []
        cause = payload.get("error") or (reasons[0] if reasons else None)
        label = f"{act} failed" if act else "failed"
        return str(cause) if cause else f"{label}: {payload.get('code') or 'error'}"
    return payload.get("error") or (f"{act} done" if act else "done")


# 맨 앞 4필드 — 잘라 읽어도 다음 행동이 남게 언제나 먼저 · 언제나 남긴다
HEAD_KEYS = ("ok", "code", "summary", "next")
# 실패 원인 한 줄 (render 의 묻힌 첫 오류 등) — 머리 바로 뒤 · --brief 에도 남긴다
CAUSE_KEYS = ("first_error", "unknown", "did_you_mean", "empty_values")
# 이 실패·영역에 맞춘 해결과 기억 — 원인 뒤 · 줄여도 남긴다
GUIDANCE_KEYS = ("known_fix", "known_fix_note", "memory", "memory_note", "learn_hint")
# 실패 · doctor 에만 싣는 버전 + 옛 설치본 경고(성공 포함, 1회) — 보고에 남게 · 줄여도 남긴다
VERSION_KEYS = ("plugin_version", "newer_installed")
# --brief 가 남기는 키: 머리 + error + 원인 + 안내 + 버전
BRIEF_KEYS = (*HEAD_KEYS, "error", *CAUSE_KEYS, *GUIDANCE_KEYS, *VERSION_KEYS)
# 실패면 --brief 에도 남기는 키 — next 가 읽으라고 가리키는 근거 (#972)
FAILURE_BRIEF_KEYS = ("reasons", "output_tail", "non_device_consumers", "unused_options", "valid_options")
# --fields 별칭: 요청 이름 > 같은 뜻의 실제 키 (캡처 경로는 file 로 낸다, #972)
FIELD_ALIASES = {"path": "file", "file": "path"}


def shape_payload(payload: dict) -> dict:
    """출력 모양 정리: 4필드 기본값 > 실패면 plugin_version > 순서(머리 > 원인 > 안내 > 나머지) > --brief · --fields 거르기.

    값은 바꾸지 않는다. 플래그가 없으면 키 집합은 (실패의 plugin_version 말고) 그대로이고 순서만 바뀐다.
    """
    # 기본값 (emit 과 같은 규칙) — emit 이 뒤에 붙이면 순서가 다시 어긋난다
    payload.setdefault("ok", True)
    payload.setdefault("code", "ok" if payload["ok"] else "error")
    payload.setdefault("summary", None)
    payload.setdefault("next", None)
    # 성공 응답에는 싣지 않는다 (응답 줄이기, #897)
    if payload["ok"] is False:
        payload.setdefault("plugin_version", plugin_version())
    newer_installed = take_newer_installed()
    if newer_installed:
        payload.setdefault("newer_installed", newer_installed)
    leading = [k for k in (*HEAD_KEYS, *CAUSE_KEYS, *GUIDANCE_KEYS, *VERSION_KEYS) if k in payload]
    ordered = {k: payload[k] for k in leading}
    ordered.update((k, v) for k, v in payload.items() if k not in ordered)
    field_names = _resolve_field_aliases(OUTPUT_CTX.get("field_names"), ordered)
    kept_names = _kept_key_names(field_names, is_failed=ordered["ok"] is False)
    if kept_names is None:
        return ordered
    return {**{k: v for k, v in ordered.items() if k in kept_names}, **_unknown_field_report(field_names, ordered)}


def _resolve_field_aliases(field_names: list[str] | None, ordered: dict) -> list[str] | None:
    """요청한 키가 없고 별칭 키가 있으면 별칭으로 바꾼다 (--fields path > file)."""
    if not field_names:
        return field_names
    return [FIELD_ALIASES[name] if name not in ordered and FIELD_ALIASES.get(name) in ordered else name
            for name in field_names]


def _unknown_field_report(field_names: list[str] | None, ordered: dict) -> dict:
    """--fields 에 없는 키가 있으면 {unknown_fields, available_fields} — 조용히 빈 결과를 내지 않는다 (#931)."""
    unknown = [name for name in field_names or [] if name not in ordered]
    if not unknown:
        return {}
    return {"unknown_fields": unknown, "available_fields": list(ordered)}


def _kept_key_names(field_names: list[str] | None, is_failed: bool) -> set[str] | None:
    """--brief · --fields 로 남길 키 이름. 둘 다 없으면 None (전부 남김), 둘 다면 합집합."""
    is_brief = bool(OUTPUT_CTX.get("is_brief"))
    if not is_brief and not field_names:
        return None
    kept_names = {*HEAD_KEYS, *GUIDANCE_KEYS, *VERSION_KEYS}
    if is_brief:
        kept_names.update(BRIEF_KEYS)
        if is_failed:
            kept_names.update(FAILURE_BRIEF_KEYS)
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
        fixes = troubleshoot.find_known_fixes(SKILL_DIR, payload.get("code"), text, areas=_failure_areas(payload))
        if fixes:
            payload["known_fix"] = fixes
            payload["known_fix_note"] = "Verified official fix. Try it first; full entry: kb show <id>"
    except Exception:   # noqa: BLE001 — 공식 지식은 보조다
        pass


def _failure_areas(payload: dict) -> tuple[str, ...] | None:
    """이 실패의 영역 (응답 platform > 동작이 정한 기억 영역). 모르면 None (거르지 않음) — iOS 실패에 android 해결이 실리지 않게 (#972)."""
    area = payload.get("platform") if payload.get("platform") in troubleshoot.AREAS else MEMORY_CTX.get("area")
    return (area,) if area in troubleshoot.AREAS else None


def _empty_value_warning(payload: dict) -> None:
    """실패했고 빈 값으로 넘어온 옵션이 있으면 그 옵션을 짚는다 (bad_viewport: unknown viewport '' 등, #886)."""
    empty = INPUT_CTX.get("empty_values")
    if not empty or payload.get("ok", True) is not False or "empty_values" in payload:
        return
    payload["empty_values"] = empty
    payload["empty_values_note"] = (f"{', '.join(empty)} has an empty value — if you passed $VAR, check that "
                                    "the environment variable is set")


# 루트를 잘못 잡았을 때 흔한 실패 — 후보 루트와 다시 부를 명령을 싣는다 (#885)
ROOT_SENSITIVE_CODES = {"browser_not_open", "git_not_found"}


def _root_warning(payload: dict) -> None:
    if ROOT_CTX.get("source") == "last_used":
        payload["root_source"] = "last_used"
        payload["root_note"] = (f"Working folder ({ROOT_CTX.get('cwd')}) is not a repo, so the last used {ROOT_CTX.get('path')} was used — "
                                "for another repo add --root <path>")
    if ROOT_CTX.get("scratch"):
        payload["root_scratch"] = True
        payload["root_note"] = (f"{ROOT_CTX.get('path')} has no git and no project marker — state goes to a scratch bucket "
                                "(_scratch/<name>-<hash>) and is not remembered as a recent root. For a project, pass the repo absolute path with --root")
    is_failed = payload.get("ok", True) is False
    if is_failed and (ROOT_CTX.get("not_repo") or ROOT_CTX.get("unknown")
                          or payload.get("code") in ROOT_SENSITIVE_CODES):
        _attach_root_candidates(payload)
    if not ROOT_CTX.get("unknown"):
        return
    payload["root_unknown"] = True
    payload["root_warning"] = (f"Called from a folder with no known project ({ROOT_CTX.get('path')}) — "
                               "state goes to this machine's shared location and no repo memory is written")
    fix = "Call again with --root <project path> (or the PROJECT_ROOT environment variable)"
    nxt = payload.get("next")
    if not nxt:
        payload["next"] = fix
    elif isinstance(nxt, str) and fix not in nxt:
        payload["next"] = f"{fix}. Then: {nxt}"


def _attach_root_candidates(payload: dict) -> None:
    """후보 루트(브라우저가 살아 있는 것이 앞)와 그대로 복사해 쓸 재시도 명령."""
    try:
        candidates = root_candidates()
    except Exception:   # noqa: BLE001 — 후보는 보조다
        return
    current = ROOT_CTX.get("resolved")
    candidates = [c for c in candidates if c["path"] != current]
    if not candidates:
        return
    payload["root_candidates"] = candidates
    payload["retry"] = retry_command_with_root(candidates[0]["path"])
    payload["next"] = (f"May have been called outside the repo — retry: {payload['retry']}"
                       + (f". Then: {payload['next']}" if payload.get("next") else ""))


def retry_command_with_root(root: str) -> str:
    """이번 명령을 --root <root> 로 바꿔 다시 부르는 한 줄 (원래 --root 는 뺀다)."""
    raw = list(INPUT_CTX.get("raw") or [])
    kept, index = [], 0
    while index < len(raw):
        if raw[index] == "--root":
            index += 2
            continue
        if not raw[index].startswith("--root="):
            kept.append(raw[index])
        index += 1
    return "launch_cli.py " + " ".join(shlex.quote(token) for token in [*kept, "--root", root])


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
        payload["verify_note"] = (f"access '{key}' failed last time ({lf.get('date')}, {lf.get('code')}) — "
                                  + ("it worked this time" if ok else
                                     "it failed again. Re-read the code and fix it with access set"))


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
            payload["memory_note"] = ("Methods that worked on this machine. If you used one, record the result with "
                                      f"learn --area {area} --key <key> --how <how> --result ok|fail")
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
        payload["journal_note"] = ("Earlier work records in this area. Reference only — when repeating the work, reuse "
                                   "the order and decision criteria, but confirm changing actions with the user. "
                                   "Add what changed with journal --add")
    # 작업을 마치는 순간(창을 닫는 때)이 적어 둘 가장 좋은 때다 — 사용자에게 먼저 묻는다
    if payload.get("action") == "close" and payload.get("ok", True) is not False and not unknown:
        payload["journal_hint"] = (
            "If this work is likely to be repeated, ask the user \"Shall I record this work?\" and, if they agree, write it with "
            f"journal --add \"<what and why · order · decision criteria · result · what will be confusing next time>\" --title <title> --area {area} "
            "--site <part of the address>. If the user asked for a record first, write it without asking (never write secrets)")


# 실패 > 성공 연쇄 기록 (#863) — session-check 가 "막혔다 풀렸는데 learn 안 한 영역"을 짚는다
RESOLVED_FILE = "resolved.json"
RESOLVED_KEEP = 20
# learn_hint 연쇄에서 빼는 실패 code — 조건 확인용 대기·판정·잘못 부름은 새로 배울 방식이 아니다
INTENDED_FAILURE_CODES = frozenset({"wait_timeout", "expect_not_met", "unexpected_status", "not_found",
                                    "index_out_of_range", "bad_args", "args_required", "args_invalid",
                                    "missing_argument", "unexpected_argument", "text_required", "value_required",
                                    "target_required"})


def _track_attempt(f: Path, area: str, payload: dict) -> str | None:
    """같은 영역에서 실패한 뒤 성공하면 '새로 알게 된 방식이면 기록하라'고 알려 준다.

    agent 가 기억을 남길 가장 좋은 순간은 막혔다 풀린 직후다. 그 순간을 도구가 짚어 준다.
    실패 횟수를 세어 두고, 풀리면 resolved.json 에 연쇄(영역·횟수·마지막 실패 code)를 남긴다.
    """
    ok = payload.get("ok", True) is not False and payload.get("code") in (None, "ok")
    # 의도된 실패(대기 시간 초과·인자 오류·없는 대상)는 막힌 것이 아니다 — 연쇄에 넣지 않는다 (#972)
    if not ok and payload.get("code") in INTENDED_FAILURE_CODES:
        return None
    try:
        last = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        last = {}
    now = time.time()
    prev = last.get(area) or {}
    if ok:
        last.pop(area, None)
    else:
        # 창 밖의 옛 실패는 이번 연쇄가 아니다 — 처음부터 센다
        earlier = int(prev.get("fails") or 1) if prev and now - prev.get("at", 0) < _FIX_WINDOW_SEC else 0
        last[area] = {"code": payload.get("code"), "at": now, "fails": earlier + 1}
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(last), encoding="utf-8")
    except OSError:
        pass
    if not (ok and prev and now - prev.get("at", 0) < _FIX_WINDOW_SEC):
        return None
    fails = int(prev.get("fails") or 1)
    _append_resolved(f.parent / RESOLVED_FILE, {"area": area, "fails": fails,
                                                "last_code": prev.get("code"), "at": now})
    times = f" {fails} times" if fails > 1 else ""
    return (f"Just got past '{prev.get('code')}' after failing{times}. If the method is reusable, record it with "
            f"learn --area {area} --key <short-key> --how '<what and how>' --result ok "
            "(long story: --detail. Do not record missing installs, one-offs or secrets)")


def _append_resolved(f: Path, row: dict) -> None:
    try:
        rows = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        rows = []
    rows = [*(rows if isinstance(rows, list) else []), row][-RESOLVED_KEEP:]
    try:
        f.write_text(json.dumps(rows), encoding="utf-8")
    except OSError:
        pass
