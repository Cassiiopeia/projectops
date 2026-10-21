"""`web` 의 공통 옵션 표 — 동작은 이 이름으로 자기가 쓰는 것을 고른다 (`Action.options`, #896).

한 동작만 쓰는 옵션은 그 동작의 `configure` 에 둔다. 둘 이상이 쓰면 여기로 올린다.
"""
from __future__ import annotations

from pro_launch.runtime.shots import add_shot_args


def _root(p) -> None:
    p.add_argument("--root", default=".", help="Project root (where the state file lives)")


def _url(p) -> None:
    p.add_argument("--url", default=None, help="URL")


def _selector(p) -> None:
    p.add_argument("--selector", default=None,
                   help="Target selector. text=Login · #id · button:has-text('x')")


def _ref(p) -> None:
    p.add_argument("--ref", type=int, default=None,
                   help="Number given by web find or web inspect. Use it instead of guessing a selector")


def _text(p) -> None:
    p.add_argument("--text", default=None, help="Value to type, or text to find or check")


def _secret_text(p) -> None:
    # 비밀번호를 --text 에 적으면 세션 기록에 평문으로 남는다(#604)
    p.add_argument("--cred", default=None, help="Type from a saved login (cred list). The value never appears on the command line")
    p.add_argument("--cred-field", dest="cred_field", default=None,
                   help="Field to type from --cred (default password, e.g. account)")
    p.add_argument("--text-env", dest="text_env", default=None,
                   help="Read the value from an environment variable — always use this for passwords")


def _timeout(p) -> None:
    p.add_argument("--timeout", type=int, default=10, help="Wait limit (seconds)")


def _target_timeout(p) -> None:
    # 추측한 선택자가 매번 10초를 다 쓰던 것을 줄인다 (#888). 기본값 계산은 element.py 의 *_wait_seconds
    p.add_argument("--timeout", type=int, default=None,
                   help="Wait limit (seconds). Default: 4 s for the target element, 10 s for the result after the press (--expect-*, downloads). If given, both use this value")


def _frame(p) -> None:
    # 교차 출처 iframe 안의 로그인 폼 등 — 최상위 문서 선택자로는 안이 안 보인다 (#877)
    p.add_argument("--frame", default=None,
                   help="Act inside an iframe: frame name, iframe selector or part of its url (lists frames if not found)")


def _clear(p) -> None:
    p.add_argument("--clear", action="store_true", help="Clear the setting")


def _out(p) -> None:
    p.add_argument("--out", default=None, help="Name (saved under $SHOT_DIR) or path")


def _confirm_mutating(p) -> None:
    p.add_argument("--confirm-mutating", dest="confirm_mutating", action="store_true",
                   help="Act even in a read-only session (only after the user approves)")


def _capture_requests(p) -> None:
    # 저장이 정말 서버로 갔는지 page.on("response") 를 손으로 걸던 것 (#930)
    p.add_argument("--capture-requests", dest="capture_requests", action="store_true",
                   help="Add the non-GET requests this action caused (method · status · url) to the result's requests")


# 공통 옵션 이름 → 파서에 다는 함수. 이름은 Action.options 에 적는 값이다
SHARED_OPTIONS = {
    "root": _root,
    "url": _url,
    "selector": _selector,
    "ref": _ref,
    "text": _text,
    "secret_text": _secret_text,
    "timeout": _timeout,
    # 요소를 조작하는 동작(click · type · check · select · hover · press · download)의 --timeout.
    # timeout 과 같은 플래그라 한 동작에 둘 중 하나만 적는다. 위 timeout 보다 뒤에 둬야 미선언 동작의 기본값이 10 으로 남는다
    "target_timeout": _target_timeout,
    "frame": _frame,
    "clear": _clear,
    "out": _out,
    "confirm_mutating": _confirm_mutating,
    "shot_format": add_shot_args,
    "capture_requests": _capture_requests,
}

# 모든 동작이 받는 것
ALWAYS_OPTIONS = ("root",)


# --timeout 상한(초). 넘으면 밀리초로 잘못 준 것으로 본다 — 3000 은 50분 (#931 실측: 공유 브라우저를 50분 붙잡았다)
MAXIMUM_TIMEOUT_SECONDS = 300


def timeout_failure(args) -> dict | None:
    """--timeout 이 상한을 넘으면 timeout_too_large 결과, 아니면 None. 모든 web 동작이 붙기 전에 본다."""
    timeout = getattr(args, "timeout", None)
    if timeout is None or timeout <= MAXIMUM_TIMEOUT_SECONDS:
        return None
    return {"ok": False, "code": "timeout_too_large", "action": getattr(args, "action", None),
            "timeout": timeout, "maximum_seconds": MAXIMUM_TIMEOUT_SECONDS,
            "error": f"--timeout {timeout} is too long (the unit is seconds — {timeout} s is about {round(timeout / 60)} min)",
            "hint": (f"Give seconds, not milliseconds (e.g. 5000ms → --timeout 5). Maximum {MAXIMUM_TIMEOUT_SECONDS} s. "
                     "To wait longer, call web wait again"),
            "next": f"web {getattr(args, 'action', '<action>')} --timeout {min(max(timeout // 1000, 1), MAXIMUM_TIMEOUT_SECONDS)}"}
