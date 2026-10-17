"""`web` 의 공통 옵션 표 — 동작은 이 이름으로 자기가 쓰는 것을 고른다 (`Action.options`, #896).

한 동작만 쓰는 옵션은 그 동작의 `configure` 에 둔다. 둘 이상이 쓰면 여기로 올린다.
"""
from __future__ import annotations

from pro_launch.runtime.shots import add_shot_args


def _root(p) -> None:
    p.add_argument("--root", default=".", help="프로젝트 루트 (상태 파일 위치)")


def _url(p) -> None:
    p.add_argument("--url", default=None, help="주소")


def _selector(p) -> None:
    p.add_argument("--selector", default=None,
                   help="대상 선택자. text=로그인 · #id · button:has-text('x')")


def _ref(p) -> None:
    p.add_argument("--ref", type=int, default=None,
                   help="web find · web inspect 가 준 번호. 선택자 추측 대신 이것을 쓴다")


def _text(p) -> None:
    p.add_argument("--text", default=None, help="입력할 값 또는 찾을·확인할 문구")


def _secret_text(p) -> None:
    # 비밀번호를 --text 에 적으면 세션 기록에 평문으로 남는다(#604)
    p.add_argument("--cred", default=None, help="저장된 로그인 정보로 입력한다 (cred list). 값은 명령줄에 남지 않는다")
    p.add_argument("--cred-field", dest="cred_field", default=None,
                   help="--cred 에서 넣을 필드 (기본 password, 예: account)")
    p.add_argument("--text-env", dest="text_env", default=None,
                   help="입력값을 환경변수에서 읽는다 — 비밀번호는 반드시 이쪽")


def _timeout(p) -> None:
    p.add_argument("--timeout", type=int, default=10, help="대기 제한(초)")


def _target_timeout(p) -> None:
    # 추측한 선택자가 매번 10초를 다 쓰던 것을 줄인다 (#888). 기본값 계산은 element.py 의 *_wait_seconds
    p.add_argument("--timeout", type=int, default=None,
                   help="대기 제한(초). 기본: 대상 요소 4초 · 누른 뒤 결과(--expect-* · 내려받기) 10초. 주면 둘 다 이 값")


def _frame(p) -> None:
    # 교차 출처 iframe 안의 로그인 폼 등 — 최상위 문서 선택자로는 안이 안 보인다 (#877)
    p.add_argument("--frame", default=None,
                   help="iframe 안에서 한다: 프레임 이름 · iframe 선택자 · 주소 일부 (못 찾으면 frames 목록)")


def _clear(p) -> None:
    p.add_argument("--clear", action="store_true", help="지정을 푼다")


def _out(p) -> None:
    p.add_argument("--out", default=None, help="이름(→ $SHOT_DIR 아래) 또는 경로")


def _confirm_mutating(p) -> None:
    p.add_argument("--confirm-mutating", dest="confirm_mutating", action="store_true",
                   help="읽기 전용 세션에서도 한다 (사용자 승인을 받은 뒤에만)")


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
}

# 모든 동작이 받는 것
ALWAYS_OPTIONS = ("root",)
