"""시안 서버 (표준 라이브러리 전용, 분리 프로세스로 실행)
요청 처리: Host 확인 > 키 확인 > 경로별 처리. 127.0.0.1 전용, 세션 폴더 밖 접근 차단
"""
from __future__ import annotations

import argparse
import hashlib
import http.server
import json
import os
import re
import secrets
import sys
import threading
import time
import urllib.parse
from pathlib import Path

BIND_HOST = "127.0.0.1"
ALLOWED_HOST_NAMES = {"localhost", BIND_HOST}
KEY_HEADER = "X-UI-Design-Key"
MAX_EVENT_BYTES = 64 * 1024
MAX_EVENT_TEXT_LENGTH = 500
IDLE_CHECK_MAX_SECONDS = 30
TOKENS_FILE_NAME = "tokens.css"
# skills/pro-ui-design/assets/ (이 파일: skills/pro-ui-design/scripts/pro_ui_design/)
ASSETS_DIR = Path(__file__).resolve().parents[2] / "assets"
SERVED_ASSETS = {"shell.js": "text/javascript; charset=utf-8", "viewer.js": "text/javascript; charset=utf-8", "viewer.css": "text/css; charset=utf-8",
                 "viewer-i18n.ko.json": "application/json; charset=utf-8"}
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp", ".mp4": "video/mp4", ".webm": "video/webm",
    ".mov": "video/quicktime", ".woff": "font/woff", ".woff2": "font/woff2", ".ttf": "font/ttf", ".otf": "font/otf",
}
FULL_DOCUMENT_PATTERN = re.compile(r"^\s*(<!doctype|<html)", re.IGNORECASE)
HEAD_END_PATTERN = re.compile(r"</head\s*>", re.IGNORECASE)


class SessionState:
    """요청 스레드가 함께 쓰는 세션 값"""

    def __init__(self, run_dir: Path):
        data = json.loads((run_dir / "session.json").read_text(encoding="utf-8"))
        self.run_dir = run_dir
        self.screens_dir = (run_dir / "screens").resolve()
        self.state_dir = run_dir / "state"
        self.events_file = self.state_dir / "events.jsonl"
        self.key = data["key"]
        self.title = data.get("title") or ""
        self.viewer = data.get("viewer") or {}
        self.preferred_port = int(data.get("port") or 0)
        self.idle_seconds = int(data.get("idle_seconds") or 14400)
        self.server_token = secrets.token_hex(16)
        self.last_activity = time.monotonic()
        self.last_revision = ""
        self.event_lock = threading.Lock()
        self.port = 0

    def list_screens(self) -> list[dict]:
        """시안 목록 (최근 수정순): 폴더 바로 아래 *.html, _로 시작하는 파일 제외"""
        screens = []
        try:
            entries = list(self.screens_dir.iterdir())
        except OSError:
            return screens
        for entry in entries:
            if entry.suffix.lower() != ".html" or entry.name.startswith("_") or not entry.is_file():
                continue
            try:
                stat = entry.stat()
            except OSError:
                continue
            screens.append({"name": entry.name, "modified_ms": stat.st_mtime_ns // 1_000_000, "_stamp": stat.st_mtime_ns,
                            "_size": stat.st_size})
        screens.sort(key=lambda screen: (-screen["_stamp"], screen["name"]))
        return screens

    def read_state(self) -> dict:
        screens = self.list_screens()
        fingerprint = "|".join(f"{s['name']}:{s['_stamp']}:{s['_size']}" for s in screens)
        revision = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:16]
        if revision != self.last_revision:
            self.last_revision = revision
            self.touch()
        return {"revision": revision, "current": screens[0]["name"] if screens else None,
                "screens": [{"name": s["name"], "modified_ms": s["modified_ms"]} for s in screens],
                "server_token": self.server_token, "title": self.title}

    def touch(self) -> None:
        self.last_activity = time.monotonic()

    def resolve_screen_file(self, relative_path: str) -> Path | None:
        """요청 경로 > 세션 안 파일. 경로 이탈, 심볼릭 링크 탈출은 None"""
        if "\x00" in relative_path or "\\" in relative_path:
            return None
        candidate = (self.screens_dir / relative_path).resolve()
        try:
            candidate.relative_to(self.screens_dir)
        except ValueError:
            return None
        return candidate


def render_screen_html(state: SessionState, screen_file: Path) -> str:
    """시안 파일 > 응답 HTML: 전체 문서는 viewer.js 만 삽입, 조각은 틀로 감쌈"""
    content = screen_file.read_bytes().decode("utf-8", errors="replace")
    viewer_script = '<script src="/assets/viewer.js"></script>'
    if FULL_DOCUMENT_PATTERN.match(content):
        match = HEAD_END_PATTERN.search(content)
        if not match:
            return viewer_script + content
        return content[:match.start()] + viewer_script + content[match.start():]
    tokens_link = ""
    if (state.screens_dir / TOKENS_FILE_NAME).is_file():
        tokens_link = f'<link rel="stylesheet" href="/files/{TOKENS_FILE_NAME}">'
    frame = (ASSETS_DIR / "frame.html").read_text(encoding="utf-8")
    return frame.replace("__TOKENS_LINK__", tokens_link).replace("__CONTENT__", content)


def render_shell_html(state: SessionState) -> str:
    settings = {**state.viewer, "title": state.title}
    embedded = json.dumps(settings, ensure_ascii=False).replace("<", "\\u003c")   # 인라인 script 탈출 방지
    return (ASSETS_DIR / "shell.html").read_text(encoding="utf-8").replace("__UI_DESIGN_SETTINGS__", embedded)


class ViewerRequestHandler(http.server.BaseHTTPRequestHandler):
    server_version = "ui-design"
    sys_version = ""

    @property
    def state(self) -> SessionState:
        return self.server.session_state

    def log_message(self, format, *args):  # noqa: A002  (표준 라이브러리 서명)
        return

    def _respond(self, status: int, body: bytes = b"", content_type: str = "text/plain; charset=utf-8",
                 extra_headers: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "frame-ancestors 'self'")
        for name, value in (extra_headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _respond_json(self, payload: dict) -> None:
        self._respond(200, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _is_allowed_host(self) -> bool:
        """다른 사이트가 DNS 로 localhost 를 가장하는 요청 차단"""
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]").lower()
        return host in ALLOWED_HOST_NAMES

    def _cookie_name(self) -> str:
        return f"ui_design_key_{self.state.port}"

    def _is_key_match(self, candidate: str | None) -> bool:
        return bool(candidate) and secrets.compare_digest(candidate.encode("utf-8"), self.state.key.encode("utf-8"))

    def _has_valid_key(self) -> bool:
        if self._is_key_match(self.headers.get(KEY_HEADER)):
            return True
        # 직접 파싱: localhost 의 다른 앱 쿠키가 비표준이어도 이 쿠키는 읽혀야 함 (쿠키는 포트별로 안 나뉨)
        for pair in (self.headers.get("Cookie") or "").split(";"):
            name, _, value = pair.strip().partition("=")
            if name == self._cookie_name():
                return self._is_key_match(value)
        return False

    def _is_same_origin(self) -> bool:
        origin = urllib.parse.urlparse(self.headers.get("Origin") or "")
        return origin.scheme == "http" and origin.hostname in ALLOWED_HOST_NAMES and origin.port == self.state.port

    def do_GET(self):  # noqa: N802  (표준 라이브러리 서명)
        if not self._is_allowed_host():
            return self._respond(403, b"forbidden")
        parsed = urllib.parse.urlparse(self.path)
        query_key = urllib.parse.parse_qs(parsed.query).get("key", [None])[0]
        if self._is_key_match(query_key):
            cookie = f"{self._cookie_name()}={self.state.key}; HttpOnly; SameSite=Lax; Path=/"
            return self._respond(302, extra_headers={"Location": parsed.path or "/", "Set-Cookie": cookie})
        if not self._has_valid_key():
            return self._respond(403, b"Open the full URL printed by ui_design_cli.py status (it has the key).")
        route = urllib.parse.unquote(parsed.path)
        if route == "/api/state":
            return self._respond_json(self.state.read_state())
        self.state.touch()
        if route == "/favicon.ico":   # 브라우저 자동 요청: 콘솔 404 방지
            return self._respond(204)
        if route == "/":
            return self._respond(200, render_shell_html(self.state).encode("utf-8"), CONTENT_TYPES[".html"])
        if route.startswith("/assets/"):
            return self._serve_asset(route[len("/assets/"):])
        if route.startswith("/screens/"):
            return self._serve_screen(route[len("/screens/"):])
        if route.startswith("/files/"):
            return self._serve_file(route[len("/files/"):])
        return self._respond(404, b"not found")

    do_HEAD = do_GET  # noqa: N815

    def _serve_asset(self, name: str) -> None:
        content_type = SERVED_ASSETS.get(name)
        if content_type is None:
            return self._respond(404, b"not found")
        self._respond(200, (ASSETS_DIR / name).read_bytes(), content_type)

    def _serve_screen(self, name: str) -> None:
        if not name.lower().endswith(".html"):   # 시안의 상대 경로 자원 (src="logo.png")
            return self._serve_file(name)
        if "/" in name:
            return self._respond(404, b"not found")
        screen_file = self.state.resolve_screen_file(name)
        if screen_file is None or not screen_file.is_file():
            return self._respond(404, b"not found")
        try:
            html = render_screen_html(self.state, screen_file)
        except OSError:   # 쓰는 중이거나 지워진 파일: 다음 확인에서 다시 받음
            return self._respond(404, b"not found")
        self._respond(200, html.encode("utf-8"), CONTENT_TYPES[".html"])

    def _serve_file(self, relative_path: str) -> None:
        file_path = self.state.resolve_screen_file(relative_path)
        if file_path is None:
            return self._respond(403, b"forbidden")
        if not file_path.is_file():
            return self._respond(404, b"not found")
        content_type = CONTENT_TYPES.get(file_path.suffix.lower(), "application/octet-stream")
        try:
            self._respond(200, file_path.read_bytes(), content_type)
        except OSError:
            self._respond(404, b"not found")

    def do_POST(self):  # noqa: N802  (표준 라이브러리 서명)
        if not self._is_allowed_host() or not self._has_valid_key():
            return self._respond(403, b"forbidden")
        route = urllib.parse.urlparse(self.path).path
        if route == "/api/stop":
            if not self._is_key_match(self.headers.get(KEY_HEADER)):   # 다른 페이지가 끌 수 없게 헤더만 인정
                return self._respond(403, b"forbidden")
            self._respond(204)
            return threading.Thread(target=self.server.shutdown, daemon=True).start()
        if route == "/api/events":
            return self._record_event()
        return self._respond(404, b"not found")

    def _record_event(self) -> None:
        """클릭 기록: 같은 Origin 만, 크기 제한, 허용 키만 저장"""
        if not self._is_same_origin():
            return self._respond(403, b"forbidden")
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self._respond(400, b"bad length")
        if length > MAX_EVENT_BYTES:
            self.close_connection = True
            return self._respond(413, b"too large")
        try:
            event = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return self._respond(400, b"bad json")
        if not isinstance(event, dict):
            return self._respond(400, b"bad json")
        record = {key: str(event[key])[:MAX_EVENT_TEXT_LENGTH] for key in ("type", "choice", "text", "screen")
                  if event.get(key) is not None}
        record["timestamp"] = int(time.time() * 1000)
        with self.state.event_lock:
            with self.state.events_file.open("a", encoding="utf-8") as events:
                events.write(json.dumps(record, ensure_ascii=False) + "\n")
        self.state.touch()
        self._respond(204)


class ViewerServer(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = os.name != "nt"   # Windows 는 사용 중인 포트까지 공유되므로 끔


def bind_server(state: SessionState) -> ViewerServer:
    """지난 포트 우선(열린 탭 유지), 쓰이고 있으면 새 포트"""
    try:
        return ViewerServer((BIND_HOST, state.preferred_port), ViewerRequestHandler)
    except OSError as error:
        print(f"[ui-design server] port {state.preferred_port} unavailable : {error}", file=sys.stderr, flush=True)
        return ViewerServer((BIND_HOST, 0), ViewerRequestHandler)


def watch_idle(server: ViewerServer, state: SessionState) -> None:
    """유휴 시간 초과 시 종료. 탭의 주기적 확인은 활동으로 치지 않음"""
    interval = min(max(state.idle_seconds / 4, 0.2), IDLE_CHECK_MAX_SECONDS)
    while True:
        time.sleep(interval)
        state.read_state()   # 탭이 없어도 새 시안 파일은 활동으로 인정
        if time.monotonic() - state.last_activity >= state.idle_seconds:
            print("[ui-design server] stopped : idle timeout", file=sys.stderr, flush=True)
            server.shutdown()
            return


def write_server_info(state: SessionState) -> None:
    info_file = state.state_dir / "server-info.json"
    temporary_file = info_file.with_suffix(".tmp")
    temporary_file.write_text(json.dumps({"port": state.port, "server_token": state.server_token, "pid": os.getpid()}),
                              encoding="utf-8")
    os.replace(temporary_file, info_file)


def main() -> int:
    parser = argparse.ArgumentParser(description="pro-ui-design local mockup server")
    parser.add_argument("--session-dir", required=True)
    args = parser.parse_args()
    state = SessionState(Path(args.session_dir))
    server = bind_server(state)
    server.session_state = state
    state.port = server.server_address[1]
    write_server_info(state)
    threading.Thread(target=watch_idle, args=(server, state), daemon=True).start()
    print(f"[ui-design server] started : port {state.port}", file=sys.stderr, flush=True)
    try:
        server.serve_forever(poll_interval=0.2)
    finally:
        server.server_close()
        (state.state_dir / "server-info.json").unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
