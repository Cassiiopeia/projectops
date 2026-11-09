"""세션 명령: start(덱 만들기·서버 실행) · status · stop
서버는 덱 하나에 하나. 상태는 덱 안 .presentation/server.json, 마지막 덱은 ~/.projectops/presentation/
"""
from __future__ import annotations

import http.client
import json
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

from common.emit import emit
from common.state import base_dir

from pro_presentation.config import option_value
from pro_presentation.deck import load_deck
from pro_presentation.settings import (DECK_FILE_NAME, DECK_TEMPLATE_DIR, INIT_QUESTIONS, LAST_DECK_RELATIVE,
                                       MEMORY_FILE_NAME, SERVER_INFO_FILE_NAME, SERVER_LOG_FILE_NAME,
                                       SKILL_ID, STATE_DIR_NAME, USER_MEMORY_RELATIVE)

GITIGNORE_TEMPLATE_NAME = "gitignore.template"

SERVER_SCRIPT = Path(__file__).resolve().parent / "server.py"
SERVER_START_TIMEOUT_SECONDS = 8
HEALTH_REQUEST_TIMEOUT_SECONDS = 2
NEXT_AFTER_CREATE = ("Ask the init questions one at a time (references/init-questions.md), write the answers into "
                     "deck.json and memory.md, then build or import the slides. Give the user the url.")
NEXT_AFTER_RESUME = ("Read memory.md first, then give the user the url and continue rehearsing slide by slide "
                     "(references/coaching.md).")


def _http(port: int, method: str, path: str, key: str = "") -> dict | None:
    request = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method=method,
                                     headers={"X-Presentation-Key": key, "Host": "localhost"})
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
                request, timeout=HEALTH_REQUEST_TIMEOUT_SECONDS) as response:
            body = response.read()
        parsed = json.loads(body) if body else {}
    except (OSError, urllib.error.URLError, http.client.HTTPException, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def read_server_info(deck_dir: Path) -> dict | None:
    """살아 있고 이 덱의 서버일 때만 정보 반환 (같은 포트의 다른 프로세스 구분)"""
    try:
        info = json.loads((deck_dir / STATE_DIR_NAME / SERVER_INFO_FILE_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    state = _http(int(info.get("port") or 0), "GET", "/api/state")
    if not state or state.get("server_token") != info.get("server_token"):
        return None
    return info


def server_url(info: dict, path: str = "/") -> str:
    return f"http://127.0.0.1:{info['port']}{path}?key={urllib.parse.quote(info['key'])}"


def _spawn_server(deck_dir: Path, idle_minutes: int) -> dict | None:
    """터미널을 닫아도 살아 있게 분리 실행 > server.json 대기"""
    state_dir = deck_dir / STATE_DIR_NAME
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / SERVER_INFO_FILE_NAME).unlink(missing_ok=True)
    detach = ({"creationflags": 0x00000008 | 0x00000200} if sys.platform == "win32"   # DETACHED_PROCESS | NEW_GROUP
              else {"start_new_session": True})
    with (state_dir / SERVER_LOG_FILE_NAME).open("a", encoding="utf-8") as log:
        subprocess.Popen([sys.executable, str(SERVER_SCRIPT), "--deck", str(deck_dir), "--idle-minutes", str(idle_minutes)],
                         stdin=subprocess.DEVNULL, stdout=log, stderr=log, close_fds=True, **detach)
    deadline = time.monotonic() + SERVER_START_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        info = read_server_info(deck_dir)
        if info:
            return info
        time.sleep(0.1)
    return None


def _last_decks_file() -> Path:
    return base_dir() / LAST_DECK_RELATIVE


def remember_deck(project_root: Path, deck_dir: Path) -> None:
    path = _last_decks_file()
    try:
        decks = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        decks = {}
    decks[str(project_root)] = str(deck_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(decks, ensure_ascii=False, indent=1), encoding="utf-8")


def resolve_deck(deck: str | None, root: str | None) -> Path | None:
    """--deck > 이 프로젝트에서 마지막으로 연 덱"""
    if deck:
        return Path(deck).expanduser().resolve()
    try:
        decks = json.loads(_last_decks_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    remembered = decks.get(str(Path(root or ".").resolve()))
    return Path(remembered) if remembered else None


def create_deck(deck_dir: Path, title: str | None, root: Path) -> list[str]:
    """템플릿 복사 (있는 파일은 덮지 않음) > 제목 · 언어 · 제한시간 · 사용자 발표 메모리 반영. 만든 파일 목록"""
    created = []
    for source in sorted(DECK_TEMPLATE_DIR.rglob("*")):
        relative = source.relative_to(DECK_TEMPLATE_DIR)
        # 템플릿 폴더 자체가 git 에서 빠지지 않게 gitignore.template 로 두고 복사할 때 이름을 바꾼다
        target = deck_dir / (".gitignore" if relative.name == GITIGNORE_TEMPLATE_NAME else relative)
        if source.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            created.append(str(target.relative_to(deck_dir)))
    user_memory = base_dir() / USER_MEMORY_RELATIVE
    if option_value(root, "seed_user_memory") and user_memory.is_file() and MEMORY_FILE_NAME in created:
        shutil.copyfile(user_memory, deck_dir / MEMORY_FILE_NAME)
    settings = json.loads((deck_dir / DECK_FILE_NAME).read_text(encoding="utf-8"))
    settings["title"] = title or settings.get("title")
    settings["language"] = option_value(root, "language") or _preferences_language(root) or settings.get("language")
    settings["time_limit_seconds"] = option_value(root, "time_limit_seconds") or settings.get("time_limit_seconds")
    (deck_dir / DECK_FILE_NAME).write_text(json.dumps(settings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return created


def _preferences_language(root: Path) -> str | None:
    """공통 preferences 의 language (없으면 None)"""
    try:
        from common.preferences import detect_repo, resolve as resolve_preferences
        owner, repo = detect_repo(str(root))
        language = (resolve_preferences("pro-presentation", owner, repo, load=True).get("values") or {}).get("language")
    except Exception:  # 선호 설정이 깨져도 덱 생성은 계속
        return None
    return language if isinstance(language, str) and language else None


def _default_deck_dir(root: Path, title: str | None) -> Path | None:
    """--deck 없음 > deck_root 설정 > get-output-path 자리"""
    configured = option_value(root, "deck_root")
    name = "".join(character if character.isalnum() or character in "-_" else "-" for character in (title or "talk")).strip("-")
    if configured:
        base = Path(configured).expanduser()
        return (base if base.is_absolute() else root / base) / (name or "talk")
    try:
        from common.paths import resolve_output_path
    except ImportError:
        return None
    result = resolve_output_path(SKILL_ID, title, root=str(root))
    if result.get("ok") is False:
        return None
    path = Path(result["path"])
    return path.parent / path.stem


def cmd_start(args) -> int:
    root = Path(args.root or ".").resolve()
    deck_dir = Path(args.deck).expanduser().resolve() if args.deck else (resolve_deck(None, args.root) or _default_deck_dir(root, args.title))
    if deck_dir is None:
        return emit({"ok": False, "code": "no_deck", "error": "Give --deck, or set deck_root",
                     "next": "start --deck <folder> --title \"<talk title>\""})
    is_new = not (deck_dir / DECK_FILE_NAME).is_file()
    created = create_deck(deck_dir, args.title, root) if is_new else []
    info = read_server_info(deck_dir) or _spawn_server(deck_dir, option_value(root, "idle_timeout_minutes"))
    if info is None:
        log_file = deck_dir / STATE_DIR_NAME / SERVER_LOG_FILE_NAME
        tail = log_file.read_text(encoding="utf-8", errors="replace")[-500:] if log_file.is_file() else ""
        return emit({"ok": False, "code": "server_failed", "error": "The practice server did not start",
                     "log_tail": tail, "next": "Read log_tail, fix the cause, then run start again"})
    remember_deck(root, deck_dir)
    url = server_url(info)
    if args.open or option_value(root, "auto_open"):
        webbrowser.open(url)
    deck = load_deck(deck_dir)
    result = {"summary": f"{'Created' if is_new else 'Opened'} deck '{deck['title']}' ({len(deck['slides'])} slides) at {url}",
              "deck_dir": str(deck_dir), "url": url, "created": is_new, "slide_count": len(deck["slides"]),
              "problems": deck["problems"], "next": NEXT_AFTER_CREATE if is_new else NEXT_AFTER_RESUME}
    if is_new:
        result.update({"created_files": len(created), "needs_init_questions": True,
                       "questions": [dict(question) for question in INIT_QUESTIONS]})
    return emit(result)


def cmd_status(args) -> int:
    deck_dir = resolve_deck(args.deck, args.root)
    if deck_dir is None:
        return emit({"ok": False, "code": "no_deck", "error": "No deck given and none opened in this project",
                     "next": "start --deck <folder>"})
    info = read_server_info(deck_dir)
    return emit({"summary": f"{deck_dir}: {'running at ' + server_url(info) if info else 'not running'}",
                 "deck_dir": str(deck_dir), "running": bool(info), "url": server_url(info) if info else None,
                 "next": None if info else f"start --deck \"{deck_dir}\""})


def cmd_stop(args) -> int:
    deck_dir = resolve_deck(args.deck, args.root)
    if deck_dir is None:
        return emit({"ok": False, "code": "no_deck", "error": "No deck given and none opened in this project"})
    info = read_server_info(deck_dir)
    if info is None:
        return emit({"summary": "Server was not running", "deck_dir": str(deck_dir), "stopped": False})
    _http(int(info["port"]), "POST", "/api/stop", info["key"])
    return emit({"summary": f"Stopped the server for {deck_dir}; the deck files are kept",
                 "deck_dir": str(deck_dir), "stopped": True})
