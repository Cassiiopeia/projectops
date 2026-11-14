"""Time limit for web commands — on a hang, emit one `browser_hung` JSON and end the process (#921).

CDP `/json/version` answered while `connect_over_cdp` / `ctx.pages` hung forever (2+ minutes, ignoring --timeout).
The Playwright sync API can't be safely interrupted by signals (observed in script_runner) — so a watchdog thread tracks time,
emits the result itself when the limit passes and ends with `os._exit`. The driver (node) exits by itself when the pipe closes.

Two limits: attach phase (CONNECT_DEADLINE_SECONDS) and whole command (action wait + margin, min 90s, max 420s + user handoff time).
A hung browser leaves hung_at in the state file so the next web open kills and relaunches instead of reattaching.
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

# Limit (seconds) for attaching (connect_over_cdp, picking a tab, reinstalling hooks) — normally under 3 seconds
CONNECT_DEADLINE_SECONDS = 30
# Extra margin (seconds) on top of the action wait (--timeout) — load wait, title read, result cleanup
ACTION_MARGIN_SECONDS = 60
# Lower and upper bound (seconds) of the whole-command limit. The lower bound ends before the Bash tool's 120s limit
MINIMUM_DEADLINE_SECONDS = 90
MAXIMUM_DEADLINE_SECONDS = 420
# Limit (seconds) for waiting on a web login user handoff — so one CLI call doesn't hold forever (login.py uses the same value)
MAXIMUM_HANDOFF_SECONDS = 600
# Share (seconds) for port waiting when open launches a new browser
LAUNCH_EXTRA_SECONDS = 20
# Watch interval (seconds)
POLL_SECONDS = 0.25
# State file: time it was judged hung — the next open kills it instead of reusing
HUNG_MARK_KEY = "hung_at"

_ACTIVE: dict = {}


def deadline_seconds(args, needs: str) -> int:
    """Whole-command limit: max(lower bound, action wait + margin) + per-action extras (key input, burst capture, fresh launch, user handoff), capped at the upper bound."""
    timeout = getattr(args, "timeout", None) or 0
    # web login --handoff-seconds: time for the user to finish 2-step verification — add it to the limit too (it used to cut off at 90s)
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
    """Watch one command. Checks the limit per phase (connect, action) and fires when exceeded."""

    def __init__(self, action: str, total_seconds: int, state_file) -> None:
        self.action = action
        self.total_seconds = total_seconds
        self.state_file = state_file
        self.started = time.monotonic()
        self.phase = "action"
        self.connect_started: float | None = None
        self.stop_event = threading.Event()
        # Browser this command drives — the hung mark goes only on it, not on one another session relaunched since
        self.watched_pid = None

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
        """Emit the hang result and exit (mark hung_at in the state file > one JSON > os._exit)."""
        state = read_state(self.state_file) if self.state_file and self.state_file.is_file() else {}
        limit = CONNECT_DEADLINE_SECONDS if self.phase == "connect" else self.total_seconds
        is_same_browser = self.watched_pid is None or str(state.get("pid")) == str(self.watched_pid)
        if state.get("pid") and is_same_browser:
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


def set_watched_browser(pid) -> None:
    """Tell the running watchdog which browser pid this command drives (no-op without a watchdog)."""
    watchdog = _ACTIVE.get("watchdog")
    if watchdog is not None:
        watchdog.watched_pid = pid


@contextlib.contextmanager
def connect_phase():
    """Mark the attach phase — while watched, the attach limit applies inside it. Does nothing when not watched (child processes etc.)."""
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
