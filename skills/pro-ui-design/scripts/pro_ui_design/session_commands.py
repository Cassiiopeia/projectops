"""세션 명령: start, status, stop, choices"""
from __future__ import annotations

import http.client
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

from common.emit import emit
from common.preferences import detect_repo, resolve as resolve_preferences

from pro_ui_design.config import resolve_config
from pro_ui_design.tokens import read_project_profile
from pro_ui_design.session import (EVENTS_FILE_NAME, SERVER_INFO_FILE_NAME, SERVER_LOG_FILE_NAME, Session,
                                   create_or_reuse_session, find_session, find_session_by_title,
                                   list_project_sessions, resolve_run_dir, save_session)

SERVER_SCRIPT = Path(__file__).resolve().parent / "server.py"
SERVER_START_TIMEOUT_SECONDS = 8
HEALTH_REQUEST_TIMEOUT_SECONDS = 2
KEY_HEADER = "X-UI-Design-Key"
SKILL_FOLDER_NAME = "pro-ui-design"
LOG_TAIL_CHARACTERS = 500
NEXT_AFTER_START = ("Write mockup HTML into screens_dir as a new file, run check, then give the user the full url. "
                    "If the user cannot open localhost, use capture and show the image instead.")
NEXT_WITHOUT_PROFILE = "First run tokens to find this project's design files. "
NEXT_WITH_CHANGED_PROFILE = "Design files changed since the notes were saved: reread them, then run tokens --save. "


def _request_server(session: Session, method: str, path: str) -> dict | None:
    request = urllib.request.Request(f"http://127.0.0.1:{session.port}{path}", method=method,
                                     headers={KEY_HEADER: session.key, "Host": "localhost"})
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
                request, timeout=HEALTH_REQUEST_TIMEOUT_SECONDS) as response:
            body = response.read()
        parsed = json.loads(body) if body else {}
    except (OSError, urllib.error.URLError, http.client.HTTPException, ValueError):   # 포트의 다른 서비스 포함
        return None
    return parsed if isinstance(parsed, dict) else None


def read_server_state(session: Session) -> dict | None:
    """살아 있고 이 세션의 서버일 때만 상태 반환 (같은 포트의 다른 프로세스 구분)"""
    if not session.port:
        return None
    state = _request_server(session, "GET", "/api/state")
    if state is None or state.get("server_token") != session.server_token:
        return None
    return state


def _spawn_server(session: Session) -> None:
    """터미널을 닫아도 살아 있게 분리 실행"""
    detach = ({"creationflags": 0x00000008 | 0x00000200} if sys.platform == "win32"   # DETACHED_PROCESS | NEW_GROUP
              else {"start_new_session": True})
    log_file = session.state_dir / SERVER_LOG_FILE_NAME
    with log_file.open("a", encoding="utf-8") as log:
        subprocess.Popen([sys.executable, str(SERVER_SCRIPT), "--session-dir", session.run_dir],
                         stdin=subprocess.DEVNULL, stdout=log, stderr=log, close_fds=True, **detach)


def _wait_for_server_info(session: Session) -> dict | None:
    info_file = session.state_dir / SERVER_INFO_FILE_NAME
    deadline = time.monotonic() + SERVER_START_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        try:
            return json.loads(info_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            time.sleep(0.05)
    return None


def _start_server(session: Session) -> dict | None:
    """서버 실행 > 준비 대기 > 포트와 식별값 저장"""
    (session.state_dir / SERVER_INFO_FILE_NAME).unlink(missing_ok=True)
    save_session(session)
    _spawn_server(session)
    info = _wait_for_server_info(session)
    if info is None:
        return None
    session.port, session.server_token = info["port"], info["server_token"]
    save_session(session)
    return info


def _read_language(root: Path) -> str | None:
    """뷰어 문구 언어: 개인 설정 language"""
    owner, repo = detect_repo(str(root))
    return resolve_preferences(SKILL_FOLDER_NAME, owner, repo, load=True)["values"].get("language")


def _build_viewer_settings(root: Path, resolved: dict) -> dict:
    return {"devices": resolved["devices"], "themes": resolved["themes"], "language": _read_language(root)}


def _describe_session(session: Session) -> dict:
    return {"url": session.url, "port": session.port, "title": session.title, "issue": session.issue,
            "run_dir": session.run_dir, "screens_dir": str(session.screens_dir), "state_dir": str(session.state_dir)}


def cmd_start(args) -> int:
    root = Path(args.root).resolve()
    if not root.is_dir():
        return emit({"ok": False, "code": "root_not_found", "error": f"Folder not found: {root}"})
    # 같은 제목은 날짜가 바뀌어도 이어 하기 (시안, 키, 포트 유지)
    existing = find_session_by_title(root, args.title)
    run_dir, location = (Path(existing.run_dir), {}) if existing else resolve_run_dir(root, args.title, args.issue)
    if run_dir is None:
        return emit(location)
    resolved = resolve_config(root)["resolved"]
    session = create_or_reuse_session(root, run_dir, args.title, args.issue)
    session.issue = args.issue or session.issue
    session.viewer = _build_viewer_settings(root, resolved)
    session.idle_seconds = args.idle_seconds or resolved["idle_timeout_minutes"] * 60

    reused = read_server_state(session) is not None
    previous_port = session.port
    if not reused and _start_server(session) is None:
        log = session.state_dir / SERVER_LOG_FILE_NAME
        tail = log.read_text(encoding="utf-8", errors="replace")[-LOG_TAIL_CHARACTERS:] if log.is_file() else ""
        return emit({"ok": False, "code": "server_start_failed", "error": "The mockup server did not start",
                     "log_tail": tail, "next": "Read log_tail, fix the cause, and run start again"})
    if reused:
        save_session(session)
    port_changed = bool(previous_port) and previous_port != session.port
    if args.open:
        webbrowser.open(session.url)
    profile = read_project_profile(root)
    return emit({**_describe_session(session), **location, "reused": reused, "port_changed": port_changed,
                 "project_profile": profile,
                 "defaults": {"default_fidelity": resolved["default_fidelity"], "motion_format": resolved["motion_format"]},
                 "summary": f"Mockup server on port {session.port}" + (" (reused)" if reused else ""),
                 "next": _build_next_after_start(profile)})


def _build_next_after_start(profile: dict) -> str:
    if not profile["exists"]:
        return NEXT_WITHOUT_PROFILE + NEXT_AFTER_START
    if profile["changed_files"]:
        return NEXT_WITH_CHANGED_PROFILE + NEXT_AFTER_START
    return f"Read the project notes at {profile['readme']}. " + NEXT_AFTER_START


def cmd_status(args) -> int:
    root = Path(args.root).resolve()
    session = find_session(root, args.title)
    if session is None:
        return emit({"running": False, "url": None, "summary": "No mockup session for this project",
                     "next": "ui_design_cli.py start --title <screen name>"})
    state = read_server_state(session)
    running = state is not None
    return emit({**_describe_session(session), "running": running,
                 "screens": state["screens"] if running else [], "latest": state["current"] if running else None,
                 "summary": f"Session '{session.title}': " + ("running" if running else "stopped"),
                 "next": None if running else f"ui_design_cli.py start --title \"{session.title}\" (same port and key)"})


def _stop_server(session: Session) -> bool:
    """HTTP 로만 종료: 저장된 PID 를 믿고 다른 프로세스를 죽이지 않음"""
    if read_server_state(session) is None:
        return False
    _request_server(session, "POST", "/api/stop")
    deadline = time.monotonic() + SERVER_START_TIMEOUT_SECONDS
    while time.monotonic() < deadline and read_server_state(session) is not None:
        time.sleep(0.05)
    return True


def cmd_stop(args) -> int:
    """기본은 이 세션만: 같은 레포의 다른 에이전트 세션을 끄지 않음. --all 은 프로젝트 전체"""
    root = Path(args.root).resolve()
    if args.all:
        targets = list_project_sessions(root)
    else:
        current = find_session(root, args.title)
        targets = [current] if current else []
    stopped_sessions = sum(_stop_server(target) for target in targets)
    return emit({"stopped": stopped_sessions > 0, "stopped_sessions": stopped_sessions,
                 "summary": f"Stopped {stopped_sessions} mockup server(s); mockups are kept"})


def read_events(session: Session) -> list[dict]:
    events = []
    try:
        lines = (session.state_dir / EVENTS_FILE_NAME).read_text(encoding="utf-8").splitlines()
    except OSError:
        return events
    for line in lines:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def cmd_choices(args) -> int:
    session = find_session(Path(args.root).resolve(), args.title)
    if session is None:
        return emit({"last_choice": None, "by_screen": {}, "summary": "No mockup session for this project"})
    chosen = [event for event in read_events(session) if event.get("choice")]
    if args.screen:
        chosen = [event for event in chosen if event.get("screen") == args.screen]
    by_screen: dict[str, list] = {}
    for event in chosen:
        by_screen.setdefault(event.get("screen") or "", []).append(event)
    last_choice = chosen[-1] if chosen else None
    return emit({"last_choice": last_choice, "by_screen": by_screen,
                 "summary": f"Last click: {last_choice['choice']}" if last_choice else "No clicks recorded",
                 "next": "The terminal reply wins over clicks. Record the decision with decide when it is settled."})
