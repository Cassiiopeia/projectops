"""`web script` — run a Playwright snippet with the attached browser's page · context (#904).

For the long tail not covered by fixed actions, agents wrote CDP attach scripts from scratch (31 of 108 sessions, 654 times).
Snippet contract: use the names page · context. If the last line is an expression its value is the result, otherwise the variable result.
Flow: read snippet > block in read-only > child process (script_runner) attaches and runs > kill past time or browser memory cap > mask credential values
print output is collected into the stdout field (so the JSON output stays intact).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import credentials

from pro_launch.commands.web import browser_memory, script_runner, tabs
from pro_launch.registry import Action
from pro_launch.runtime.browser import read_state, write_state
from pro_launch.runtime.output import out
from pro_launch.runtime.procs import kill_browser

# Default run cap (seconds)
DEFAULT_SCRIPT_SECONDS = 60
# Extra time for attach and reinstall (seconds) — separate from the snippet cap
CONNECT_GRACE_SECONDS = 5
# Max characters of result · stdout included
MAXIMUM_RESULT_CHARS = 20000
MAXIMUM_STDOUT_CHARS = 4000
MASK = "***"
# Minimum length of secret values to mask — short values would mask ordinary text
MINIMUM_MASKED_LENGTH = 4


def read_snippet(file_name: str | None) -> tuple[str | None, dict | None]:
    """Read the snippet from --file or stdin. (code, failure result)"""
    if file_name and file_name != "-":
        path = Path(file_name).expanduser()
        if not path.is_file():
            return None, {"ok": False, "code": "file_not_found", "file": file_name,
                          "error": f"File not found: {file_name}"}
        return path.read_text(encoding="utf-8"), None
    if sys.stdin is None or sys.stdin.isatty():
        return None, {"ok": False, "code": "script_required",
                      "error": "Pass a snippet file with --file or pipe it on standard input",
                      "next": "web script --file snippet.py"}
    return sys.stdin.read(), None


def saved_secret_values() -> list[str]:
    """Secret values of all saved credentials (longest first). Empty list if unreadable"""
    try:
        entries = credentials.load_all()
    except Exception:
        return []
    values = {value for entry in entries.values() if isinstance(entry, dict)
              for value in credentials.secret_values(entry) if len(value) >= MINIMUM_MASKED_LENGTH}
    return sorted(values, key=len, reverse=True)


def mask_secrets(text: str, secrets: list[str]) -> str:
    for secret in secrets:
        text = text.replace(secret, MASK)
    return text


def build_payload(reply: dict, secrets: list[str]) -> dict:
    """Child's reply > common result. Mask secret values in result, error and stdout and truncate them"""
    stdout_text = mask_secrets(reply.get("stdout") or "", secrets)[-MAXIMUM_STDOUT_CHARS:]
    base = {"action": "script", "url": reply.get("url")}
    if stdout_text:
        base["stdout"] = stdout_text
    if not reply.get("ok"):
        return base | {"ok": False, "code": "script_failed", "error": mask_secrets(reply.get("error") or "", secrets),
                       "next": "Fix the snippet and call again. For a common task, check web --help for a built-in action"}
    result_text = mask_secrets(reply.get("result_text") or "null", secrets)
    is_truncated = len(result_text) > MAXIMUM_RESULT_CHARS
    captured = {"requests": reply["requests"]} if "requests" in reply else {}
    return base | captured | {
                   "result": result_text[:MAXIMUM_RESULT_CHARS] if is_truncated else json.loads(result_text),
                   "result_truncated": is_truncated, "title": reply.get("title"),
                   "summary": "Ran the snippet" + (" (result truncated — too long)" if is_truncated else ""),
                   "next": "web text  # read the changed screen"}


def execute(args, state: dict, state_file) -> int:
    code, failure = read_snippet(args.file)
    if failure:
        return out(failure | {"action": "script"})
    # A snippet can do anything — never run it without approval in a read-only session
    if state.get("readonly") and not args.confirm_mutating:
        return out({"ok": False, "code": "mutating_blocked", "action": "script",
                    "error": "Did not run the snippet: read-only session (cannot tell what it would change)",
                    "next": "If the snippet only reads, tell the user and add --confirm-mutating"})
    request = json.dumps({"state": state, "code": code, "timeout_seconds": args.timeout,
                          "capture_requests": bool(args.capture_requests)})
    secrets = saved_secret_values()
    limit_megabytes = browser_memory.resolve_limit_megabytes(getattr(args, "memory_limit_mb", None))
    browser_pid = _int_or_none(state.get("pid"))
    # Signals cannot safely interrupt Playwright waits — kill the whole child process
    run = browser_memory.run_with_memory_cap([sys.executable, script_runner.__file__], request,
                                             args.timeout + CONNECT_GRACE_SECONDS, browser_pid, limit_megabytes,
                                             env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    if run["status"] == "memory_exceeded":
        return out(_memory_exceeded_payload(run["rss_megabytes"], limit_megabytes, browser_pid, state, state_file))
    if run["status"] == "timeout":
        return out({"ok": False, "code": "script_timeout", "action": "script",
                    "error": f"Did not finish within {args.timeout}s (stopped the run)",
                    "next": "Raise --timeout or shorten the waits inside the snippet"})
    lines = [line for line in run["stdout"].splitlines() if line.strip()]
    try:
        reply = json.loads(lines[-1])
    except (IndexError, ValueError):
        error_lines = (run["stderr"] or "").strip().splitlines()
        return out({"ok": False, "code": "script_failed", "action": "script",
                    "error": mask_secrets(error_lines[-1] if error_lines else "The child process exited without a reply", secrets)})
    if "code" in reply and not reply.get("ok", True):   # Could not attach (browser_gone etc.) — pass it through
        return out(reply)
    _remember_document(state_file, reply.get("time_origin"))
    payload = build_payload(reply, secrets)
    if reply.get("page_reloaded"):
        tabs.attach_reload_notice(payload, reply["page_reloaded"])
    return out(payload)


def _remember_document(state_file, time_origin: float | None) -> None:
    """Update only the document time in this session's tab record — so the next command does not report a snippet's reload as someone else's"""
    fresh = read_state(state_file) if state_file.is_file() else {}
    mark = (fresh.get("tab_marks") or {}).get(tabs.mark_key())
    if mark and time_origin is not None:
        mark["time_origin"] = time_origin
        write_state(state_file, fresh)


def _int_or_none(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _memory_exceeded_payload(rss_megabytes: int, limit_megabytes: int, browser_pid: int | None,
                             state: dict, state_file) -> dict:
    """Snippet already killed > stop the bloated browser too (the renderer holds the memory) > remove only the stopped browser's info from state."""
    is_browser_alive = kill_browser(browser_pid) if browser_pid else False
    if browser_pid and not is_browser_alive:
        # Viewport and rules were set by a person, so keep them (same as browser_gone handling)
        for key in ("cdp", "pid"):
            state.pop(key, None)
        write_state(state_file, state)
    return {"ok": False, "code": "browser_memory_exceeded", "action": "script",
            "rss_megabytes": rss_megabytes, "limit_megabytes": limit_megabytes,
            "browser_closed": bool(browser_pid) and not is_browser_alive,
            "error": f"Browser memory reached {rss_megabytes}MB, over the {limit_megabytes}MB limit — stopped the snippet and closed the browser",
            "hint": "Bulk collection: do not open thousands of pages in the browser — export the cookies to a file and collect over HTTP "
                    "(references/web.md, 'Bulk collection'). Set the limit with --memory-limit-mb or "
                    f"{browser_memory.BROWSER_MEMORY_LIMIT_ENV}",
            "next": "web open  # relaunch with the same profile (the login stays in the profile)"}


def configure(p) -> None:
    p.add_argument("--file", default=None, help="Playwright snippet to run (.py). Omitted or - reads standard input")
    p.add_argument("--memory-limit-mb", dest="memory_limit_mb", type=int, default=None,
                   help=f"Browser memory limit in MB, child processes included (default {browser_memory.DEFAULT_BROWSER_MEMORY_LIMIT_MEGABYTES}, "
                        f"env var {browser_memory.BROWSER_MEMORY_LIMIT_ENV}). Past it, stops the snippet and closes the browser")
    p.add_argument("--timeout", type=int, default=DEFAULT_SCRIPT_SECONDS,
                   help=f"Run limit in seconds (default {DEFAULT_SCRIPT_SECONDS}). Past it, stops with script_timeout")


ACTION = Action(name="script", run=execute, needs="state_online", configure=configure,
                options=("confirm_mutating", "capture_requests"),
                help="Run a Playwright snippet with the attached browser's page and context (for tasks no built-in action covers)",
                example="web script --file count_rows.py")
