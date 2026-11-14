"""Decision record: decide saves, decision reads. The only contract later skills (build, report, test, designer request) pick up
{run_dir}/decision.json: title, issue, chosen, chosen_name, reason, screen, captures, tokens, comment_url, run_dir
"""
from __future__ import annotations

import glob
import json
from pathlib import Path

from common.emit import emit

from pro_ui_design.session import Session, find_current_session, find_session, list_project_sessions, write_json_atomically
from pro_ui_design.session_commands import read_events
from pro_ui_design.settings import CAPTURES_FOLDER_NAME, SESSION_TOKENS_FILE_NAME

DECISION_FILE_NAME = "decision.json"


def _newest_screen(session: Session) -> str | None:
    screens = [path for path in session.screens_dir.glob("*.html") if not path.name.startswith("_")]
    return max(screens, key=lambda path: path.stat().st_mtime).name if screens else None


def _find_clicked_event(session: Session, choice: str) -> dict | None:
    """None when picked only in the terminal"""
    return next((event for event in reversed(read_events(session)) if event.get("choice") == choice), None)


def _list_captures(session: Session, screen: str | None) -> list[str]:
    if not screen:
        return []
    captures = Path(session.run_dir) / CAPTURES_FOLDER_NAME
    stem = glob.escape(Path(screen).stem)   # Anchor on the separator so layout does not also match layout-v2
    return sorted(str(path) for pattern in (f"{stem}.*", f"{stem}__*") for path in captures.glob(pattern) if path.is_file())


def cmd_decide(args) -> int:
    session = find_session(Path(args.root).resolve(), args.title)
    if session is None:
        return emit({"ok": False, "code": "no_session", "error": "No mockup session for this project",
                     "next": "ui_design_cli.py start --title <screen name>"})
    clicked = _find_clicked_event(session, args.choice)
    screen = args.screen or (clicked or {}).get("screen") or _newest_screen(session)
    tokens_file = session.screens_dir / SESSION_TOKENS_FILE_NAME
    decision = {"title": session.title, "issue": args.issue or session.issue, "chosen": args.choice,
                "chosen_name": (clicked or {}).get("text"), "reason": args.reason, "screen": screen,
                "captures": _list_captures(session, screen), "tokens": str(tokens_file) if tokens_file.is_file() else None,
                "comment_url": args.comment_url, "run_dir": session.run_dir}
    write_json_atomically(Path(session.run_dir) / DECISION_FILE_NAME, decision)
    return emit({"decision": decision, "summary": f"Recorded: {args.choice}",
                 "next": ("Implement the chosen option from this mockup. Add one line under ## Decisions in the project notes. "
                          "pro-agent-test and pro-report read this with decision.")})


def find_latest_decision(root: Path) -> tuple[dict | None, bool]:
    """(decision, is from current session). Current session first, else the latest decision in this project"""
    current = find_current_session(root)
    files = [Path(session.run_dir) / DECISION_FILE_NAME for session in list_project_sessions(root)]
    files = sorted((path for path in files if path.is_file()), key=lambda path: path.stat().st_mtime, reverse=True)
    if current:
        current_file = Path(current.run_dir) / DECISION_FILE_NAME
        files.sort(key=lambda path: path != current_file)
    for path in files:
        try:
            return json.loads(path.read_text(encoding="utf-8")), bool(current) and path.parent == Path(current.run_dir)
        except (OSError, ValueError):
            continue
    return None, False


def cmd_decision(args) -> int:
    decision, is_current_session = find_latest_decision(Path(args.root).resolve())
    return emit({"decision": decision, "is_current_session": is_current_session,
                 "summary": f"Chosen: {decision['chosen']}" if decision else "No decision recorded"})
