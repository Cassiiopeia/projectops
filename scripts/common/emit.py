"""MCP-style JSON 출력 헬퍼.

모든 _cli.py 서브커맨드 출력은 이 emit() 통해 stdout으로 나간다.
4필드(ok/code/summary/next) 기본값 자동 보장, 출력에서도 이 4개가 맨 앞에 온다.

성공: emit({"data": ...})                        → rc=0, ok=true, code="ok"
에러: emit({"ok": False, "code": "...", ...})    → rc=1

전역 출력 옵션 (run_cli 가 argv 에서 꺼낸다):
  --brief        안내 필드(ok·code·summary·next·error·hint·usage·example)만
  --field a.b.0  성공 응답의 그 값만 (문자열이면 글자 그대로). 인라인 파이썬으로 키를 짐작해 파싱하지 않게 한다.
                 오류 응답에는 적용하지 않는다 (원인을 가리지 않는다)
"""
import json
import sys
from typing import Any, Optional

# 응답 맨 앞에 두는 키 — 잘라 읽어도 판단에 필요한 것이 남는다
_HEAD_KEYS = ("ok", "code", "summary", "next")
# --brief 에서도 남기는 안내 키
_GUIDE_KEYS = _HEAD_KEYS + ("error", "hint", "usage", "example", "did_you_mean", "available_subcommands")

_output_options: dict = {"brief": False, "field": None}


def configure_output(brief: bool = False, field: Optional[str] = None) -> None:
    """--brief / --field 를 켠다 (run_cli 가 호출)"""
    _output_options["brief"] = brief
    _output_options["field"] = field


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
    payload.setdefault("summary", None)
    payload.setdefault("next", None)
    payload = {**{key: payload[key] for key in _HEAD_KEYS}, **{k: v for k, v in payload.items() if k not in _HEAD_KEYS}}
    ok = payload["ok"]

    field = _output_options["field"]
    if field and ok:
        try:
            value = _lookup(payload, field)
        except (KeyError, IndexError, ValueError):
            sys.stdout.write(json.dumps({"ok": False, "code": "field_not_found", "summary": None, "next": None,
                                         "error": f"응답에 '{field}' 가 없다", "available_keys": list(payload)},
                                        ensure_ascii=False) + "\n")
            sys.stdout.flush()
            return 1
        sys.stdout.write((value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)) + "\n")
        sys.stdout.flush()
        return 0
    if _output_options["brief"]:
        payload = {key: value for key, value in payload.items() if key in _GUIDE_KEYS}
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()
    return 0 if ok else 1
