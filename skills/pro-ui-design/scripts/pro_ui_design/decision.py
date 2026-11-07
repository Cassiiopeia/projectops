"""결정 기록: decide 저장, decision 조회. 다음 스킬(구현, 보고서, 테스트, 디자이너 요청)이 이어받는 유일한 약속
{run_dir}/decision.json: title, issue, chosen, chosen_name, reason, screen, captures, tokens, comment_url, run_dir
"""
from __future__ import annotations

import json
from pathlib import Path

from common.emit import emit

from pro_ui_design.session import Session, find_current_session, write_json_atomically
from pro_ui_design.session_commands import read_events

DECISION_FILE_NAME = "decision.json"
CAPTURES_FOLDER_NAME = "captures"
TOKENS_FILE_NAME = "tokens.css"


def _newest_screen(session: Session) -> str | None:
    screens = [path for path in session.screens_dir.glob("*.html") if not path.name.startswith("_")]
    return max(screens, key=lambda path: path.stat().st_mtime).name if screens else None


def _find_clicked_event(session: Session, choice: str) -> dict | None:
    """터미널로만 고른 경우 없음"""
    return next((event for event in reversed(read_events(session)) if event.get("choice") == choice), None)


def _list_captures(session: Session, screen: str | None) -> list[str]:
    if not screen:
        return []
    captures = Path(session.run_dir) / CAPTURES_FOLDER_NAME
    return sorted(str(path) for path in captures.glob(f"{Path(screen).stem}*") if path.is_file())


def cmd_decide(args) -> int:
    session = find_current_session(Path(args.root).resolve())
    if session is None:
        return emit({"ok": False, "code": "no_session", "error": "No mockup session for this project",
                     "next": "ui_design_cli.py start --title <screen name>"})
    clicked = _find_clicked_event(session, args.choice)
    screen = args.screen or (clicked or {}).get("screen") or _newest_screen(session)
    tokens_file = session.screens_dir / TOKENS_FILE_NAME
    decision = {"title": session.title, "issue": args.issue or session.issue, "chosen": args.choice,
                "chosen_name": (clicked or {}).get("text"), "reason": args.reason, "screen": screen,
                "captures": _list_captures(session, screen), "tokens": str(tokens_file) if tokens_file.is_file() else None,
                "comment_url": args.comment_url, "run_dir": session.run_dir}
    write_json_atomically(Path(session.run_dir) / DECISION_FILE_NAME, decision)
    return emit({"decision": decision, "summary": f"Recorded: {args.choice}",
                 "next": ("Implement the chosen option from this mockup. Add one line under ## Decisions in the project notes. "
                          "pro-agent-test and pro-report read this with decision.")})


def find_latest_decision(root: Path) -> dict | None:
    """현재 세션 우선. 없으면 같은 산출물 폴더의 가장 최근 결정 (다른 제목으로 새 세션을 열어도 찾음)"""
    session = find_current_session(root)
    if session is None:
        return None
    run_dir = Path(session.run_dir)
    current = run_dir / DECISION_FILE_NAME
    candidates = [current] if current.is_file() else sorted(run_dir.parent.glob(f"*/{DECISION_FILE_NAME}"),
                                                            key=lambda path: path.stat().st_mtime, reverse=True)
    for candidate in candidates:
        try:
            return json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
    return None


def cmd_decision(args) -> int:
    decision = find_latest_decision(Path(args.root).resolve())
    return emit({"decision": decision, "summary": f"Chosen: {decision['chosen']}" if decision else "No decision recorded"})
