"""Mockup server (standard library only, runs as a detached process)
Request handling: check Host > check key > route. 127.0.0.1 only, access outside the session folder blocked
"""
from __future__ import annotations

import argparse
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

# When run detached, import modules from this folder (this file: scripts/pro_ui_design/server.py)
sys.path.insert(0, str(Path(__file__).resolve().parent))

from session_state import SessionState  # noqa: E402

BIND_HOST = "127.0.0.1"
ALLOWED_HOST_NAMES = {"localhost", BIND_HOST}
KEY_HEADER = "X-UI-Design-Key"
MAX_EVENT_BYTES = 64 * 1024
MAX_EVENT_TEXT_LENGTH = 500
IDLE_CHECK_MAX_SECONDS = 30
# Idle connection close time (seconds), response buffer size sent at once (64KB)
IDLE_CONNECTION_SECONDS = 120
RESPONSE_BUFFER_BYTES = 64 * 1024
TOKENS_FILE_NAME = "tokens.css"
# skills/pro-ui-design/assets/ (this file: skills/pro-ui-design/scripts/pro_ui_design/)
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


def render_screen_html(state: SessionState, screen_file: Path) -> str:
    """Mockup file > response HTML: full documents get only viewer.js injected, fragments get wrapped in the frame"""
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
    embedded = json.dumps(settings, ensure_ascii=False).replace("<", "\\u003c")   # Prevent escaping the inline script
    return (ASSETS_DIR / "shell.html").read_text(encoding="utf-8").replace("__UI_DESIGN_SETTINGS__", embedded)


class ViewerRequestHandler(http.server.BaseHTTPRequestHandler):
    server_version = "ui-design"
    sys_version = ""
    # Reuse connections + send buffered responses: a new connection per request costs tens of ms (worst on Windows, #1112)
    protocol_version = "HTTP/1.1"
    timeout = IDLE_CONNECTION_SECONDS
    disable_nagle_algorithm = True
    wbufsize = RESPONSE_BUFFER_BYTES

    @property
    def state(self) -> SessionState:
        return self.server.session_state

    def log_message(self, format, *args):  # noqa: A002  (standard library signature)
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
        if status >= 400:
            # A rejected request may have an unread body > close the connection so leftovers are not read as the next request
            self.close_connection = True
            self.send_header("Connection", "close")
        for name, value in (extra_headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _respond_json(self, payload: dict) -> None:
        self._respond(200, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _is_allowed_host(self) -> bool:
        """Block requests from other sites posing as localhost via DNS"""
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]").lower()
        return host in ALLOWED_HOST_NAMES

    def _cookie_name(self) -> str:
        return f"ui_design_key_{self.state.port}"

    def _is_key_match(self, candidate: str | None) -> bool:
        return bool(candidate) and secrets.compare_digest(candidate.encode("utf-8"), self.state.key.encode("utf-8"))

    def _has_valid_key(self) -> bool:
        if self._is_key_match(self.headers.get(KEY_HEADER)):
            return True
        # Parse by hand: this cookie must be readable even if other localhost apps set non-standard cookies (cookies are not per port)
        for pair in (self.headers.get("Cookie") or "").split(";"):
            name, _, value = pair.strip().partition("=")
            if name == self._cookie_name():
                return self._is_key_match(value)
        return False

    def _is_same_origin(self) -> bool:
        origin = urllib.parse.urlparse(self.headers.get("Origin") or "")
        return origin.scheme == "http" and origin.hostname in ALLOWED_HOST_NAMES and origin.port == self.state.port

    def do_GET(self):  # noqa: N802  (standard library signature)
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
        if route == "/favicon.ico":   # Automatic browser request: avoid a console 404
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
        if not name.lower().endswith(".html"):   # Relative-path resources of a mockup (src="logo.png")
            return self._serve_file(name)
        if "/" in name:
            return self._respond(404, b"not found")
        screen_file = self.state.resolve_screen_file(name)
        if screen_file is None or not screen_file.is_file():
            return self._respond(404, b"not found")
        try:
            html = render_screen_html(self.state, screen_file)
        except OSError:   # File being written or deleted: picked up on the next poll
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

    def do_POST(self):  # noqa: N802  (standard library signature)
        if not self._is_allowed_host() or not self._has_valid_key():
            return self._respond(403, b"forbidden")
        route = urllib.parse.urlparse(self.path).path
        if route == "/api/stop":
            if not self._is_key_match(self.headers.get(KEY_HEADER)):   # Accept only the header so other pages cannot shut it down
                return self._respond(403, b"forbidden")
            self._respond(204)
            return threading.Thread(target=self.server.shutdown, daemon=True).start()
        if route == "/api/events":
            return self._record_event()
        return self._respond(404, b"not found")

    def _record_event(self) -> None:
        """Click log: same Origin only, size limit, allowed keys only"""
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
    allow_reuse_address = os.name != "nt"   # Off on Windows, where it would share ports already in use


def bind_server(state: SessionState) -> ViewerServer:
    """Prefer the previous port (keeps open tabs), new port if taken"""
    try:
        return ViewerServer((BIND_HOST, state.preferred_port), ViewerRequestHandler)
    except OSError as error:
        print(f"[ui-design server] port {state.preferred_port} unavailable : {error}", file=sys.stderr, flush=True)
        return ViewerServer((BIND_HOST, 0), ViewerRequestHandler)


def watch_idle(server: ViewerServer, state: SessionState) -> None:
    """Exit after idle timeout. Periodic tab polling does not count as activity"""
    interval = min(max(state.idle_seconds / 4, 0.2), IDLE_CHECK_MAX_SECONDS)
    while True:
        time.sleep(interval)
        state.read_state()   # A new mockup file counts as activity even with no tab open
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
