"""api: 서버 시나리오를 끝까지 밟기 (토큰 체이닝 · 상태코드 판정)"""
from __future__ import annotations

import json
import re
from pathlib import Path

from common.access import load_access as _load_access
from common.emit import emit
from common.http import request as _http_request

from pro_agent_test.scenario_rules import _validate, scenario_target
from pro_agent_test.storage import _expand, _resolve_scenario, _scenario_dir


# =========================================================================
# 엣지케이스 — 코드에서 "밟아야 할 실패 경로"를 뽑아낸다
# =========================================================================

# (정규식, 무엇을 밟아야 하는가, 어떻게 만드는가)
_SECRET_KEYS = ("password", "secret", "token", "key")


# ── 서버 타겟: API 시퀀스를 밟는다 (이슈 #586) ───────────────────────────
#
# 화면이 없는 백엔드도 이 스킬로 검증한다. 핵심은 **이전 응답에서 값을 뽑아 다음
# 요청에 물리는 것**이다 — 로그인 없이는 그다음 요청이 전부 401이라 한 걸음도 못 간다.

def _parse_do(do: str) -> tuple[str, str, dict | None]:
    """단계의 `do`를 메서드·경로·본문으로 가른다.

    형식: `POST /api/auth/login {"id": "x"}`  (본문은 없어도 된다)
    """
    m = re.match(r"\s*([A-Z]+)\s+(\S+)\s*(\{.*\}|\[.*\])?\s*$", do, re.S)
    if not m:
        raise ValueError(
            f'단계를 읽을 수 없습니다: {do!r} — "POST /api/x {{...}}" 형식이어야 합니다')
    body = None
    if m.group(3):
        try:
            body = json.loads(m.group(3))
        except json.JSONDecodeError as e:
            raise ValueError(f"본문이 올바른 JSON이 아닙니다: {e}") from e
    return m.group(1).upper(), m.group(2), body


def _fill(value, saved: dict):
    """{token} 자리에 앞 단계에서 저장한 값을 끼운다. 중첩 구조도 따라 내려간다."""
    if isinstance(value, str):
        def sub(m):
            key = m.group(1)
            if key not in saved:
                raise ValueError(f"{{{key}}} 를 채울 값이 없습니다 — 앞 단계의 save를 확인하세요")
            return str(saved[key])
        return re.sub(r"\{([A-Za-z_][A-Za-z0-9_]*)\}", sub, value)
    if isinstance(value, dict):
        return {k: _fill(v, saved) for k, v in value.items()}
    if isinstance(value, list):
        return [_fill(v, saved) for v in value]
    return value


def _jsonpath(data, expr: str):
    """`$.a.b[0]` 정도만 읽는다.

    전체 JSONPath 라이브러리를 쓰지 않는 이유는 이 스크립트가 표준 라이브러리만으로
    돌아야 하기 때문이다. 응답에서 토큰 하나 꺼내는 데는 이걸로 충분하다.
    """
    cur = data
    for part in re.findall(r"[^.\[\]]+|\[\d+\]", expr.lstrip("$.")):
        if part.startswith("["):
            idx = int(part[1:-1])
            if not isinstance(cur, list) or idx >= len(cur):
                return None
            cur = cur[idx]
        else:
            if not isinstance(cur, dict) or part not in cur:
                return None
            cur = cur[part]
    return cur


def _api_call(base: str, method: str, path: str, body, headers: dict, timeout: int = 30) -> dict:
    """한 요청을 보낸다. 실패해도 예외로 끝내지 않는다 — 실패 응답 자체가 검증 대상인 경우가 많다."""
    url = path if path.startswith("http") else base.rstrip("/") + "/" + path.lstrip("/")
    data = json.dumps(body).encode() if body is not None else None
    h = {"Content-Type": "application/json", "Accept": "application/json", **headers}
    r = _http_request(method, url, h, data, timeout=timeout)
    r.pop("raw", None)
    r.pop("headers", None)
    return r

def cmd_api(args) -> int:
    """서버 시나리오를 밟는다.

    한 번의 호출로 시나리오 전체를 밟는다 — 앱·웹과 달리 화면을 보고 판단할 것이
    없으므로 쪼갤 이유가 없고, 토큰 체이닝이 한 프로세스 안에서 끝나야 단순하다.
    """
    root = Path(args.root).resolve()
    d = _scenario_dir(root)
    f = _resolve_scenario(d, args.name)
    if f is None:
        return emit({"ok": False, "code": "scenario_not_found",
                     "error": f"시나리오 '{args.name}' 을 찾지 못했습니다",
                     "next": f"scenario list --root {root}"})

    data, problems = _expand(d, f)
    if problems:
        return emit({"ok": False, "code": "scenario_invalid", "problems": problems})
    problems = _validate(data)
    if problems:
        return emit({"ok": False, "code": "scenario_invalid", "problems": problems})
    if scenario_target(data) != "server":
        return emit({"ok": False, "code": "wrong_target",
                     "error": f"이 시나리오의 target은 '{scenario_target(data)}' 입니다",
                     "hint": "api 는 server 타겟 전용입니다"})

    base = args.base_url or data.get("base_url") or ""
    if not base or base.startswith("{"):
        # 시나리오에 없으면 기록해 둔 것을 쓴다. 코드에서 짐작하지 않는다.
        rec = _load_access(root).get("base_url")
        base = (rec.get("url") if isinstance(rec, dict) else rec) or ""
    if not base:
        return emit({"ok": False, "code": "base_url_required",
                     "error": "API 주소를 알 수 없습니다",
                     "next": ("--base-url 로 넘기거나, 코드를 읽어 알아낸 뒤 "
                              "access set --key base_url --json '{\"url\":\"http://...\"}'")})

    if not re.match(r"https?://[^\s/]+", base):
        return emit({"ok": False, "code": "bad_base_url",
                     "error": f"API 주소 '{base}' 는 http(s):// 로 시작해야 합니다",
                     "next": "--base-url http://127.0.0.1:8080 처럼 전체 주소를 넘긴다"})

    saved: dict = {}
    results = []
    failed_at = None
    for i, st in enumerate(data["steps"], 1):
        if st.get("human"):
            results.append({"step": i, "status": "paused", "human": st["human"]})
            failed_at = i
            break
        try:
            method, path, body = _parse_do(_fill(st["do"], saved))
            body = _fill(body, saved) if body is not None else None
            headers = {}
            if st.get("auth"):
                headers["Authorization"] = f"Bearer {_fill(st['auth'], saved)}"
        except ValueError as e:
            results.append({"step": i, "status": "error", "error": str(e)})
            failed_at = i
            break

        res = _api_call(base, method, path, body, headers, timeout=args.timeout)
        row = {"step": i, "do": f"{method} {path}", "elapsed_ms": res.get("elapsed_ms")}
        if not res["ok"]:
            row.update({"status": "error", "error": res["error"]})
            results.append(row)
            failed_at = i
            break

        row["http_status"] = res["status"]
        checks = []
        want = st.get("expect_status")
        if want is not None:
            ok = res["status"] == want
            checks.append({"expect_status": want, "got": res["status"], "ok": ok})
        # expect_json 은 사람이 읽는 설명이다. 자동 판정은 save/상태코드로 하고,
        # 여기서는 실제 응답을 함께 남겨 agent가 눈으로 대조하게 한다.
        if st.get("expect_json"):
            row["response"] = res["json"]
            checks.append({"expect_json": st["expect_json"], "ok": None})
        if st.get("expect_server"):
            row["expect_server"] = st["expect_server"]   # 실제 조회는 db 서브커맨드로

        for key, expr in (st.get("save") or {}).items():
            val = _jsonpath(res["json"], expr) if res["json"] is not None else None
            saved[key] = val
            checks.append({"save": key, "from": expr, "got": None if val is None else "받음",
                           "ok": val is not None})

        row["checks"] = checks
        row["status"] = "ok" if all(c.get("ok") is not False for c in checks) else "fail"
        results.append(row)
        if row["status"] == "fail":
            failed_at = i
            break

    done = failed_at is None
    return emit({
        "ok": done,
        "scenario": data.get("name"),
        "base_url": base,
        "steps": results,
        "saved_keys": sorted(saved),
        "summary": (f"{len(results)}단계 전부 통과" if done
                    else f"{failed_at}번째 단계에서 멈춤"),
        "next": (None if done else
                 "logs --root <루트>  # 서버 로그로 원인을 좁히세요. 없으면 access set --key logs"),
    })
