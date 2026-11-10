"""연습 화면 서버 (표준 라이브러리 전용, 분리 프로세스로 실행)
요청 처리: Host 확인 > 키 확인 > 경로별 처리. 127.0.0.1 전용, 덱 폴더·스킬 자산 밖 접근 차단
"""
from __future__ import annotations

import argparse
import http.server
import json
import os
import secrets
import subprocess
import sys
import threading
import time
import urllib.parse
from pathlib import Path

# 분리 실행 시 패키지 import 경로 (이 파일: scripts/pro_presentation/server.py)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pro_presentation.deck import deck_version, load_deck  # noqa: E402
from pro_presentation.image_variants import find_variant  # noqa: E402
from pro_presentation.layout_state import read_layout  # noqa: E402
from pro_presentation.server_saves import SaveHandlers  # noqa: E402
from pro_presentation.settings import (IMAGE_SUFFIXES, PRACTICE_ASSETS_DIR, SERVER_INFO_FILE_NAME,  # noqa: E402
                                       SLIDES_DIR_NAME, STATE_DIR_NAME, THEME_FILE_NAME)

BIND_HOST = "127.0.0.1"
ALLOWED_HOST_NAMES = {"localhost", BIND_HOST}
KEY_HEADER = "X-Presentation-Key"
KEY_COOKIE = "presentation_key"
# 요청이 없으면 스스로 종료 (2시간)
IDLE_SHUTDOWN_SECONDS = 2 * 60 * 60
IDLE_CHECK_SECONDS = 60
# 응답을 모았다가 한 번에 보냄 (64KB): 머리말과 본문을 따로 보내면 요청마다 지연 (Windows 에서 특히 큼)
RESPONSE_BUFFER_BYTES = 64 * 1024
# 연결 재사용 (HTTP/1.1): 요청마다 새로 연결하면 브라우저가 요청을 보내기까지 수십 ms 가 걸림 (실측 33ms)
# 쉬는 연결은 이 시간(초) 뒤에 닫음
KEEP_ALIVE_PROTOCOL = "HTTP/1.1"
IDLE_CONNECTION_SECONDS = 120
# 덱 버전 기억 시간 (초): 열린 창마다 2초에 한 번씩 묻는 것을 한 번의 폴더 읽기로
VERSION_MEMO_SECONDS = 0.5
# 캐시: 덱 파일은 계속 바뀜 > 기본은 저장 금지. 파일은 매번 확인(바뀌지 않았으면 304), 주소에 v= 가 있으면 오래 기억
CACHE_NEVER = "no-store"
CACHE_REVALIDATE = "no-cache"
CACHE_VERSIONED = "private, max-age=31536000, immutable"
# 그림 사본 만들기 (image_variants.py 단독 실행): 한 번에 만드는 개수 · 한 번의 시간 제한 (초)
IMAGE_SCRIPT = Path(__file__).resolve().parent / "image_variants.py"
IMAGE_BATCH_COUNT = 8
IMAGE_BUILD_TIMEOUT_SECONDS = 600
# Windows: 분리 실행된 서버가 자식 프로세스를 띄울 때 콘솔 창이 뜨지 않게 (CREATE_NO_WINDOW)
NO_WINDOW_FLAGS = {"creationflags": 0x08000000} if sys.platform == "win32" else {}
PRACTICE_ASSETS = {"practice.js", "slides.js", "flow.js", "recorder.js", "layout.js", "popout.js", "practice.css",
                   "i18n.ko.json"}
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8", ".md": "text/plain; charset=utf-8", ".txt": "text/plain; charset=utf-8",
    ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
    ".webp": "image/webp", ".woff": "font/woff", ".woff2": "font/woff2", ".ttf": "font/ttf", ".otf": "font/otf",
}


class DeckServer(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, deck_dir: Path, key: str, token: str, image_python: str | None = None):
        super().__init__((BIND_HOST, 0), RequestHandler)
        self.deck_dir = deck_dir
        self.key = key
        self.token = token
        self.last_request_at = time.monotonic()
        self.idle_shutdown_seconds = IDLE_SHUTDOWN_SECONDS
        # 그림 사본: Pillow 가 있는 파이썬 (없으면 원본 그대로) · 만들기 요청 · 만든 횟수 (화면이 새 사본을 받게)
        self.image_python = image_python
        self.images_wanted = threading.Event()
        self.images_generation = 0
        self._version_memo = (0.0, 0)
        self._version_lock = threading.Lock()

    def current_version(self, is_fresh: bool = False) -> int:
        """덱 버전 (+ 그림 사본 세대). 저장 직후(is_fresh)가 아니면 잠깐 기억한 값"""
        with self._version_lock:
            read_at, version = self._version_memo
            if is_fresh or time.monotonic() - read_at > VERSION_MEMO_SECONDS:
                version = deck_version(self.deck_dir)
                self._version_memo = (time.monotonic(), version)
        return version + self.images_generation


class RequestHandler(SaveHandlers, http.server.BaseHTTPRequestHandler):
    server: DeckServer
    protocol_version = KEEP_ALIVE_PROTOCOL
    timeout = IDLE_CONNECTION_SECONDS
    disable_nagle_algorithm = True
    wbufsize = RESPONSE_BUFFER_BYTES

    def log_message(self, format, *args):  # noqa: A002  (표준 라이브러리 서명)
        return

    def _respond(self, status: int, body: bytes = b"", content_type: str = "text/plain; charset=utf-8",
                 headers: dict | None = None, cache_control: str = CACHE_NEVER) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        if status != 304:
            self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache_control)
        if status >= 400:
            # 거부한 요청은 본문을 읽지 않았을 수 있음 > 연결을 닫아 남은 본문이 다음 요청으로 읽히지 않게
            self.close_connection = True
            self.send_header("Connection", "close")
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _respond_json(self, payload: dict, status: int = 200) -> None:
        self._respond(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _respond_file(self, target: Path, query: dict) -> None:
        """파일 응답: 브라우저가 가진 것과 같으면 304 (본문 없음)"""
        stat = target.stat()
        etag = f'"{stat.st_mtime_ns:x}-{stat.st_size:x}"'
        content_type = CONTENT_TYPES.get(target.suffix.lower(), "application/octet-stream")
        cache_control = CACHE_VERSIONED if query.get("v") else CACHE_REVALIDATE
        if self.headers.get("If-None-Match") == etag:
            return self._respond(304, b"", content_type, {"ETag": etag}, cache_control)
        return self._respond(200, target.read_bytes(), content_type, {"ETag": etag}, cache_control)

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
            return self._serve_render(route[len("/render/"):], cookie, query)
        if route.startswith("/assets/"):
            return self._serve_asset(route[len("/assets/"):], query)
        if route.startswith("/deck/"):
            return self._serve_deck_file(route[len("/deck/"):], query)
        if route == "/api/deck":
            return self._respond_json({**load_deck(self.server.deck_dir), "version": self.server.current_version(),
                                       "images_generation": self.server.images_generation})
        if route == "/api/version":
            return self._respond_json({"version": self.server.current_version()})
        if route == "/api/layout":
            return self._respond_json(read_layout(self.server.deck_dir))
        return self._respond(404, b"not found")

    def _serve_asset(self, name: str, query: dict) -> None:
        if name not in PRACTICE_ASSETS:
            return self._respond(404, b"not found")
        return self._respond_file(PRACTICE_ASSETS_DIR / name, query)

    def _resolve_deck_file(self, relative_path: str) -> Path | None:
        """덱 폴더 안 파일만 (.. · 상태 폴더 차단)"""
        deck_root = self.server.deck_dir.resolve()
        candidate = (deck_root / relative_path).resolve()
        if deck_root not in candidate.parents or not candidate.is_file():
            return None
        if candidate.relative_to(deck_root).parts[0] == STATE_DIR_NAME:
            return None
        return candidate

    def _serve_deck_file(self, relative_path: str, query: dict) -> None:
        target = self._resolve_deck_file(relative_path)
        if target is None:
            return self._respond(404, b"not found")
        if target.suffix.lower() in IMAGE_SUFFIXES:
            target = self._display_image(target, is_thumbnail=bool(query.get("w")))
        return self._respond_file(target, query)

    def _display_image(self, source: Path, is_thumbnail: bool) -> Path:
        """큰 그림 > 화면용 사본 (썸네일 사본이 아직 없으면 보기용). 사본이 없으면 만들기를 요청하고 원본"""
        for kind in (("thumb", "view") if is_thumbnail else ("view",)):
            variant, is_decided = find_variant(self.server.deck_dir, source, kind)
            if not is_decided and self.server.image_python:
                self.server.images_wanted.set()
            if variant is not None:
                return variant
        return source

    def _serve_render(self, slide_id: str, cookie: dict, query: dict) -> None:
        """한 장을 1920x1080 단독 페이지로 (연습 화면 iframe · 내보내기 캡처 공용)"""
        slide_file = self._resolve_deck_file(f"{SLIDES_DIR_NAME}/{slide_id}/slide.html")
        if slide_file is None:
            return self._respond(404, b"slide not found")
        template = (PRACTICE_ASSETS_DIR / "render.html").read_text(encoding="utf-8")
        page = (template.replace("__THEME_URL__", f"/deck/{THEME_FILE_NAME}")
                .replace("__BASE_URL__", f"/deck/{SLIDES_DIR_NAME}/{urllib.parse.quote(slide_id)}/")
                .replace("__SLIDE_HTML__", slide_file.read_text(encoding="utf-8", errors="replace")))
        return self._respond(200, page.encode("utf-8"), CONTENT_TYPES[".html"], cookie,
                             CACHE_VERSIONED if query.get("v") else CACHE_NEVER)


def watch_idle(server: DeckServer) -> None:
    while True:
        time.sleep(IDLE_CHECK_SECONDS)
        if time.monotonic() - server.last_request_at > server.idle_shutdown_seconds:
            server.shutdown()
            return


def build_images(server: DeckServer) -> None:
    """그림 사본 만들기: 요청(시작할 때 · 사본 없는 그림을 보낼 때)마다 별도 프로세스로 몇 개씩 (서버 응답은 계속)
    한 묶음이 끝날 때마다 세대를 올려 화면이 가벼운 사본으로 바꿔 받음. 만들 수 없으면 (Pillow 없음) 그만둠"""
    while server.image_python:
        server.images_wanted.wait()
        server.images_wanted.clear()
        try:
            output = subprocess.run([server.image_python, str(IMAGE_SCRIPT), "--deck", str(server.deck_dir),
                                     "--limit", str(IMAGE_BATCH_COUNT)], capture_output=True, encoding="utf-8",
                                    errors="replace", timeout=IMAGE_BUILD_TIMEOUT_SECONDS, **NO_WINDOW_FLAGS)
            result = json.loads(output.stdout.strip().splitlines()[-1])
        except (OSError, subprocess.SubprocessError, ValueError, IndexError):
            result = {}
        if not result.get("ok"):
            server.image_python = None
        if result.get("built"):
            server.images_generation += 1
        if result.get("has_more"):
            server.images_wanted.set()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--deck", required=True)
    parser.add_argument("--idle-minutes", type=int, default=IDLE_SHUTDOWN_SECONDS // 60)
    parser.add_argument("--image-python", default=None, help="Python that has Pillow (builds display-sized image copies)")
    args = parser.parse_args()
    deck_dir = Path(args.deck).resolve()
    server = DeckServer(deck_dir, secrets.token_urlsafe(18), secrets.token_hex(8), args.image_python)
    server.idle_shutdown_seconds = max(60, args.idle_minutes * 60)
    state_dir = deck_dir / STATE_DIR_NAME
    state_dir.mkdir(parents=True, exist_ok=True)
    info = {"pid": os.getpid(), "port": server.server_address[1], "key": server.key, "server_token": server.token,
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    (state_dir / SERVER_INFO_FILE_NAME).write_text(json.dumps(info), encoding="utf-8")
    threading.Thread(target=watch_idle, args=(server,), daemon=True).start()
    server.images_wanted.set()
    threading.Thread(target=build_images, args=(server,), daemon=True).start()
    try:
        server.serve_forever()
    finally:
        (state_dir / SERVER_INFO_FILE_NAME).unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
