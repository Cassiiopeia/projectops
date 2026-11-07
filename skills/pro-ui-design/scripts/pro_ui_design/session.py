"""시안 세션: 폴더 위치 결정, session.json 읽기/쓰기, 레포별 현재 세션 포인터
세션 폴더 구조: {run_dir}/session.json · screens/(시안, 자산) · state/(events.jsonl, server-info.json, server.log)
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import subprocess
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

from common.paths import resolve_output_path
from common.state import base_dir
from common.title import normalize

from pro_ui_design.settings import SKILL_ID

SESSION_FILE_NAME = "session.json"
SCREENS_FOLDER_NAME = "screens"
STATE_FOLDER_NAME = "state"
EVENTS_FILE_NAME = "events.jsonl"
SERVER_INFO_FILE_NAME = "server-info.json"
SERVER_LOG_FILE_NAME = "server.log"
SESSION_KEY_BYTES = 32


@dataclass
class Session:
    run_dir: str
    title: str
    key: str
    issue: int | None = None
    port: int = 0
    server_token: str = ""
    idle_seconds: int = 14400
    viewer: dict = field(default_factory=dict)

    @property
    def screens_dir(self) -> Path:
        return Path(self.run_dir) / SCREENS_FOLDER_NAME

    @property
    def state_dir(self) -> Path:
        return Path(self.run_dir) / STATE_FOLDER_NAME

    @property
    def url(self) -> str:
        return f"http://localhost:{self.port}/?key={self.key}"


def _git_top_level(root: Path) -> str | None:
    try:
        output = subprocess.run(["git", "-C", str(root), "rev-parse", "--show-toplevel"], capture_output=True,
                                text=True, encoding="utf-8", errors="replace", timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return output.stdout.strip() if output.returncode == 0 and output.stdout.strip() else None


def _project_hash(root: Path) -> str:
    """레포 또는 폴더 경로 > 짧은 해시 (원격 없는 레포끼리 섞이지 않게)"""
    identity = _git_top_level(root) or str(root.resolve())
    return hashlib.sha256(str(Path(identity).resolve()).encode("utf-8")).hexdigest()[:16]


def _pointer_file(root: Path) -> Path:
    return base_dir() / SKILL_ID / "current" / f"{_project_hash(root)}.json"


def resolve_run_dir(root: Path, title: str, issue: int | None) -> tuple[Path | None, dict]:
    """세션 폴더: Git 레포 > 산출물 폴더(자동 .gitignore), 그 외 > projectops 상태 폴더"""
    if _git_top_level(root) is None:
        name = f"{date.today():%Y%m%d}_{normalize(title) or 'untitled'}"
        return base_dir() / SKILL_ID / "sessions" / _project_hash(root) / name, {"gitignore": "outside_repo"}
    resolved = resolve_output_path(SKILL_ID, title, root=str(root), issue=issue)
    if resolved.get("ok") is False:
        return None, resolved
    document = Path(resolved["path"])
    return document.parent / document.stem, {"gitignore": resolved.get("gitignore"),
                                             "output_root": resolved.get("output_root")}


def write_json_atomically(path: Path, payload: dict) -> None:
    """임시 파일 > 교체: 서버와 CLI 가 동시에 읽어도 반쪽 JSON 없음"""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(descriptor, "w", encoding="utf-8") as temporary_file:
        json.dump(payload, temporary_file, ensure_ascii=False, indent=2)
    os.replace(temporary_name, path)


def load_session(run_dir: Path) -> Session | None:
    try:
        data = json.loads((run_dir / SESSION_FILE_NAME).read_text(encoding="utf-8"))
        return Session(run_dir=str(run_dir), title=data["title"], key=data["key"], issue=data.get("issue"),
                       port=int(data.get("port") or 0), server_token=data.get("server_token") or "",
                       idle_seconds=int(data.get("idle_seconds") or 14400), viewer=data.get("viewer") or {})
    except (OSError, ValueError, KeyError, TypeError):
        return None


def save_session(session: Session) -> None:
    write_json_atomically(Path(session.run_dir) / SESSION_FILE_NAME, asdict(session))


def create_or_reuse_session(root: Path, run_dir: Path, title: str, issue: int | None) -> Session:
    """같은 세션 폴더면 키와 포트 유지 (열린 탭의 주소가 그대로 살아 있게)"""
    session = load_session(run_dir)
    if session is None:
        session = Session(run_dir=str(run_dir), title=title, key=secrets.token_hex(SESSION_KEY_BYTES), issue=issue)
    session.screens_dir.mkdir(parents=True, exist_ok=True)
    session.state_dir.mkdir(parents=True, exist_ok=True)
    set_current_session(root, session)
    return session


def set_current_session(root: Path, session: Session) -> None:
    write_json_atomically(_pointer_file(root), {"run_dir": session.run_dir})


def find_current_session(root: Path) -> Session | None:
    """대화가 압축되어도 복구: 레포 > 마지막 세션"""
    try:
        pointer = json.loads(_pointer_file(root).read_text(encoding="utf-8"))
        return load_session(Path(pointer["run_dir"]))
    except (OSError, ValueError, KeyError, TypeError):
        return None
