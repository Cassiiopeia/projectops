"""`web script` — 붙은 브라우저의 page · context 로 Playwright 조각을 실행한다 (#904).

고정 동작에 없는 긴 꼬리는 agent 가 CDP 연결 스크립트를 처음부터 짰다(108개 세션 중 31개, 654번).
조각 계약: 이름 page · context 를 쓴다. 마지막 줄이 식이면 그 값, 아니면 변수 result 가 결과다.
흐름: 조각 읽기 > 읽기 전용 막기 > 자식 프로세스(script_runner)가 붙어서 실행 > 상한 넘으면 죽임 > 자격증명 값 가림
print 는 stdout 필드로 모은다(JSON 출력을 깨지 않게).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import credentials

from pro_launch.commands.web import script_runner
from pro_launch.registry import Action
from pro_launch.runtime.output import out

# 기본 실행 상한(초)
DEFAULT_SCRIPT_SECONDS = 60
# 붙기·재설치에 더 주는 시간(초) — 조각 상한과 따로
CONNECT_GRACE_SECONDS = 5
# 결과 · stdout 을 싣는 최대 글자 수
MAXIMUM_RESULT_CHARS = 20000
MAXIMUM_STDOUT_CHARS = 4000
MASK = "***"
# 가릴 비밀 값의 최소 길이 — 짧은 값은 평범한 글자까지 가린다
MINIMUM_MASKED_LENGTH = 4


def read_snippet(file_name: str | None) -> tuple[str | None, dict | None]:
    """--file 또는 표준 입력에서 조각을 읽는다. (코드, 실패 결과)"""
    if file_name and file_name != "-":
        path = Path(file_name).expanduser()
        if not path.is_file():
            return None, {"ok": False, "code": "file_not_found", "file": file_name,
                          "error": f"{file_name} 파일이 없습니다"}
        return path.read_text(encoding="utf-8"), None
    if sys.stdin is None or sys.stdin.isatty():
        return None, {"ok": False, "code": "script_required",
                      "error": "--file 로 조각 파일을 주거나 표준 입력으로 넘겨 주세요",
                      "next": "web script --file snippet.py"}
    return sys.stdin.read(), None


def saved_secret_values() -> list[str]:
    """저장된 모든 자격증명의 비밀 값 (긴 것부터). 못 읽으면 빈 목록"""
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
    """자식의 답 > 공통 결과. 결과 · 오류 · stdout 의 비밀 값을 가리고 길이를 자른다"""
    stdout_text = mask_secrets(reply.get("stdout") or "", secrets)[-MAXIMUM_STDOUT_CHARS:]
    base = {"action": "script", "url": reply.get("url")}
    if stdout_text:
        base["stdout"] = stdout_text
    if not reply.get("ok"):
        return base | {"ok": False, "code": "script_failed", "error": mask_secrets(reply.get("error") or "", secrets),
                       "next": "조각을 고쳐 다시 부른다. 자주 쓰는 일이면 고정 동작이 있는지 web --help 로 본다"}
    result_text = mask_secrets(reply.get("result_text") or "null", secrets)
    is_truncated = len(result_text) > MAXIMUM_RESULT_CHARS
    captured = {"requests": reply["requests"]} if "requests" in reply else {}
    return base | captured | {
                   "result": result_text[:MAXIMUM_RESULT_CHARS] if is_truncated else json.loads(result_text),
                   "result_truncated": is_truncated, "title": reply.get("title"),
                   "summary": "조각을 실행했다" + (" (결과가 길어 잘랐다)" if is_truncated else ""),
                   "next": "web text  # 바뀐 화면을 읽는다"}


def execute(args, state: dict, state_file) -> int:
    code, failure = read_snippet(args.file)
    if failure:
        return out(failure | {"action": "script"})
    # 조각은 무엇이든 할 수 있다 — 읽기 전용 세션에서는 승인 없이 돌리지 않는다
    if state.get("readonly") and not args.confirm_mutating:
        return out({"ok": False, "code": "mutating_blocked", "action": "script",
                    "error": "읽기 전용 세션이라 조각을 실행하지 않았습니다 (무엇을 바꿀지 알 수 없다)",
                    "next": "읽기만 하는 조각이면 사용자에게 알리고 --confirm-mutating 을 붙인다"})
    request = json.dumps({"state": state, "code": code, "timeout_seconds": args.timeout,
                          "capture_requests": bool(args.capture_requests)})
    secrets = saved_secret_values()
    try:
        # 신호로는 Playwright 대기를 안전하게 끊을 수 없다 — 자식 프로세스째 죽인다
        completed = subprocess.run([sys.executable, script_runner.__file__], input=request, capture_output=True,
                                   text=True, encoding="utf-8", timeout=args.timeout + CONNECT_GRACE_SECONDS,
                                   env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    except subprocess.TimeoutExpired:
        return out({"ok": False, "code": "script_timeout", "action": "script",
                    "error": f"{args.timeout}초 안에 끝나지 않았습니다 (실행을 멈췄다)",
                    "next": "--timeout 을 늘리거나 조각 안의 기다림을 줄인다"})
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    try:
        reply = json.loads(lines[-1])
    except (IndexError, ValueError):
        error_lines = (completed.stderr or "").strip().splitlines()
        return out({"ok": False, "code": "script_failed", "action": "script",
                    "error": mask_secrets(error_lines[-1] if error_lines else "자식 프로세스가 답 없이 끝났다", secrets)})
    if "code" in reply and not reply.get("ok", True):   # 붙지 못했다 (browser_gone 등) — 그대로 낸다
        return out(reply)
    return out(build_payload(reply, secrets))


def configure(p) -> None:
    p.add_argument("--file", default=None, help="실행할 Playwright 조각 (.py). 없거나 - 면 표준 입력")
    p.add_argument("--timeout", type=int, default=DEFAULT_SCRIPT_SECONDS,
                   help=f"실행 상한(초, 기본 {DEFAULT_SCRIPT_SECONDS}). 넘으면 멈추고 script_timeout")


ACTION = Action(name="script", run=execute, needs="state_online", configure=configure,
                options=("confirm_mutating", "capture_requests"),
                help="붙은 브라우저의 page · context 로 Playwright 조각을 실행한다 (고정 동작에 없는 일)",
                example="web script --file count_rows.py")
