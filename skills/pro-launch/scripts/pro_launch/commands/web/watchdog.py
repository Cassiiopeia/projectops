"""web 명령의 실행 시간 상한 — 멈추면 `browser_hung` JSON 하나를 내고 프로세스를 끝낸다 (#921).

CDP `/json/version` 은 답하는데 `connect_over_cdp` · `ctx.pages` 가 끝없이 멈춘 일이 있었다(2분+, --timeout 무시).
Playwright 동기 API 는 신호로 안전하게 끊기지 않는다(script_runner 실측) — 그래서 감시 스레드가 시간을 보고
상한을 넘으면 결과를 직접 내고 `os._exit` 로 끝낸다. 드라이버(node)는 파이프가 닫히면 스스로 끝난다.

상한 2개: 붙기 단계(CONNECT_DEADLINE_SECONDS) · 명령 전체(동작 대기 + 여유, 최소 90초 · 최대 420초 + 사용자 인계 시간).
멈춘 브라우저는 상태 파일에 hung_at 을 남겨 다음 web open 이 다시 붙지 않고 끄고 새로 띄우게 한다.
"""
from __future__ import annotations

import contextlib
import json
import os
import sys
import threading
import time

from pro_launch.runtime.browser import read_state, write_state
from pro_launch.runtime.output import out

# 붙기(connect_over_cdp · 탭 고르기 · 훅 재설치) 상한(초) — 정상이면 3초 안쪽
CONNECT_DEADLINE_SECONDS = 30
# 동작 대기(--timeout)에 더 주는 여유(초) — 로드 대기 · 제목 읽기 · 결과 정리
ACTION_MARGIN_SECONDS = 60
# 명령 전체 상한의 하한 · 상한(초). 하한은 Bash 도구 120초 제한보다 먼저 끝나게
MINIMUM_DEADLINE_SECONDS = 90
MAXIMUM_DEADLINE_SECONDS = 420
# web login 사용자 인계 대기 상한(초) — CLI 한 번이 무한히 붙잡지 않게 (login.py 가 같은 값을 쓴다)
MAXIMUM_HANDOFF_SECONDS = 600
# 새로 띄우는 open 의 포트 대기 몫(초)
LAUNCH_EXTRA_SECONDS = 20
# 감시 간격(초)
POLL_SECONDS = 0.25
# 상태 파일: 멈춘 것으로 판정한 시각 — 다음 open 이 재사용하지 않고 끈다
HUNG_MARK_KEY = "hung_at"

_ACTIVE: dict = {}


def deadline_seconds(args, needs: str) -> int:
    """명령 전체 상한: max(하한, 동작 대기 + 여유) + 동작별 추가(키 입력 · 연속 캡처 · 새로 띄우기 · 사용자 인계), 최대 상한."""
    timeout = getattr(args, "timeout", None) or 0
    # web login --handoff-seconds: 사용자가 2단계 인증을 마치는 시간 — 상한에도 그만큼 더한다 (90초에 끊기던 것)
    handoff_seconds = min(max(getattr(args, "handoff_seconds", None) or 0, 0), MAXIMUM_HANDOFF_SECONDS)
    extra = handoff_seconds
    keys_text = getattr(args, "keys", None) or ""
    delay_milliseconds = getattr(args, "delay_ms", None) or 0
    extra += len(keys_text or getattr(args, "text", None) or "") * delay_milliseconds / 1000
    extra += (getattr(args, "tiles", None) or 0) * 3
    if needs == "launch":
        extra += LAUNCH_EXTRA_SECONDS
    total = max(MINIMUM_DEADLINE_SECONDS, timeout + ACTION_MARGIN_SECONDS) + extra
    return int(min(total, MAXIMUM_DEADLINE_SECONDS + handoff_seconds))


class Watchdog:
    """명령 하나를 지켜본다. 단계(connect · action)마다 상한을 보고 넘으면 fire."""

    def __init__(self, action: str, total_seconds: int, state_file) -> None:
        self.action = action
        self.total_seconds = total_seconds
        self.state_file = state_file
        self.started = time.monotonic()
        self.phase = "action"
        self.connect_started: float | None = None
        self.stop_event = threading.Event()

    def start(self) -> "Watchdog":
        threading.Thread(target=self._watch, name="web-watchdog", daemon=True).start()
        _ACTIVE["watchdog"] = self
        return self

    def cancel(self) -> None:
        self.stop_event.set()
        _ACTIVE.pop("watchdog", None)

    def _watch(self) -> None:
        while not self.stop_event.wait(POLL_SECONDS):
            now = time.monotonic()
            is_connect_over = (self.phase == "connect" and self.connect_started is not None
                               and now - self.connect_started > CONNECT_DEADLINE_SECONDS)
            if is_connect_over or now - self.started > self.total_seconds:
                self._fire(now)
                return

    def _fire(self, now: float) -> None:
        """멈춤 결과를 내고 끝낸다 (상태 파일에 hung_at 표시 > JSON 하나 > os._exit)."""
        state = read_state(self.state_file) if self.state_file and self.state_file.is_file() else {}
        limit = CONNECT_DEADLINE_SECONDS if self.phase == "connect" else self.total_seconds
        if state.get("pid"):
            state[HUNG_MARK_KEY] = time.strftime("%Y-%m-%d %H:%M:%S")
            with contextlib.suppress(OSError):
                write_state(self.state_file, state)
        payload = {"ok": False, "code": "browser_hung", "action": self.action, "phase": self.phase,
                   "pid": state.get("pid"), "profile": state.get("profile"), "cdp": state.get("cdp"),
                   "elapsed_seconds": round(now - self.started, 1), "deadline_seconds": limit,
                   "url": None,
                   "error": (f"Attaching to the browser did not finish within {limit}s (CDP answers but the connection is hung)"
                             if self.phase == "connect" else
                             f"web {self.action} did not finish within {limit}s and was stopped"),
                   "hint": "Marked the browser as hung — the next web open kills it and starts a new one instead of reattaching (profile and logins are kept)",
                   "next": "web open  # kills the hung browser and restarts it with the same profile"}
        try:
            exit_code = out(payload)
        except Exception:
            print(json.dumps(payload, ensure_ascii=False))
            exit_code = 1
        with contextlib.suppress(Exception):
            sys.stdout.flush()
        os._exit(exit_code if isinstance(exit_code, int) else 1)


@contextlib.contextmanager
def connect_phase():
    """붙기 단계 표시 — 감시 중이면 이 안에서 붙기 상한을 본다. 감시가 없으면(자식 프로세스 등) 아무 일도 안 한다."""
    watchdog = _ACTIVE.get("watchdog")
    if watchdog is None:
        yield
        return
    previous_phase = watchdog.phase
    watchdog.connect_started = time.monotonic()
    watchdog.phase = "connect"
    try:
        yield
    finally:
        watchdog.phase = previous_phase
        watchdog.connect_started = None
