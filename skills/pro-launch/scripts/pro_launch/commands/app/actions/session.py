"""`app session start|stop|status` — iOS 상주 Maestro 세션 (#894 2단계, 선택).

세션이 떠 있으면 iOS tap·swipe·tree·run 이 JVM 을 새로 띄우지 않고 그 세션을 쓴다 (호출당 20초 > 1초 안팎).
세션이 없으면 지금처럼 호출마다 Maestro 를 띄운다. 클라이언트는 scripts/maestro_session.py, 중계 프로세스는 scripts/maestro_session_relay.py.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import maestro_drivers
import maestro_runs
import maestro_session

from pro_launch.commands.app.gestures import backend_for, elapsed_seconds, host_load_fields
from pro_launch.registry import Action
from pro_launch.runtime import procs
from pro_launch.runtime.output import out

SESSION_VERBS = ("start", "stop", "status")
# 백그라운드로 띄울 중계 스크립트 (같은 폴더)
RELAY_SCRIPT = Path(maestro_session.__file__).with_name("maestro_session_relay.py")
# start: 중계가 maestro mcp 기동 + 기기 연결 예열을 끝낼 때까지 기다리는 최대 시간 (초)
START_WAIT_SECONDS = 150
START_POLL_SECONDS = 0.5
# stop: 정중히 끝내자는 요청 뒤 기다리는 시간 (초)
STOP_WAIT_SECONDS = 10
# 유휴 종료 허용 범위 (분)
MINIMUM_IDLE_MINUTES, MAXIMUM_IDLE_MINUTES = 1, 240


def _app_session(args) -> int:
    """세션 동사 고르기 > 기기·백엔드(iOS 만) > start · stop · status."""
    verb = getattr(args, "session_verb", None)
    if verb not in SESSION_VERBS:
        return out({"ok": False, "code": "session_verb_required",
                    "error": "One of start · stop · status is required",
                    "next": "app session start --device <UDID>"})
    be, dev_id, err = backend_for(args)
    if err is not None:
        return err
    if be.name != "ios":
        return out({"ok": False, "code": "unsupported_on_platform", "action": "session", "platform": be.name,
                    "device": dev_id, "error": "The resident session is iOS (Maestro) only — Android actions are already fast",
                    "next": "On Android use app tap·swipe·run as is, without a session"})
    if dev_id == "booted":
        return out({"ok": False, "code": "session_needs_udid", "error": "A session is bound to a device UDID ('booted' is not accepted)",
                    "next": "devices  # pass a UDID from ios_booted as --device"})
    if getattr(args, "kill_stale", False) and verb != "stop":
        return out({"ok": False, "code": "bad_args", "error": "--kill-stale is only for session stop",
                    "next": f"app session stop --device {dev_id} --kill-stale"})
    return {"start": _start, "stop": _stop, "status": _status}[verb](args, be, dev_id)


def _relay_state(dev_id: str) -> tuple[dict | None, bool]:
    """(상태, 중계가 살아 있나). 중계가 죽었는데 파일만 남았으면 걷어낸다."""
    session = maestro_session.read_session(dev_id)
    if session is None:
        return None, False
    pid = session.get("relay_pid")
    if pid and procs.pid_alive(int(pid)):
        return session, True
    # 중계만 강제로 죽었으면 maestro mcp(java)가 고아로 남는다 — 같은 프로세스 묶음이라 묶음째 끝낸다
    maestro_pid = session.get("maestro_pid")
    if pid and maestro_pid and procs.pid_alive(int(maestro_pid)):
        procs.kill_process_group(int(pid), grace=2.0)
    try:
        maestro_session.session_file(dev_id).unlink()
    except OSError:
        pass
    return session, False


def _start(args, be, dev_id: str) -> int:
    """중계 띄우기 > 상태 파일 ready·failed 대기 > 결과. 이미 떠 있으면 그대로 쓴다."""
    session, is_alive = _relay_state(dev_id)
    if is_alive and maestro_session.is_ready(session):
        return out(_session_payload(args, dev_id, session, summary="Using the session that is already running", is_already_running=True))
    if is_alive:
        return out({"ok": False, "code": "session_starting", "device": dev_id, "relay_pid": session.get("relay_pid"),
                    "error": "Another call is starting the session", "next": "app session status in a moment"})
    idle_minutes = getattr(args, "idle_minutes", None) or maestro_session.DEFAULT_IDLE_MINUTES
    if not MINIMUM_IDLE_MINUTES <= idle_minutes <= MAXIMUM_IDLE_MINUTES:
        return out({"ok": False, "code": "bad_idle_minutes",
                    "error": f"--idle-minutes must be {MINIMUM_IDLE_MINUTES}-{MAXIMUM_IDLE_MINUTES} minutes"})
    state_path = maestro_session.session_file(dev_id)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, str(RELAY_SCRIPT), "serve", "--device", dev_id,
               "--idle-minutes", str(idle_minutes), "--maestro", be._maestro(), "--state-file", str(state_path)]
    relay_pid = procs.spawn_detached(command, str(state_path.parent), state_path.with_suffix(".log"))
    # 예열 동안 maestro mcp 가 기기에 붙는다 — 이 구간도 pro-launch 실행으로 기록
    with maestro_runs.start_lock(), maestro_runs.recording():   # 다른 Maestro 시작과 겹치지 않게 (#922)
        session = _wait_until_settled(dev_id, relay_pid)
    if maestro_session.is_ready(session):
        return out(_session_payload(args, dev_id, session, summary="Session started — iOS tap·swipe·tree·run now use this session"))
    procs.kill_process_group(relay_pid, grace=2.0)
    reason = (session or {}).get("reason") or "session_start_timeout"
    failure = {"ok": False, "code": "session_start_failed", "device": dev_id, "reason": reason,
               "error": _failure_text(session, state_path), "tools_available": (session or {}).get("tools_available"),
                **_diagnostics(dev_id),
                "elapsed_seconds": elapsed_seconds(args),
                "next": "Carry on without a session (app tap·tree start Maestro on every call). "
                        "If device_unreachable, check whether another maestro is using the same device"}
    if failure.get("stale_maestro_drivers"):
        failure["next"] = (f"app session stop --device {dev_id} --kill-stale  # clean up leftover Maestro drivers, then "
                           "app session start again")
    elif failure.get("host_load"):
        failure["next"] = "Host load is high — retry once it drops (the driver start wait was already raised automatically)"
    if reason == "session_tools_missing":
        # 이 Maestro 버전의 MCP 도구 이름을 모른다 — 기동 실패와 다른 대처라 code 를 나눈다
        failure.update(code="session_tools_missing")
    return out(failure)


def _diagnostics(dev_id: str) -> dict:
    """세션 시작 실패에 붙일 진단: 남은 고아 드라이버 · 다른 Maestro · 호스트 부하."""
    try:
        return {**maestro_drivers.failure_fields(dev_id), **host_load_fields(), **maestro_runs.lock_wait_report()}
    except Exception:   # noqa: BLE001 — 진단이 실패 응답을 망치면 안 된다
        return {}


def _wait_until_settled(dev_id: str, relay_pid: int) -> dict | None:
    """상태 파일이 ready·failed 가 되거나, 중계가 죽거나, 시간이 다 될 때까지."""
    deadline = time.monotonic() + START_WAIT_SECONDS
    session = None
    while time.monotonic() < deadline:
        session = maestro_session.read_session(dev_id)
        if session and session.get("relay_pid") == relay_pid and session.get("status") in ("ready", "failed"):
            return session
        if not procs.pid_alive(relay_pid):
            return session if session and session.get("relay_pid") == relay_pid else None
        time.sleep(START_POLL_SECONDS)
    return session


def _failure_text(session: dict | None, state_path) -> str:
    detail = (session or {}).get("detail")
    if detail:
        return detail
    try:
        tail = state_path.with_suffix(".log").read_text(encoding="utf-8").strip().splitlines()[-3:]
    except OSError:
        tail = []
    return " | ".join(tail) or "The relay did not become ready"


def _stop(args, be, dev_id: str) -> int:
    """정중히 끝내자고 요청 > 안 끝나면 프로세스 묶음째 종료 > 상태 파일 정리."""
    session, is_alive = _relay_state(dev_id)
    stale = maestro_drivers.kill_stale(dev_id) if getattr(args, "kill_stale", False) else {}
    if not is_alive:
        return out({"ok": True, "code": "ok", "device": dev_id, "was_running": False,
                    **stale, "cleaned_stale": session is not None, "summary": "No session running",
                    "next": "app session start --device <UDID>  # when needed"})
    relay_pid = int(session["relay_pid"])
    if maestro_session.is_ready(session):
        try:
            maestro_session.request(session, {"op": "stop"}, STOP_WAIT_SECONDS)
        except (OSError, ValueError):
            pass
    deadline = time.monotonic() + STOP_WAIT_SECONDS
    while procs.pid_alive(relay_pid) and time.monotonic() < deadline:
        time.sleep(0.2)
    is_still_alive = procs.pid_alive(relay_pid) and procs.kill_process_group(relay_pid)
    _relay_state(dev_id)
    if is_still_alive:
        return out({"ok": False, "code": "session_stop_failed", "device": dev_id, "relay_pid": relay_pid,
                    "error": "The relay process did not exit", "next": procs.manual_kill_command(relay_pid)})
    return out({"ok": True, "code": "ok", "device": dev_id, "was_running": True, **stale,
                "summary": "Session ended — iOS actions now start Maestro on every call",
                "next": "app session start --device <UDID>  # to make it fast again"})


def _status(args, be, dev_id: str) -> int:
    session, is_alive = _relay_state(dev_id)
    if not is_alive:
        return out({"ok": True, "code": "ok", "device": dev_id, "is_running": False,
                    "cleaned_stale": session is not None, "summary": "No session — iOS actions start Maestro on every call",
                    "next": "app session start --device <UDID>  # when exploring with many calls"})
    if not maestro_session.is_ready(session):
        return out({"ok": True, "code": "ok", "device": dev_id, "is_running": True, "status": session.get("status"),
                    "summary": "Session is starting", "next": "app session status in a moment"})
    try:
        ping = maestro_session.request(session, {"op": "ping"}, 5)
    except (OSError, ValueError):
        ping = {}
    return out(_session_payload(args, dev_id, session, summary="Session is running",
                                is_maestro_alive=ping.get("is_maestro_alive")))


def _session_payload(args, dev_id: str, session: dict, summary: str, **extra) -> dict:
    # 토큰·포트는 내보내지 않는다 (상태 파일에만)
    return {"ok": True, "code": "ok", "device": dev_id, "is_running": True, **extra,
            "relay_pid": session.get("relay_pid"), "tools": session.get("tools"),
            "idle_minutes": session.get("idle_minutes"), "started_at": session.get("started_at"),
            "last_used": session.get("last_used"), "viewer": session.get("viewer"),
            **maestro_runs.lock_wait_report(), "elapsed_seconds": elapsed_seconds(args), "summary": summary,
            "next": "app tree --device <UDID>  # now about 1 s. app session stop when done"}


def configure(p) -> None:
    p.add_argument("session_verb", nargs="?", default=None, choices=SESSION_VERBS,
                   help="session: start · stop · status")
    p.add_argument("--kill-stale", dest="kill_stale", action="store_true",
                   help="session stop: also end orphan Maestro drivers left on this device (xcodebuild·JVM whose parent is gone). Live ones of other sessions are left alone")
    p.add_argument("--idle-minutes", dest="idle_minutes", type=float, default=None,
                   help=f"session start: ends by itself after this much idle time (default {maestro_session.DEFAULT_IDLE_MINUTES} min)")


ACTION = Action(name="session", device_use="mutate", run=_app_session, configure=configure,
                help="iOS resident Maestro session (start·stop·status) — while it runs tap·swipe·tree·run take about 1 s",
                example="app session start --device $DEV")
