"""MCP-style JSON 출력 헬퍼.

모든 _cli.py 서브커맨드 출력은 이 emit() 통해 stdout으로 나간다.
4필드(ok/code/summary/next) 기본값 자동 보장, 출력에서도 이 4개가 맨 앞에 온다. summary 는 언제나 문자열.

성공: emit({"data": ...})                        → rc=0, ok=true, code="ok"
에러: emit({"ok": False, "code": "...", ...})    → rc=1

전역 출력 옵션 (run_cli 가 argv 에서 꺼낸다):
  --brief        안내 필드(ok·code·summary·next·error·hint·usage·example) + 목록의 최소 행(번호·제목·상태)
  --field a.b.0  성공 응답의 그 값만 (문자열이면 글자 그대로). 인라인 파이썬으로 키를 짐작해 파싱하지 않게 한다.
                 오류 응답에는 적용하지 않는다 (원인을 가리지 않는다)
  --fields a,b   여러 경로 > {경로: 값} JSON. 하나면 --field 와 같다
"""
import difflib
import json
import sys
from typing import Any, Optional

# 응답 맨 앞에 두는 키 — 잘라 읽어도 판단에 필요한 것이 남는다
_HEAD_KEYS = ("ok", "code", "summary", "next")
# --brief 에서도 남기는 안내 키
_GUIDE_KEYS = _HEAD_KEYS + ("error", "hint", "usage", "example", "did_you_mean", "available_subcommands",
                              "newer_installed", "count", "warning", "warnings")
# --brief 에서 목록 행마다 남기는 식별 키 (번호·제목·상태) — 목록을 버리지 않아 재호출이 필요 없게
_BRIEF_ROW_KEYS = ("number", "id", "run_id", "job_id", "title", "name", "state", "status", "conclusion")
# field_not_found 후보로 펼칠 중첩 깊이
_CANDIDATE_PATH_DEPTH = 3

_output_options: dict = {"brief": False, "field": None, "extra": {}}


def configure_output(brief: bool = False, field: Optional[str] = None, extra: Optional[dict] = None) -> None:
    """--brief / --field(s) 를 켠다 (run_cli 가 호출). field 에 쉼표가 있으면 여러 경로. extra: 첫 응답에 덧붙일 키"""
    _output_options["brief"] = brief
    _output_options["field"] = field
    _output_options["extra"] = dict(extra or {})


def _lookup(payload: Any, dotted_path: str) -> Any:
    """a.b.0 경로로 값을 찾는다. 없으면 KeyError"""
    current = payload
    for part in dotted_path.split("."):
        if isinstance(current, list):
            current = current[int(part)]
        elif isinstance(current, dict):
            current = current[part]
        else:
            raise KeyError(part)
    return current


def _candidate_paths(value: Any, prefix: str = "", depth: int = _CANDIDATE_PATH_DEPTH) -> list:
    """응답 안의 점 경로 후보 (issue.labels, runs.0.run_id …). 목록은 첫 항목만 펼친다"""
    if depth == 0:
        return []
    if isinstance(value, dict):
        children = value.items()
    elif isinstance(value, list) and value:
        children = [("0", value[0])]
    else:
        return []
    paths = []
    for key, child in children:
        path = f"{prefix}{key}"
        paths.append(path)
        paths.extend(_candidate_paths(child, f"{path}.", depth - 1))
    return paths


def _suggest_paths(payload: dict, wanted: str) -> list:
    """없는 경로 > 끝 이름이 같은 중첩 경로 우선, 그다음 비슷한 경로"""
    candidates = _candidate_paths(payload)
    last_name = wanted.split(".")[-1]
    same_last = [path for path in candidates if path.split(".")[-1] == last_name and path != wanted]
    similar = difflib.get_close_matches(wanted, candidates, n=5, cutoff=0.5)
    return list(dict.fromkeys(same_last + similar))[:5]


def _default_summary(payload: dict) -> str:
    """summary 가 비었을 때: 실패면 원인(error) 또는 code, 성공이면 '완료'"""
    if payload["ok"]:
        return "done"
    return str(payload.get("error") or payload["code"])


def _brief_rows(items: list) -> Optional[list]:
    """dict 목록 > 행마다 식별 키만. 남길 키가 없으면 None"""
    if not items or not all(isinstance(item, dict) for item in items):
        return None
    rows = [{key: item[key] for key in _BRIEF_ROW_KEYS if key in item} for item in items]
    return rows if any(rows) else None


def _to_brief(payload: dict) -> dict:
    """안내 키 + 목록(최소 행)만 남긴다"""
    brief = {}
    for key, value in payload.items():
        if key in _GUIDE_KEYS:
            brief[key] = value
        elif isinstance(value, list) and (rows := _brief_rows(value)) is not None:
            brief[key] = rows
    return brief


def _write(payload: Any) -> None:
    sys.stdout.write((payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)) + "\n")
    sys.stdout.flush()


def _emit_fields(payload: dict, field: str) -> int:
    """--field(s): 성공 응답에서 요청 경로 값만. 없는 경로면 field_not_found + 중첩 후보"""
    paths = [path.strip() for path in field.split(",") if path.strip()]
    values = {}
    for path in paths:
        try:
            values[path] = _lookup(payload, path)
        except (KeyError, IndexError, ValueError):
            _write({"ok": False, "code": "field_not_found", "summary": f"the response has no '{path}'",
                    "next": "call again with a path from did_you_mean", "error": f"the response has no '{path}'",
                    "did_you_mean": _suggest_paths(payload, path), "available_keys": list(payload)})
            return 1
    _write(values[paths[0]] if len(paths) == 1 else values)
    return 0


def emit(payload: dict) -> int:
    """JSON을 stdout에 출력하고 ok 값에 따라 rc 반환.

    payload에 ok/code/summary/next가 없으면 기본값을 채워 4필드를 강제한다.
    한글은 ensure_ascii=False로 그대로 출력.
    """
    payload.setdefault("ok", True)
    if payload["ok"] and "code" not in payload:
        payload["code"] = "ok"
    elif not payload["ok"] and "code" not in payload:
        payload["code"] = "error"
    # summary 는 언제나 문자열 — None 이 섞이면 부르는 쪽 파싱이 깨진다
    if payload.get("summary") in (None, ""):
        payload["summary"] = _default_summary(payload)
    elif not isinstance(payload["summary"], str):
        payload["summary"] = str(payload["summary"])
    payload.setdefault("next", None)
    payload = {**{key: payload[key] for key in _HEAD_KEYS}, **{k: v for k, v in payload.items() if k not in _HEAD_KEYS}}
    # 한 번만 싣는 안내 (옛 버전에서 돌고 있다는 경고 등)
    for key, value in _output_options["extra"].items():
        payload.setdefault(key, value)
    _output_options["extra"] = {}
    ok = payload["ok"]

    field = _output_options["field"]
    if field and ok:
        return _emit_fields(payload, field)
    if _output_options["brief"]:
        payload = _to_brief(payload)
    _write(payload)
    return 0 if ok else 1
