"""Claude Code PostToolUse·PostToolUseFailure(Bash) hook: detect projectops tool anomalies > tell the agent to auto-report (#997·#1000)
Parse input > apply rules (skill_bug_rules) > save session state > additionalContext. Any error always passes silently.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import skill_bug_rules  # noqa: E402

# Session state: ~/.projectops/cache/pro-skill-bug/watch/{session_id}.json
WATCH_FOLDER = Path.home() / ".projectops" / "cache" / "pro-skill-bug" / "watch"
CONFIG_PATH = Path.home() / ".projectops" / "config" / "config.json"
# config.json: "skill-bug": {"auto_report": false} turns it off
CONFIG_SECTION = "skill-bug"
CONFIG_KEY_AUTO_REPORT = "auto_report"
# Without this text and with no pending failure, nothing is read (runs on every Bash call, so it must be fast)
QUICK_TRIGGER = "_cli.py"
SESSION_ID_SAFE_PATTERN = re.compile(r"[^A-Za-z0-9_-]")
# Session state file retention (7 days)
STATE_KEEP_SECONDS = 7 * 24 * 3600
# Number of alarm evidence entries kept in state (read by bug_cli alarm)
STATE_ALARMS_KEPT = 10


def main(stdin_text: str) -> int:
    try:
        payload = json.loads(stdin_text or "{}")
        response = build_response(payload)
    except Exception:   # noqa: BLE001 — a hook error must not block the user's work
        return 0
    if response:
        print(json.dumps(response, ensure_ascii=False))
    return 0


def build_response(payload: dict) -> dict | None:
    """One hook input > additionalContext response or None"""
    if payload.get("tool_name") != "Bash":
        return None
    command = str((payload.get("tool_input") or {}).get("command") or "")
    session_id = SESSION_ID_SAFE_PATTERN.sub("", str(payload.get("session_id") or ""))
    if not session_id:
        return None
    state_path = WATCH_FOLDER / f"{session_id}.json"
    if QUICK_TRIGGER not in command and not state_path.exists():
        return None
    if not is_auto_report_enabled():
        return None
    call = skill_bug_rules.classify_call(command, tool_output_text(payload), payload.get("tool_use_id"))
    if call is None:
        return None
    state = load_state(state_path)
    alarms = skill_bug_rules.evaluate(state, call, command)
    first_alarm_number = len(state.get("alarms") or []) + 1
    if alarms:
        state["alarms"] = ((state.get("alarms") or []) + alarms)[-STATE_ALARMS_KEPT:]
    if call["kind"] == "projectops" or state.get("pending_failure") or alarms:
        save_state(state_path, state)
    if not alarms:
        return None
    return {"hookSpecificOutput": {"hookEventName": payload.get("hook_event_name") or "PostToolUse",
                                   "additionalContext": build_instruction(session_id, alarms, first_alarm_number)}}


def tool_output_text(payload: dict) -> str:
    """Bash result text: tool_response (stdout, stderr) on success, error on failure"""
    if payload.get("error"):
        return str(payload["error"])
    response = payload.get("tool_response")
    if isinstance(response, dict):
        return "\n".join(str(response.get(key) or "") for key in ("stdout", "stderr"))
    return str(response or "")


def is_auto_report_enabled() -> bool:
    try:
        section = json.loads(CONFIG_PATH.read_text(encoding="utf-8")).get(CONFIG_SECTION) or {}
    except (OSError, ValueError):
        return True
    return section.get(CONFIG_KEY_AUTO_REPORT, True) is not False


def load_state(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(path: Path, state: dict) -> None:
    """Save session state (prune old state files on a new session's first save)"""
    if not path.exists():
        prune_old_states(path.parent)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


def prune_old_states(folder: Path) -> None:
    cutoff = time.time() - STATE_KEEP_SECONDS
    for state_file in folder.glob("*.json") if folder.exists() else ():
        if state_file.stat().st_mtime < cutoff:
            state_file.unlink(missing_ok=True)


def build_instruction(session_id: str, alarms: list[dict], first_alarm_number: int) -> str:
    """Fired rules > agent instruction (English, read by the agent; bug_cli alarm reads detailed evidence from state)"""
    lines = ["projectops: a suspected projectops tool bug was detected automatically in this session."]
    for offset, alarm in enumerate(alarms):
        lines.append(f"- alarm {first_alarm_number + offset}: {alarm['rule']} | {alarm['skill']} {alarm['subcommand']}"
                     f" | code {alarm.get('code') or 'none'} | kind {alarm.get('kind') or 'none'}")
    lines += [
        "Do this now, without asking the user and without stopping your current task:",
        "start ONE background subagent (Agent tool, run_in_background) that invokes the projectops-extras:pro-skill-bug skill",
        f"with: automatic report, session id {session_id}, the alarm number(s) above, and one line on what you were doing.",
        f"It starts with `bug_cli.py alarm --session-id {session_id}`, collects the facts, strips personal data,",
        "and files or comments on the issue itself.",
        "Then continue your task. When the subagent finishes, tell the user one line with the issue link.",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main(sys.stdin.read() if not sys.stdin.isatty() else ""))
