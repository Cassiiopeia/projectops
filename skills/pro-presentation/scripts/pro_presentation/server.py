"""연습 화면 서버 (표준 라이브러리 전용, 분리 프로세스로 실행)
요청 처리: Host 확인 > 키 확인 > 경로별 처리. 127.0.0.1 전용, 덱 폴더·스킬 자산 밖 접근 차단
"""
from __future__ import annotations

import argparse
import http.server
import json
import os
import secrets
import sys
import threading
import time
import urllib.parse
from pathlib import Path

# 분리 실행 시 패키지 import 경로 (이 파일: scripts/pro_presentation/server.py)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pro_presentation.deck import deck_version, load_deck  # noqa: E402
from pro_presentation.recording_marks import RECORDING_EXTENSIONS, parse_marks, save_page_recording  # noqa: E402
from pro_presentation.settings import (DECK_FILE_NAME, PRACTICE_ASSETS_DIR, SAVABLE_FILES, SERVER_INFO_FILE_NAME,  # noqa: E402
                                       SLIDES_DIR_NAME, STATE_DIR_NAME, THEME_FILE_NAME)

BIND_HOST = "127.0.0.1"
ALLOWED_HOST_NAMES = {"localhost", BIND_HOST}
KEY_HEADER = "X-Presentation-Key"
KEY_COOKIE = "presentation_key"
# 요청이 없으면 스스로 종료 (2시간)
IDLE_SHUTDOWN_SECONDS = 2 * 60 * 60
IDLE_CHECK_SECONDS = 60
MAX_SAVE_BYTES = 512 * 1024
# 연습 화면 녹음 최대 크기 (300MB, opus 기준 몇 시간) · 장 넘긴 시각을 담는 헤더 (encodeURIComponent JSON)
MAX_RECORDING_BYTES = 300 * 1024 * 1024
RECORDING_COPY_CHUNK_BYTES = 1024 * 1024
MARKS_HEADER = "X-Recording-Marks"
PRACTICE_ASSETS = {"practice.js": "text/javascript; charset=utf-8", "recorder.js": "text/javascript; charset=utf-8",
                   "practice.css": "text/css; charset=utf-8",
                   "i18n.ko.json": "application/json; charset=utf-8"}
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8", ".md": "text/plain; charset=utf-8", ".txt": "text/plain; charset=utf-8",
    ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
    ".webp": "image/webp", ".woff": "font/woff", ".woff2": "font/woff2", ".ttf": "font/ttf", ".otf": "font/otf",
}


class DeckServer(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, deck_dir: Path, key: str, token: str):
        super().__init__((BIND_HOST, 0), RequestHandler)
        self.deck_dir = deck_dir
        self.key = key
        self.token = token
        self.last_request_at = time.monotonic()
        self.idle_shutdown_seconds = IDLE_SHUTDOWN_SECONDS


class RequestHandler(http.server.BaseHTTPRequestHandler):
    server: DeckServer

    def log_message(self, format, *args):  # noqa: A002  (표준 라이브러리 서명)
        return

    # 응답 (캐시 금지: 덱 파일은 계속 바뀜)
    def _respond(self, status: int, body: bytes = b"", content_type: str = "text/plain; charset=utf-8",
                 headers: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _respond_json(self, payload: dict, status: int = 200) -> None:
        self._respond(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    # 접근 검사 (Host · 키: 헤더 > 쿠키 > ?key=)
    def _is_allowed_host(self) -> bool:
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]")
        return host in ALLOWED_HOST_NAMES

    def _cookie_name(self) -> str:
        # 쿠키는 포트를 가리지 않는다: 덱 여러 개를 동시에 열어도 섞이지 않게 포트별 이름
        return f"{KEY_COOKIE}_{self.server.server_address[1]}"

    def _presented_key(self, query: dict) -> str:
        """헤더 > ?key= > 쿠키 순 (주소의 키가 남은 쿠키보다 우선)"""
        if self.headers.get(KEY_HEADER):
            return self.headers[KEY_HEADER]
        if query.get("key"):
            return query["key"][0]
        for part in (self.headers.get("Cookie") or "").split(";"):
            name, _, value = part.strip().partition("=")
            if name == self._cookie_name():
                return value
        return ""

    def _check_access(self, query: dict) -> bool:
        self.server.last_request_at = time.monotonic()
        if not self._is_allowed_host():
            self._respond(403, b"host not allowed")
            return False
        if not secrets.compare_digest(self._presented_key(query), self.server.key):
            self._respond(403, b"key required: open the url printed by start")
            return False
        return True

    def do_HEAD(self):  # noqa: N802
        self.do_GET()

    def do_GET(self):  # noqa: N802  (표준 라이브러리 서명)
        parsed = urllib.parse.urlsplit(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        route = urllib.parse.unquote(parsed.path)
        if route == "/api/state" and self._is_allowed_host():
            return self._respond_json({"server_token": self.server.token, "pid": os.getpid()})
        if not self._check_access(query):
            return None
        cookie = {"Set-Cookie": f"{self._cookie_name()}={self.server.key}; Path=/; HttpOnly; SameSite=Strict"}
        if route == "/":
            return self._respond(200, (PRACTICE_ASSETS_DIR / "index.html").read_bytes(), CONTENT_TYPES[".html"], cookie)
        if route.startswith("/render/"):
            return self._serve_render(route[len("/render/"):], cookie)
        if route.startswith("/assets/"):
            return self._serve_asset(route[len("/assets/"):])
        if route.startswith("/deck/"):
            return self._serve_deck_file(route[len("/deck/"):])
        if route == "/api/deck":
            return self._respond_json({**load_deck(self.server.deck_dir), "version": deck_version(self.server.deck_dir)})
        if route == "/api/version":
            return self._respond_json({"version": deck_version(self.server.deck_dir)})
        return self._respond(404, b"not found")

    def _serve_asset(self, name: str) -> None:
        content_type = PRACTICE_ASSETS.get(name)
        if content_type is None:
            return self._respond(404, b"not found")
        return self._respond(200, (PRACTICE_ASSETS_DIR / name).read_bytes(), content_type)

    def _resolve_deck_file(self, relative_path: str) -> Path | None:
        """덱 폴더 안 파일만 (.. · 상태 폴더 차단)"""
        deck_root = self.server.deck_dir.resolve()
        candidate = (deck_root / relative_path).resolve()
        if deck_root not in candidate.parents or not candidate.is_file():
            return None
        if candidate.relative_to(deck_root).parts[0] == STATE_DIR_NAME:
            return None
        return candidate

    def _serve_deck_file(self, relative_path: str) -> None:
        target = self._resolve_deck_file(relative_path)
        if target is None:
            return self._respond(404, b"not found")
        return self._respond(200, target.read_bytes(), CONTENT_TYPES.get(target.suffix.lower(), "application/octet-stream"))

    def _serve_render(self, slide_id: str, cookie: dict) -> None:
        """한 장을 1920x1080 단독 페이지로 (연습 화면 iframe · 내보내기 캡처 공용)"""
        slide_file = self._resolve_deck_file(f"{SLIDES_DIR_NAME}/{slide_id}/slide.html")
        if slide_file is None:
            return self._respond(404, b"slide not found")
        template = (PRACTICE_ASSETS_DIR / "render.html").read_text(encoding="utf-8")
        page = (template.replace("__THEME_URL__", f"/deck/{THEME_FILE_NAME}")
                .replace("__BASE_URL__", f"/deck/{SLIDES_DIR_NAME}/{urllib.parse.quote(slide_id)}/")
                .replace("__SLIDE_HTML__", slide_file.read_text(encoding="utf-8", errors="replace")))
        return self._respond(200, page.encode("utf-8"), CONTENT_TYPES[".html"], cookie)

    def do_POST(self):  # noqa: N802  (표준 라이브러리 서명)
        parsed = urllib.parse.urlsplit(self.path)
        if not self._check_access(urllib.parse.parse_qs(parsed.query)):
            return None
        if parsed.path == "/api/save":
            return self._save_slide_file()
        if parsed.path == "/api/order":
            return self._save_slide_order()
        if parsed.path == "/api/recording":
            return self._save_recording(urllib.parse.parse_qs(parsed.query))
        if parsed.path == "/api/stop":
            self._respond_json({"stopped": True})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return None
        return self._respond(404, b"not found")

    def _save_slide_file(self) -> None:
        """브라우저 고침 > 장 파일. 읽은 뒤 파일이 바뀌었으면 덮어쓰지 않음 (409)"""
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_SAVE_BYTES:
            return self._respond_json({"code": "bad_size"}, 413)
        try:
            request = json.loads(self.rfile.read(length))
            file_name = SAVABLE_FILES[request["file"]]
            base_version = int(request["base_version"])
            text = str(request["text"])
        except (ValueError, KeyError, TypeError):
            return self._respond_json({"code": "bad_request"}, 400)
        slides_root = (self.server.deck_dir / SLIDES_DIR_NAME).resolve()
        folder = (slides_root / str(request.get("slide", ""))).resolve()
        if folder.parent != slides_root or not folder.is_dir():
            return self._respond_json({"code": "slide_not_found"}, 404)
        target = folder / file_name
        if target.is_file() and target.stat().st_mtime_ns > base_version:
            return self._respond_json({"code": "changed_on_disk"}, 409)
        target.write_text(text.rstrip() + "\n" if text.strip() else "", encoding="utf-8")
        return self._respond_json({"code": "saved", "version": deck_version(self.server.deck_dir)})


    def _save_slide_order(self) -> None:
        """흐름 보기에서 끈 순서 > deck.json slides (같은 장 집합일 때만, 종류 유지)"""
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_SAVE_BYTES:
            return self._respond_json({"code": "bad_size"}, 413)
        deck_file = self.server.deck_dir / DECK_FILE_NAME
        try:
            request = json.loads(self.rfile.read(length))
            order = [str(slide_id) for slide_id in request["order"]]
            base_version = int(request["base_version"])
            settings = json.loads(deck_file.read_text(encoding="utf-8"))
        except (ValueError, KeyError, TypeError, OSError):
            return self._respond_json({"code": "bad_request"}, 400)
        if deck_file.stat().st_mtime_ns > base_version:
            return self._respond_json({"code": "changed_on_disk"}, 409)
        entries = {(entry if isinstance(entry, str) else entry.get("id")): entry for entry in settings.get("slides") or []}
        if sorted(entries) != sorted(order):
            return self._respond_json({"code": "slides_differ"}, 409)
        settings["slides"] = [entries[slide_id] for slide_id in order]
        deck_file.write_text(json.dumps(settings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return self._respond_json({"code": "saved", "version": deck_version(self.server.deck_dir)})

    def _save_recording(self, query: dict) -> None:
        """연습 화면 녹음 > recordings/<label>/: 검증(형식·크기·장 시각) > 상태 폴더에 받기 > 녹음 폴더로 이동"""
        extension = (query.get("ext") or [""])[0]
        length = int(self.headers.get("Content-Length") or 0)
        if extension not in RECORDING_EXTENSIONS:
            return self._respond_json({"code": "bad_format"}, 400)
        if length <= 0 or length > MAX_RECORDING_BYTES:
            return self._respond_json({"code": "bad_size"}, 413)
        try:
            marks, duration_seconds = parse_marks(urllib.parse.unquote(self.headers.get(MARKS_HEADER) or ""))
        except (ValueError, KeyError, TypeError):
            return self._respond_json({"code": "bad_marks"}, 400)
        # 받는 중 파일은 상태 폴더에 (버전 계산·화면 다시 그리기에서 빠짐)
        state_dir = self.server.deck_dir / STATE_DIR_NAME
        state_dir.mkdir(parents=True, exist_ok=True)
        incoming = state_dir / f"incoming-{secrets.token_hex(4)}.{extension}"
        try:
            with incoming.open("wb") as audio_file:
                remaining = length
                while remaining > 0:
                    chunk = self.rfile.read(min(RECORDING_COPY_CHUNK_BYTES, remaining))
                    if not chunk:
                        return self._respond_json({"code": "incomplete"}, 400)
                    audio_file.write(chunk)
                    remaining -= len(chunk)
            saved = save_page_recording(self.server.deck_dir, extension, incoming, marks, duration_seconds)
        finally:
            incoming.unlink(missing_ok=True)  # (성공·실패 공통: 이동했으면 이미 없음)
        return self._respond_json({"code": "saved", **saved, "version": deck_version(self.server.deck_dir)})


def watch_idle(server: DeckServer) -> None:
    while True:
        time.sleep(IDLE_CHECK_SECONDS)
        if time.monotonic() - server.last_request_at > server.idle_shutdown_seconds:
            server.shutdown()
            return


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--deck", required=True)
    parser.add_argument("--idle-minutes", type=int, default=IDLE_SHUTDOWN_SECONDS // 60)
    args = parser.parse_args()
    deck_dir = Path(args.deck).resolve()
    server = DeckServer(deck_dir, secrets.token_urlsafe(18), secrets.token_hex(8))
    server.idle_shutdown_seconds = max(60, args.idle_minutes * 60)
    state_dir = deck_dir / STATE_DIR_NAME
    state_dir.mkdir(parents=True, exist_ok=True)
    info = {"pid": os.getpid(), "port": server.server_address[1], "key": server.key, "server_token": server.token,
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    (state_dir / SERVER_INFO_FILE_NAME).write_text(json.dumps(info), encoding="utf-8")
    threading.Thread(target=watch_idle, args=(server,), daemon=True).start()
    try:
        server.serve_forever()
    finally:
        (state_dir / SERVER_INFO_FILE_NAME).unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
