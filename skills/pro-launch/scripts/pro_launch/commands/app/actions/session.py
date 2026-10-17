"""`app session start|stop|status` — iOS 상주 Maestro 세션 (#894 2단계, 선택).

세션이 떠 있으면 iOS tap·swipe·tree·run 이 JVM 을 새로 띄우지 않고 그 세션을 쓴다 (호출당 20초 > 1초 안팎).
세션이 없으면 지금처럼 호출마다 Maestro 를 띄운다. 클라이언트는 scripts/maestro_session.py, 중계 프로세스는 scripts/maestro_session_relay.py.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import maestro_session

from pro_launch.commands.app.gestures import backend_for, elapsed_seconds
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
                    "error": "start · stop · status 중 하나가 필요하다",
                    "next": "app session start --device <UDID>"})
    be, dev_id, err = backend_for(args)
    if err is not None:
        return err
    if be.name != "ios":
        return out({"ok": False, "code": "unsupported_on_platform", "action": "session", "platform": be.name,
                    "device": dev_id, "error": "상주 세션은 iOS(Maestro) 전용이다 — Android 조작은 이미 빠르다",
                    "next": "Android 는 세션 없이 app tap·swipe·run 을 그대로 쓴다"})
    if dev_id == "booted":
        return out({"ok": False, "code": "session_needs_udid", "error": "세션은 기기 UDID 로 묶는다 ('booted' 는 받지 않는다)",
                    "next": "devices  # ios_booted 의 UDID 를 --device 로"})
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
        return out(_session_payload(args, dev_id, session, summary="이미 떠 있는 세션을 쓴다", is_already_running=True))
    if is_alive:
        return out({"ok": False, "code": "session_starting", "device": dev_id, "relay_pid": session.get("relay_pid"),
                    "error": "다른 호출이 세션을 띄우는 중이다", "next": "잠시 뒤 app session status"})
    idle_minutes = getattr(args, "idle_minutes", None) or maestro_session.DEFAULT_IDLE_MINUTES
    if not MINIMUM_IDLE_MINUTES <= idle_minutes <= MAXIMUM_IDLE_MINUTES:
        return out({"ok": False, "code": "bad_idle_minutes",
                    "error": f"--idle-minutes 는 {MINIMUM_IDLE_MINUTES}~{MAXIMUM_IDLE_MINUTES} 분이다"})
    state_path = maestro_session.session_file(dev_id)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, str(RELAY_SCRIPT), "serve", "--device", dev_id,
               "--idle-minutes", str(idle_minutes), "--maestro", be._maestro(), "--state-file", str(state_path)]
    relay_pid = procs.spawn_detached(command, str(state_path.parent), state_path.with_suffix(".log"))
    session = _wait_until_settled(dev_id, relay_pid)
    if maestro_session.is_ready(session):
        return out(_session_payload(args, dev_id, session, summary="세션 시작 — 이후 iOS tap·swipe·tree·run 이 이 세션을 쓴다"))
    procs.kill_process_group(relay_pid, grace=2.0)
    reason = (session or {}).get("reason") or "session_start_timeout"
    failure = {"ok": False, "code": "session_start_failed", "device": dev_id, "reason": reason,
               "error": _failure_text(session, state_path), "tools_available": (session or {}).get("tools_available"),
                "elapsed_seconds": elapsed_seconds(args),
                "next": "세션 없이 그대로 쓴다 (app tap·tree 는 호출마다 Maestro 를 띄운다). "
                        "device_unreachable 면 다른 maestro 가 같은 기기를 쓰는 중인지 본다"}
    if reason == "session_tools_missing":
        # 이 Maestro 버전의 MCP 도구 이름을 모른다 — 기동 실패와 다른 대처라 code 를 나눈다
        failure.update(code="session_tools_missing")
    return out(failure)


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
    return " | ".join(tail) or "중계가 준비되지 못했다"


def _stop(args, be, dev_id: str) -> int:
    """정중히 끝내자고 요청 > 안 끝나면 프로세스 묶음째 종료 > 상태 파일 정리."""
    session, is_alive = _relay_state(dev_id)
    if not is_alive:
        return out({"ok": True, "code": "ok", "device": dev_id, "was_running": False,
                    "cleaned_stale": session is not None, "summary": "떠 있는 세션이 없다",
                    "next": "app session start --device <UDID>  # 필요할 때"})
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
                    "error": "중계 프로세스가 끝나지 않았다", "next": procs.manual_kill_command(relay_pid)})
    return out({"ok": True, "code": "ok", "device": dev_id, "was_running": True,
                "summary": "세션을 끝냈다 — 이후 iOS 조작은 호출마다 Maestro 를 띄운다",
                "next": "app session start --device <UDID>  # 다시 빠르게 쓰려면"})


def _status(args, be, dev_id: str) -> int:
    session, is_alive = _relay_state(dev_id)
    if not is_alive:
        return out({"ok": True, "code": "ok", "device": dev_id, "is_running": False,
                    "cleaned_stale": session is not None, "summary": "세션 없음 — iOS 조작은 호출마다 Maestro 를 띄운다",
                    "next": "app session start --device <UDID>  # 탐색을 여러 번 할 때"})
    if not maestro_session.is_ready(session):
        return out({"ok": True, "code": "ok", "device": dev_id, "is_running": True, "status": session.get("status"),
                    "summary": "세션을 띄우는 중", "next": "잠시 뒤 app session status"})
    try:
        ping = maestro_session.request(session, {"op": "ping"}, 5)
    except (OSError, ValueError):
        ping = {}
    return out(_session_payload(args, dev_id, session, summary="세션이 떠 있다",
                                is_maestro_alive=ping.get("is_maestro_alive")))


def _session_payload(args, dev_id: str, session: dict, summary: str, **extra) -> dict:
    # 토큰·포트는 내보내지 않는다 (상태 파일에만)
    return {"ok": True, "code": "ok", "device": dev_id, "is_running": True, **extra,
            "relay_pid": session.get("relay_pid"), "tools": session.get("tools"),
            "idle_minutes": session.get("idle_minutes"), "started_at": session.get("started_at"),
            "last_used": session.get("last_used"), "viewer": session.get("viewer"),
            "elapsed_seconds": elapsed_seconds(args), "summary": summary,
            "next": "app tree --device <UDID>  # 이제 1초 안팎. 끝나면 app session stop"}


def configure(p) -> None:
    p.add_argument("session_verb", nargs="?", default=None, choices=SESSION_VERBS,
                   help="session: start · stop · status")
    p.add_argument("--idle-minutes", dest="idle_minutes", type=float, default=None,
                   help=f"session start: 이만큼 안 쓰면 스스로 끝난다 (기본 {maestro_session.DEFAULT_IDLE_MINUTES}분)")


ACTION = Action(name="session", run=_app_session, configure=configure,
                help="iOS 상주 Maestro 세션 (start·stop·status) — 떠 있으면 tap·swipe·tree·run 이 1초 안팎",
                example="app session start --device $DEV")
