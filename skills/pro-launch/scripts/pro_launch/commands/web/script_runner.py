"""Child process of `web script` — attaches, runs the snippet and prints one JSON line (#904).

If the parent (actions/script.py) passes the time limit, it kills this whole process.
Interrupting the Playwright sync API with a signal leaves the event loop spinning (observed: stuck at 60% CPU) — hence a separate process.
Input (stdin JSON): state, code, timeout_seconds. Output (last stdout line): ok, result_text | error, stdout, url, title
"""
from __future__ import annotations

import ast
import contextlib
import io
import json
import sys
from pathlib import Path

# Variable name the snippet stores its result in
RESULT_VARIABLE = "result"


def compile_snippet(code: str):
    """(body code, last-expression code or None). If the last line is an expression, its value is the result"""
    tree = ast.parse(code, filename="<web script>", mode="exec")
    last_expression = None
    if tree.body and isinstance(tree.body[-1], ast.Expr):
        last_expression = ast.Expression(tree.body.pop().value)
    body = compile(tree, "<web script>", "exec")
    tail = compile(last_expression, "<web script>", "eval") if last_expression else None
    return body, tail


def run_snippet(code: str, namespace: dict):
    """Run the snippet and return the result value"""
    body, tail = compile_snippet(code)
    exec(body, namespace)
    return eval(tail, namespace) if tail else namespace.get(RESULT_VARIABLE)


def first_error_line(error: BaseException) -> str:
    """Exception > 'Type: first line' (first line only, since the call log after it may contain input values)"""
    lines = str(error).strip().splitlines()
    return f"{type(error).__name__}: {lines[0][:300]}" if lines else type(error).__name__


def to_json_text(value) -> str:
    """Result value > JSON text. str for anything not JSON-serializable"""
    return json.dumps(value, ensure_ascii=False, default=str)


def main() -> int:
    request = json.loads(sys.stdin.read())
    from pro_launch.commands.web.session import read_url_title, web_connect
    # Attaching and reinstalling (hooks, stealth, viewport, rules, dialogs) is the same as other actions
    connection, failure = web_connect(request["state"])
    if failure:
        print(json.dumps(failure, ensure_ascii=False))
        return 0
    playwright, _browser, page = connection
    from pro_launch.commands.web.tabs import read_time_origin, reload_notice
    reloaded = reload_notice(page, request["state"])
    captured = io.StringIO()
    # Non-GET requests the snippet caused (--capture-requests, #930)
    from pro_launch.commands.web.request_capture import RequestCapture
    capture = RequestCapture().attach(page) if request.get("capture_requests") else None
    try:
        # Keep Playwright waits inside the snippet under the limit too
        page.set_default_timeout(request["timeout_seconds"] * 1000)
        namespace = {"page": page, "context": page.context, "__name__": "__web_script__"}
        with contextlib.redirect_stdout(captured):
            value = run_snippet(request["code"], namespace)
        url, title = read_url_title(page, timeout=3)
        reply = {"ok": True, "result_text": to_json_text(value), "url": url, "title": title}
    except Exception as error:
        reply = {"ok": False, "error": first_error_line(error), "url": page.url}
    finally:
        if capture is not None:
            reply_requests = capture.finish()
        # The snippet may have navigated or reloaded itself — return the current document so the next command doesn't report it as "spontaneous"
        time_origin = read_time_origin(page)
        playwright.stop()
    if capture is not None:
        reply["requests"] = reply_requests
    reply["stdout"] = captured.getvalue()
    reply["time_origin"] = time_origin
    if reloaded:
        reply["page_reloaded"] = reloaded
    print(json.dumps(reply, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    # Put scripts/ on the path — this file lives in scripts/pro_launch/commands/web/
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    sys.exit(main())
