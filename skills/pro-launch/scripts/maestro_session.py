"""iOS 상주 Maestro 세션 (#894 2단계) — 상태 파일 · 중계를 부르는 클라이언트 · 응답 읽기.

CLI 는 호출마다 끝나는 프로세스라 STDIO MCP 서버를 붙들 주체가 없다. 그래서 중계 프로세스 하나가
`maestro mcp` 의 표준입출력을 소유하고 127.0.0.1 TCP 로 요청을 받아 넘긴다 (표준 라이브러리만).

  app session start   > 중계 띄우기 > 도구 이름 확인(tools/list) > 기기 연결 예열 > 상태 파일 ready
  app tap·swipe·tree·run > call() > 중계 > tools/call (따뜻하면 run 0.7~1초 · inspect_screen 0.1초, 실측)
  유휴 N분 · app session stop > 중계가 maestro mcp 와 함께 끝난다

상태 파일: {PROJECTOPS_HOME}/launch/maestro-sessions/<UDID>.json (권한 600 — 접속 토큰이 들어 있다)
비밀 입력(type)은 이 길로 넘기지 않는다: maestro mcp 가 run 응답에 env 값을 평문으로 되돌려 주고(2.10.0 실측),
상주 프로세스의 로그 자리는 호출마다 임시 폴더로 돌릴 수 없다.

중계 프로세스 본체는 maestro_session_relay.py (standalone 으로 돈다). 이 모듈은 상태 파일 · 클라이언트 · 응답 읽기.
이 모듈도 표준 라이브러리만 top-level 에서 들인다 — 중계가 import 한다.
"""
from __future__ import annotations

import json
import os
import re
import socket
from pathlib import Path

# 상태 파일 폴더 이름 (launch 상태 루트 아래, 기기 하나에 파일 하나)
SESSION_FOLDER_NAME = "maestro-sessions"
DEFAULT_IDLE_MINUTES = 20
# 논리 이름 > 버전별 후보 도구 이름 (Maestro 버전마다 이름이 달랐다: run_flow → run)
TOOL_CANDIDATES = {"run": ("run", "run_flow"), "inspect": ("inspect_screen", "inspect_view_hierarchy")}
# 클라이언트 접속 대기 (초)
CLIENT_CONNECT_TIMEOUT_SECONDS = 3


# ── 상태 파일 (클라이언트 쪽) ─────────────────────────────────────────────

def session_folder() -> Path:
    from common.state import base_dir   # 중계는 standalone 이라 여기서만 들인다
    return base_dir() / "launch" / SESSION_FOLDER_NAME


def session_file(device: str) -> Path:
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", device)
    return session_folder() / f"{safe_name}.json"


def read_session(device: str) -> dict | None:
    """기기의 세션 상태. 파일이 없거나 깨졌으면 None."""
    try:
        data = json.loads(session_file(device).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def write_session(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.chmod(temporary, 0o600)   # 접속 토큰 — 본인만 읽는다
    os.replace(temporary, path)


def is_ready(session: dict | None) -> bool:
    return bool(session and session.get("status") == "ready" and session.get("port") and session.get("token"))


# ── 클라이언트 ───────────────────────────────────────────────────────────

def request(session: dict, payload: dict, timeout_seconds: float) -> dict:
    """중계에 한 줄 JSON 요청 > 한 줄 JSON 응답. 접속 실패·시간 초과는 OSError 계열로 올린다."""
    with socket.create_connection(("127.0.0.1", int(session["port"])), timeout=CLIENT_CONNECT_TIMEOUT_SECONDS) as conn:
        conn.settimeout(timeout_seconds)
        conn.sendall((json.dumps({**payload, "token": session["token"]}) + "\n").encode("utf-8"))
        received = b""
        while not received.endswith(b"\n"):
            chunk = conn.recv(65536)
            if not chunk:
                break
            received += chunk
    if not received.strip():
        raise ConnectionError("relay closed the connection without a reply")
    return json.loads(received.decode("utf-8"))


def call(device: str, tool: str, arguments: dict, timeout_seconds: float) -> tuple[dict | None, str | None]:
    """세션으로 도구 호출 > (결과, None). 세션이 없으면 (None, None) — 지금의 길 그대로.

    세션이 있는데 못 썼으면 (None, 사유) — 부르는 쪽이 호출마다 띄우는 길로 내려가고 사유를 응답에 남긴다.
    결과: {"is_error": bool, "text": str, "reconnected": bool}
    """
    session = read_session(device)
    if session is None:
        return None, None
    if not is_ready(session):
        return None, "session_not_ready"
    try:
        reply = request(session, {"op": "call", "tool": tool, "arguments": arguments,
                                  "timeout_seconds": timeout_seconds}, timeout_seconds + 30)
    except ConnectionRefusedError:
        # 중계가 없다 (강제 종료·재부팅) — 남은 상태 파일을 걷는다
        try:
            session_file(device).unlink()
        except OSError:
            pass
        return None, "session_gone"
    except socket.timeout:
        return None, "session_timeout"
    except (OSError, ValueError):
        return None, "session_unreachable"
    if not reply.get("ok"):
        return None, str(reply.get("reason") or "session_call_failed")
    return {"is_error": bool(reply.get("is_error")), "text": str(reply.get("text") or ""),
            "reconnected": bool(reply.get("reconnected"))}, None


def flow_outcome(result: dict) -> tuple[bool, list[str]]:
    """run 도구 결과 > (성공 여부, 출력 줄). 실패 문구 예: 'Failed to run flow: Element not found: ...'"""
    text = result["text"]
    if result["is_error"]:
        return False, [line for line in text.splitlines() if line.strip()] or ["maestro mcp run failed"]
    try:
        body = json.loads(text)
    except ValueError:
        return True, [text]
    # 응답에 env_vars 가 실려 오는 일이 있다 — 줄로 내보내지 않는다
    is_success = bool(body.get("success", True)) if isinstance(body, dict) else True
    message = body.get("message", "") if isinstance(body, dict) else ""
    return is_success, [message] if message else []


def resolve_tool_names(available: list[str]) -> tuple[dict[str, str], list[str]]:
    """서버가 가진 도구 이름 > ({논리 이름: 실제 이름}, 못 찾은 논리 이름)."""
    mapping, missing = {}, []
    for logical, candidates in TOOL_CANDIDATES.items():
        found = next((name for name in candidates if name in available), None)
        if found:
            mapping[logical] = found
        else:
            missing.append(logical)
    return mapping, missing


def inspect_screen_to_hierarchy(json_text: str) -> str:
    """inspect_screen 응답(줄임 키 b·txt·rid·a11y·c) > `maestro hierarchy` 와 같은 모양의 JSON. 못 읽으면 빈 문자열."""
    try:
        body = json.loads(json_text)
    except ValueError:
        return ""
    if not isinstance(body, dict):
        return ""
    # 줄임 표는 응답의 ui_schema 가 정한다 — 버전마다 바뀌어도 따라간다
    full_name_by_short = {"b": "bounds", "txt": "text", "rid": "resource-id", "a11y": "accessibilityText", "c": "children"}
    full_name_by_short.update((body.get("ui_schema") or {}).get("abbreviations") or {})

    def expand(element: dict) -> dict:
        named = {full_name_by_short.get(k, k): v for k, v in element.items()}
        children = named.pop("children", None) or []
        return {"attributes": named, "children": [expand(c) for c in children if isinstance(c, dict)]}

    return json.dumps({"attributes": {}, "children": [expand(e) for e in body.get("elements") or [] if isinstance(e, dict)]})
