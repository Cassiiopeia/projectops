"""api: drive a server scenario end to end (token chaining · status code judgement)"""
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
# Edge cases — extract from the code the "failure paths that must be driven"
# =========================================================================

# (regex, what must be driven, how to produce it)
_SECRET_KEYS = ("password", "secret", "token", "key")


# ── Server target: drive an API sequence (issue #586) ───────────────────────────
#
# Backends with no screen are verified with this skill too. The key is **pulling values from the previous
# response into the next request** — without login every later request is 401 and nothing moves.

def _parse_do(do: str) -> tuple[str, str, dict | None]:
    """Split a step's `do` into method, path and body.

    Format: `POST /api/auth/login {"id": "x"}`  (body is optional)
    """
    m = re.match(r"\s*([A-Z]+)\s+(\S+)\s*(\{.*\}|\[.*\])?\s*$", do, re.S)
    if not m:
        raise ValueError(
            f'Cannot read the step: {do!r} — it must look like "POST /api/x {{...}}"')
    body = None
    if m.group(3):
        try:
            body = json.loads(m.group(3))
        except json.JSONDecodeError as e:
            raise ValueError(f"The body is not valid JSON: {e}") from e
    return m.group(1).upper(), m.group(2), body


def _fill(value, saved: dict):
    """Fill {token} slots with values saved by earlier steps. Walks nested structures too."""
    if isinstance(value, str):
        def sub(m):
            key = m.group(1)
            if key not in saved:
                raise ValueError(f"No value to fill {{{key}}} — check save in an earlier step")
            return str(saved[key])
        return re.sub(r"\{([A-Za-z_][A-Za-z0-9_]*)\}", sub, value)
    if isinstance(value, dict):
        return {k: _fill(v, saved) for k, v in value.items()}
    if isinstance(value, list):
        return [_fill(v, saved) for v in value]
    return value


def _jsonpath(data, expr: str):
    """Reads only about `$.a.b[0]`.

    No full JSONPath library because this script must run on the standard library
    only. This is enough to pull one token out of a response.
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
    """Send one request. Failure does not raise — the failure response itself is often what is verified."""
    url = path if path.startswith("http") else base.rstrip("/") + "/" + path.lstrip("/")
    data = json.dumps(body).encode() if body is not None else None
    h = {"Content-Type": "application/json", "Accept": "application/json", **headers}
    r = _http_request(method, url, h, data, timeout=timeout)
    r.pop("raw", None)
    r.pop("headers", None)
    return r

def cmd_api(args) -> int:
    """Drive a server scenario.

    One call drives the whole scenario — unlike app and web there is no screen to judge,
    so no reason to split, and token chaining is simpler kept inside one process.
    """
    root = Path(args.root).resolve()
    d = _scenario_dir(root)
    f = _resolve_scenario(d, args.name)
    if f is None:
        return emit({"ok": False, "code": "scenario_not_found",
                     "error": f"Scenario '{args.name}' not found",
                     "next": f"scenario list --root {root}"})

    data, problems = _expand(d, f)
    if problems:
        return emit({"ok": False, "code": "scenario_invalid", "problems": problems,
                     "next": "Fix each entry in problems in the scenario file, then run it again"})
    problems = _validate(data)
    if problems:
        return emit({"ok": False, "code": "scenario_invalid", "problems": problems,
                     "next": "Fix each entry in problems in the scenario file, then run it again"})
    if scenario_target(data) != "server":
        return emit({"ok": False, "code": "wrong_target",
                     "error": f"This scenario's target is '{scenario_target(data)}'",
                     "hint": "api is only for the server target"})

    base = args.base_url or data.get("base_url") or ""
    if not base or base.startswith("{"):
        # If the scenario lacks it, use what was recorded. Do not guess from the code.
        rec = _load_access(root).get("base_url")
        base = (rec.get("url") if isinstance(rec, dict) else rec) or ""
    if not base:
        return emit({"ok": False, "code": "base_url_required",
                     "error": "API address is unknown",
                     "next": ("pass --base-url, or find it in the code, then "
                              "access set --key base_url --json '{\"url\":\"http://...\"}'")})

    if not re.match(r"https?://[^\s/]+", base):
        return emit({"ok": False, "code": "bad_base_url",
                     "error": f"API address '{base}' must start with http(s)://",
                     "next": "pass the full address, e.g. --base-url http://127.0.0.1:8080"})

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
        # expect_json is a human-readable description. Automatic judgement uses save/status code;
        # here the actual response is kept alongside so the agent can compare by eye.
        if st.get("expect_json"):
            row["response"] = res["json"]
            checks.append({"expect_json": st["expect_json"], "ok": None})
        if st.get("expect_server"):
            row["expect_server"] = st["expect_server"]   # actual lookup via the db subcommand

        for key, expr in (st.get("save") or {}).items():
            val = _jsonpath(res["json"], expr) if res["json"] is not None else None
            saved[key] = val
            checks.append({"save": key, "from": expr, "got": None if val is None else "received",
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
        "summary": (f"all {len(results)} step(s) passed" if done
                    else f"stopped at step {failed_at}"),
        "next": (None if done else
                 "logs --root <root>  # narrow the cause with server logs. If none, access set --key logs"),
    })
