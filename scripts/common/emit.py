"""MCP-style JSON output helper.

Every _cli.py subcommand writes to stdout through this emit().
The 4 fields (ok/code/summary/next) always get defaults and come first in the output. summary is always a string.

Success: emit({"data": ...})                        → rc=0, ok=true, code="ok"
Error:   emit({"ok": False, "code": "...", ...})    → rc=1

Global output options (run_cli pulls them from argv):
  --brief        guidance fields (ok, code, summary, next, error, hint, usage, example) + minimal list rows (number, title, state)
  --field a.b.0  only that value of a success response (strings printed raw). Avoids guessing keys with inline Python parsing.
                 Not applied to error responses (does not hide the cause)
  --fields a,b   {path: value} JSON — JSON even for one path (#1187)
"""
import difflib
import itertools
import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

# Keep one unencodable char (— etc.) on a cp949 console from killing the CLI. Clean UTF-8 comes via PYTHONIOENCODING
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(errors="replace")

# Keys placed first in the response — truncated reads still keep what is needed to decide
_HEAD_KEYS = ("ok", "code", "summary", "next")
# A failure that already carries one of these tells the agent what to do; no fallback next is added
_FAILURE_GUIDE_KEYS = ("hint", "ask_user", "fix", "known_fix", "usage", "example")
# Guidance keys kept under --brief too
_GUIDE_KEYS = _HEAD_KEYS + ("error", "hint", "usage", "example", "did_you_mean", "available_subcommands",
                              "newer_installed", "count", "warning", "warnings")
# Identity keys kept per list row under --brief (number, title, state) — the list stays, so no re-call is needed
_BRIEF_ROW_KEYS = ("number", "id", "run_id", "job_id", "title", "name", "state", "status", "conclusion")
# Nesting depth expanded for field_not_found candidates
_CANDIDATE_PATH_DEPTH = 3

_output_options: dict = {"brief": False, "field": None, "should_return_object": False, "extra": {}}


def configure_output(brief: bool = False, field: Optional[str] = None, extra: Optional[dict] = None,
                     should_return_object: bool = False) -> None:
    """Turn on --brief / --field(s) (called by run_cli). A comma in field means several paths. extra: keys added to the first response
    should_return_object: given via --fields > {path: value} even for one path"""
    _output_options["brief"] = brief
    _output_options["field"] = field
    _output_options["should_return_object"] = should_return_object
    _output_options["extra"] = dict(extra or {})


def _lookup(payload: Any, dotted_path: str) -> Any:
    """Find a value by an a.b.0 path. KeyError if missing"""
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
    """Dot-path candidates inside the response (issue.labels, runs.0.run_id …). Lists expand only their first item"""
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
    """Missing path > nested paths with the same last name first, then similar paths"""
    candidates = _candidate_paths(payload)
    last_name = wanted.split(".")[-1]
    same_last = [path for path in candidates if path.split(".")[-1] == last_name and path != wanted]
    similar = difflib.get_close_matches(wanted, candidates, n=5, cutoff=0.5)
    return list(dict.fromkeys(same_last + similar))[:5]


def _default_summary(payload: dict) -> str:
    """When summary is empty: on failure the cause (error) or code, on success 'done'"""
    if payload["ok"]:
        return "done"
    return str(payload.get("error") or payload["code"])


def _brief_rows(items: list) -> Optional[list]:
    """dict list > identity keys per row only. None if there are no keys to keep"""
    if not items or not all(isinstance(item, dict) for item in items):
        return None
    rows = [{key: item[key] for key in _BRIEF_ROW_KEYS if key in item} for item in items]
    return rows if any(rows) else None


def _to_brief(payload: dict) -> dict:
    """Keep only guidance keys + lists (minimal rows)"""
    brief = {}
    for key, value in payload.items():
        if key in _GUIDE_KEYS:
            brief[key] = value
        elif isinstance(value, list) and (rows := _brief_rows(value)) is not None:
            brief[key] = rows
    return brief


def _write(payload: Any) -> None:
    try:
        sys.stdout.write((payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)) + "\n")
        sys.stdout.flush()
    except BrokenPipeError:
        # Reader (head etc.) exited first > send later output and exit flush to devnull (prevents re-emit and exit-warning tracebacks, #1010)
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())


def _emit_fields(payload: dict, field: str) -> int:
    """--field(s): only the requested path values from a success response. Missing path > field_not_found + nested candidates"""
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
    is_single_value = len(paths) == 1 and not _output_options["should_return_object"]
    _write(values[paths[0]] if is_single_value else values)
    return 0


def _fallback_next() -> str:
    """Where to look when a failure carries no next step, so the agent is never left without one."""
    command = [Path(sys.argv[0]).name] + list(itertools.takewhile(lambda token: not token.startswith("-"), sys.argv[1:3]))
    return (f"Read error first. If an argument is wrong: {' '.join(command)} --help. Otherwise look up this code "
            "in the skill's failure-code table (SKILL.md and its references) and decide from there")


def emit(payload: dict) -> int:
    """Print JSON to stdout and return rc based on ok.

    Fills defaults when ok/code/summary/next are missing, enforcing the 4 fields.
    Non-ASCII text is printed as is with ensure_ascii=False.
    """
    payload.setdefault("ok", True)
    if payload["ok"] and "code" not in payload:
        payload["code"] = "ok"
    elif not payload["ok"] and "code" not in payload:
        payload["code"] = "error"
    # summary is always a string — a None breaks the caller's parsing
    if payload.get("summary") in (None, ""):
        payload["summary"] = _default_summary(payload)
    elif not isinstance(payload["summary"], str):
        payload["summary"] = str(payload["summary"])
    payload.setdefault("next", None)
    if not payload["ok"] and not payload["next"] and not any(payload.get(key) for key in _FAILURE_GUIDE_KEYS):
        payload["next"] = _fallback_next()
    payload = {**{key: payload[key] for key in _HEAD_KEYS}, **{k: v for k, v in payload.items() if k not in _HEAD_KEYS}}
    # One-time notice (e.g. warning that an old version is running)
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
