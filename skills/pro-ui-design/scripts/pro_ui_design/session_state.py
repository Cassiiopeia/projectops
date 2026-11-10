"""시안 서버의 세션 값: 세션 폴더 읽기 · 시안 목록과 변경 지문 · 요청 경로 확인
server.py 가 같은 폴더에서 바로 불러 씀 (표준 라이브러리 전용, 분리 프로세스 실행)
"""
from __future__ import annotations

import hashlib
import json
import secrets
import threading
import time
from pathlib import Path


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
