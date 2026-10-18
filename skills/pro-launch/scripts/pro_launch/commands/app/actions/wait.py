"""`app wait` — 화면에 요소가 나타나거나(--gone 이면 사라질) 때까지 기다린다 (#928)."""
from __future__ import annotations

import time

import app_input

from pro_launch.commands.app.gestures import backend_for, device_failure_response, elapsed_seconds
from pro_launch.registry import Action
from pro_launch.runtime.output import out

# 기본 대기 · 상한 (초) / 화면 다시 읽기 간격 기본 · 하한 (초)
DEFAULT_WAIT_TIMEOUT_SECONDS = 30
MAXIMUM_WAIT_TIMEOUT_SECONDS = 300
DEFAULT_POLL_INTERVAL_SECONDS = 1.0
MINIMUM_POLL_INTERVAL_SECONDS = 0.2


def _app_wait(args) -> int:
    """대상 고르기 > 기기·백엔드 > 조건이 될 때까지 화면 구조를 다시 읽기 > 결과."""
    selector = next(((f, getattr(args, f"sel_{f}")) for f in app_input.SELECTOR_FIELDS
                     if getattr(args, f"sel_{f}", None)), None)
    if not selector:
        return out({"ok": False, "code": "target_required",
                    "error": "--text · --id · --desc 중 하나가 필요하다",
                    "next": "app tree  # 기다릴 요소의 문구를 본다"})
    timeout = getattr(args, "timeout", None) or DEFAULT_WAIT_TIMEOUT_SECONDS
    if not 0 < timeout <= MAXIMUM_WAIT_TIMEOUT_SECONDS:
        return out({"ok": False, "code": "timeout_too_large",
                    "error": f"--timeout 은 초 단위 1~{MAXIMUM_WAIT_TIMEOUT_SECONDS} 이다 (받은 값 {timeout})"})
    interval = max(getattr(args, "interval", None) or DEFAULT_POLL_INTERVAL_SECONDS, MINIMUM_POLL_INTERVAL_SECONDS)
    be, dev_id, err = backend_for(args)
    if err is not None:
        return err
    field, value = selector
    should_be_gone = bool(getattr(args, "gone", False))
    condition = f"{field}={value!r} " + ("gone" if should_be_gone else "visible")
    started = time.monotonic()
    deadline = started + timeout
    polls = 0
    while True:
        nodes = be.nodes(dev_id) or []
        polls += 1
        matches = app_input.match_nodes(nodes, field, value)
        # 화면 구조를 못 읽은 것은 '사라졌다'가 아니다
        if (matches and not should_be_gone) or (should_be_gone and nodes and not matches):
            return out({"ok": True, "code": "ok", "device": dev_id, "via": be.name, "condition": condition,
                        "polls": polls, "waited_seconds": round(time.monotonic() - started, 1),
                        "elapsed_seconds": elapsed_seconds(args),
                        "summary": f"{field}={value!r} " + ("사라짐" if should_be_gone else "나타남"),
                        "next": "app shot  # 화면 확인"})
        if time.monotonic() >= deadline:
            break
        time.sleep(interval)
    if not nodes and getattr(be, "device_failure", None):
        return device_failure_response(be, dev_id, args)
    return out({"ok": False, "code": "wait_timeout", "device": dev_id, "via": be.name,
                "condition": condition, "polls": polls, "timeout_seconds": timeout,
                "elapsed_seconds": elapsed_seconds(args),
                "error": f"{timeout}초 동안 {field}={value!r} 가 " + ("사라지지 않았다" if should_be_gone else "나타나지 않았다"),
                "next": "app shot 으로 화면을 보고 문구를 확인한다 (app tree)"})


def configure(p) -> None:
    # --text · --id · --desc 는 tap 이, --timeout 은 flow 가 이미 정의했다 (app 은 파서 하나를 같이 쓴다)
    p.add_argument("--gone", action="store_true", help="wait: 나타날 때가 아니라 사라질 때까지")
    p.add_argument("--interval", type=float, default=None,
                   help=f"wait: 화면을 다시 읽는 간격 초 (기본 {DEFAULT_POLL_INTERVAL_SECONDS:g})")


ACTION = Action(name="wait", run=_app_wait, configure=configure,
                help="요소(--text·--id·--desc)가 나타날 때까지, --gone 이면 사라질 때까지 기다린다 (--timeout 초)",
                example='app wait --device $DEV --text "로드 중" --gone --timeout 40')
