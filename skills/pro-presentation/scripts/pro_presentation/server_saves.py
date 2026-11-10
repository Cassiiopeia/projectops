"""연습 화면 서버의 쓰기 요청: 대본 · 메모 저장, 장 순서, 배치, 녹음 받기, 서버 끄기
RequestHandler 가 섞어 쓰는 묶음 (server.py). 접근 검사 · 응답 함수는 RequestHandler 쪽
"""
from __future__ import annotations

import json
import secrets
import threading
import urllib.parse

from pro_presentation.layout_state import save_layout
from pro_presentation.recording_marks import RECORDING_EXTENSIONS, parse_marks, save_page_recording
from pro_presentation.settings import DECK_FILE_NAME, SAVABLE_FILES, SLIDES_DIR_NAME, STATE_DIR_NAME

MAX_SAVE_BYTES = 512 * 1024
# 연습 화면 녹음 최대 크기 (300MB, opus 기준 몇 시간) · 장 넘긴 시각을 담는 헤더 (encodeURIComponent JSON)
MAX_RECORDING_BYTES = 300 * 1024 * 1024
RECORDING_COPY_CHUNK_BYTES = 1024 * 1024
MARKS_HEADER = "X-Recording-Marks"


class SaveHandlers:
    def do_POST(self):  # noqa: N802  (표준 라이브러리 서명)
        parsed = urllib.parse.urlsplit(self.path)
        if not self._check_access(urllib.parse.parse_qs(parsed.query)):
            return None
        if parsed.path == "/api/save":
            return self._save_slide_file()
        if parsed.path == "/api/order":
            return self._save_slide_order()
        if parsed.path == "/api/layout":
            request = self._read_json_request()
            return None if request is None else self._respond_json(save_layout(self.server.deck_dir, request))
        if parsed.path == "/api/recording":
            return self._save_recording(urllib.parse.parse_qs(parsed.query))
        if parsed.path == "/api/stop":
            self._respond_json({"stopped": True})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return None
        return self._respond(404, b"not found")

    def _read_json_request(self) -> dict | None:
        """JSON 본문 읽기 (크기 · 형식 오류는 여기서 응답하고 None)"""
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_SAVE_BYTES:
            self._respond_json({"code": "bad_size"}, 413)
            return None
        try:
            request = json.loads(self.rfile.read(length))
        except ValueError:
            request = None
        if not isinstance(request, dict):
            self._respond_json({"code": "bad_request"}, 400)
            return None
        return request

    def _save_slide_file(self) -> None:
        """브라우저 고침 > 장 파일. 읽은 뒤 파일이 바뀌었으면 덮어쓰지 않음 (409)"""
        request = self._read_json_request()
        if request is None:
            return None
        try:
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
        return self._respond_json({"code": "saved", "version": self.server.current_version(is_fresh=True)})

    def _save_slide_order(self) -> None:
        """흐름 보기에서 끈 순서 > deck.json slides (같은 장 집합일 때만, 종류 유지)"""
        request = self._read_json_request()
        if request is None:
            return None
        deck_file = self.server.deck_dir / DECK_FILE_NAME
        try:
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
        return self._respond_json({"code": "saved", "version": self.server.current_version(is_fresh=True)})

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
        return self._respond_json({"code": "saved", **saved, "version": self.server.current_version(is_fresh=True)})
