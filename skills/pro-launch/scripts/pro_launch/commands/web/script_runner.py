"""`web script` 의 자식 프로세스 — 붙어서 조각을 돌리고 JSON 한 줄을 낸다 (#904).

부모(actions/script.py)가 시간 상한을 넘기면 이 프로세스를 통째로 죽인다.
Playwright 동기 API 는 신호로 끊으면 이벤트 루프가 헛돈다(실측: CPU 60% 로 멈춤) — 그래서 프로세스를 나눴다.
입력(stdin JSON): state · code · timeout_seconds. 출력(stdout 마지막 줄): ok · result_text | error · stdout · url · title
"""
from __future__ import annotations

import ast
import contextlib
import io
import json
import sys
from pathlib import Path

# 조각이 결과를 담는 변수 이름
RESULT_VARIABLE = "result"


def compile_snippet(code: str):
    """(본문 코드, 마지막 식 코드 또는 None). 마지막 줄이 식이면 그 값이 결과다"""
    tree = ast.parse(code, filename="<web script>", mode="exec")
    last_expression = None
    if tree.body and isinstance(tree.body[-1], ast.Expr):
        last_expression = ast.Expression(tree.body.pop().value)
    body = compile(tree, "<web script>", "exec")
    tail = compile(last_expression, "<web script>", "eval") if last_expression else None
    return body, tail


def run_snippet(code: str, namespace: dict):
    """조각을 실행하고 결과 값을 돌려준다"""
    body, tail = compile_snippet(code)
    exec(body, namespace)
    return eval(tail, namespace) if tail else namespace.get(RESULT_VARIABLE)


def first_error_line(error: BaseException) -> str:
    """예외 > 'Type: 첫 줄' (호출 기록 뒤쪽에 입력값이 섞일 수 있어 첫 줄만)"""
    lines = str(error).strip().splitlines()
    return f"{type(error).__name__}: {lines[0][:300]}" if lines else type(error).__name__


def to_json_text(value) -> str:
    """결과 값 > JSON 글. JSON 으로 못 바꾸는 것은 str"""
    return json.dumps(value, ensure_ascii=False, default=str)


def main() -> int:
    request = json.loads(sys.stdin.read())
    from pro_launch.commands.web.session import read_url_title, web_connect
    # 붙기 · 재설치(훅·stealth·뷰포트·규칙·대화상자)는 다른 동작과 같다
    connection, failure = web_connect(request["state"])
    if failure:
        print(json.dumps(failure, ensure_ascii=False))
        return 0
    playwright, _browser, page = connection
    captured = io.StringIO()
    # 조각이 일으킨 GET 이 아닌 요청 (--capture-requests, #930)
    from pro_launch.commands.web.request_capture import RequestCapture
    capture = RequestCapture().attach(page) if request.get("capture_requests") else None
    try:
        # 조각 안의 Playwright 대기도 상한을 넘지 않게
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
        playwright.stop()
    if capture is not None:
        reply["requests"] = reply_requests
    reply["stdout"] = captured.getvalue()
    print(json.dumps(reply, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    # scripts/ 를 경로에 넣는다 — 이 파일은 scripts/pro_launch/commands/web/ 에 있다
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    sys.exit(main())
