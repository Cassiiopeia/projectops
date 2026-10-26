#!/usr/bin/env python3
"""bug_cli: pro-skill-bug 사실 수집 CLI — 판정 없음, 출력은 항상 JSON (ok·code·summary·next)

extras 플러그인은 자기 폴더만 설치되므로 scripts/common 을 쓰지 않는다 (표준 라이브러리 전용).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bug import alarm, context, excerpt, redact, transcript  # noqa: E402

# 이슈 본문 초안 폴더: ~/.projectops/cache/pro-skill-bug/{세션 ID 앞 8자}_{yyyyMMdd-HHmmss}.md
DRAFT_FOLDER_PARTS = (".projectops", "cache", "pro-skill-bug")


class _BadArgumentsExit(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


class JsonArgumentParser(argparse.ArgumentParser):
    """인자 오류를 stderr 대신 JSON 으로 돌려주기 위한 파서"""

    def error(self, message):
        raise _BadArgumentsExit(message)


def emit(payload: dict) -> int:
    payload.setdefault("ok", True)
    payload.setdefault("code", "ok" if payload["ok"] else "error")
    payload.setdefault("summary", None)
    payload.setdefault("next", None)
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()
    return 0 if payload["ok"] else 1


def _transcript_or_failure(session_id: str | None) -> tuple[Path | None, dict | None]:
    path = transcript.find_transcript(session_id)
    if path:
        return path, None
    searched = [str(base / "projects") for base in transcript.config_dirs()]
    return None, {"ok": False, "code": "transcript_not_found", "searched": searched,
                  "summary": "Could not find this session's transcript",
                  "next": "locate --session-id <id>  # the id is the .jsonl file name under projects/"}


# 서브커맨드: 기록 찾기 > 결과 + next

def cmd_locate(args) -> dict:
    path, failure = _transcript_or_failure(args.session_id)
    if failure:
        return failure
    return {"path": str(path), "session_id": path.stem, "size_bytes": path.stat().st_size,
            "summary": f"Transcript found ({path.stat().st_size} bytes)",
            "next": f"excerpt --session-id {path.stem}"}


def cmd_excerpt(args) -> dict:
    path, failure = _transcript_or_failure(args.session_id)
    if failure:
        return failure
    result = excerpt.build_excerpt(list(transcript.iter_events(path)), args.last, args.max_chars, args.around,
                                   args.tool_use_id, args.window)
    if not result["steps"]:
        summary = "No projectops commands in this transcript"
    else:
        summary = (f"{len(result['steps'])} of {result['total_projectops_calls']} projectops calls, "
                   f"{len(result['user_messages'])} user messages, {len(result['images'])} images")
    return {"path": str(path), "session_id": path.stem, **result, "summary": summary,
            "next": "draft-path  # then write the issue body; raise --last if the start of the story is missing"}


def cmd_alarm(args) -> dict:
    session_id = args.session_id or os.environ.get(transcript.SESSION_ID_ENV) or ""
    alarms = alarm.load_alarms(session_id) if session_id else None
    if not alarms:
        return {"ok": False, "code": "alarm_not_found", "session_id": session_id or None,
                "summary": "No alarm saved for this session (none fired yet, or the state file expired after 7 days)",
                "next": f"excerpt --session-id {session_id or '<id>'} --around <a word from the failed command>"}
    number = args.alarm or len(alarms)
    if not 1 <= number <= len(alarms):
        return {"ok": False, "code": "bad_args", "error": f"--alarm must be 1..{len(alarms)}", "next": "alarm"}
    picked, counts = alarm.redact_alarm(alarms[number - 1])
    anchor_hint = f" --tool-use-id {picked['tool_use_id']}" if picked.get("tool_use_id") else ""
    return {"alarm": picked, "alarm_number": number, "alarms_count": len(alarms), "redactions": counts,
            "summary": f"Alarm {number} of {len(alarms)}: {picked.get('rule')} on {picked.get('skill')} {picked.get('subcommand')}",
            "next": f"excerpt --session-id {session_id}{anchor_hint}  # then context"}


def cmd_context(args) -> dict:
    command, cwd = args.command, None
    if args.session_id:
        alarms = alarm.load_alarms(args.session_id) or []
        anchor_command, cwd = _anchor_command_and_cwd(args.session_id, alarms[-1].get("tool_use_id") if alarms else None)
        command = command or anchor_command
    facts = context.collect_context(command, Path(cwd) if cwd else None)
    return {"context": facts, "summary": "Environment facts for the issue body",
            "next": "draft-path  # write the body with the fixed template"}


def _anchor_command_and_cwd(session_id: str, tool_use_id: str | None) -> tuple[str | None, str | None]:
    """기록에서 기준 호출의 (명령 글, 그때 작업 폴더). 기준이 없으면 마지막 줄의 작업 폴더"""
    path = transcript.find_transcript(session_id)
    if not path:
        return None, None
    command, cwd = None, None
    for row in transcript.iter_rows(path):
        cwd = row.get("cwd") or cwd
        for block in (row.get("message") or {}).get("content") or []:
            if isinstance(block, dict) and block.get("type") == "tool_use" and tool_use_id and block.get("id") == tool_use_id:
                return str((block.get("input") or {}).get("command") or ""), cwd
    return command, cwd


def cmd_draft_path(args) -> dict:
    session_prefix = (os.environ.get(transcript.SESSION_ID_ENV) or "nosession")[:8]
    folder = Path.home().joinpath(*DRAFT_FOLDER_PARTS)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{session_prefix}_{time.strftime('%Y%m%d-%H%M%S')}.md"
    return {"path": str(path), "summary": "Draft path for the issue body",
            "next": f"write the body there, then redact --file {path} --in-place"}


def cmd_redact(args) -> dict:
    path = Path(args.file).expanduser()
    if not path.is_file():
        return {"ok": False, "code": "file_not_found", "error": f"No such file: {path}", "next": "draft-path"}
    redacted, counts = redact.redact_text(path.read_text(encoding="utf-8"))
    payload = {"file": str(path), "redactions": counts,
               "summary": f"Masked {sum(counts.values())} value(s)" if counts else "Nothing matched the mechanical rules",
               "next": "Read the whole body yourself for names, addresses, birth dates, accounts or certificate contents, then search-issues"}
    if args.in_place:
        path.write_text(redacted, encoding="utf-8")
    else:
        payload["text"] = redacted
    return payload


def build_parser() -> JsonArgumentParser:
    parser = JsonArgumentParser(prog="bug_cli.py", description="Collect facts about a suspected projectops skill bug")
    commands = parser.add_subparsers(dest="command", parser_class=JsonArgumentParser, required=True)
    locate = commands.add_parser("locate", help="find this session's transcript")
    locate.add_argument("--session-id", dest="session_id", default=None)
    locate.set_defaults(run=cmd_locate)
    excerpt_parser = commands.add_parser("excerpt", help="projectops commands, results, user messages and images (redacted)")
    excerpt_parser.add_argument("--session-id", dest="session_id", default=None)
    excerpt_parser.add_argument("--last", type=int, default=40, help="how many recent projectops calls (default 40)")
    excerpt_parser.add_argument("--max-chars", dest="max_chars", type=int, default=4000, help="per command/result (default 4000)")
    excerpt_parser.add_argument("--around", default=None, help="center on the first call whose command or result contains this text")
    excerpt_parser.add_argument("--tool-use-id", dest="tool_use_id", default=None,
                                help="anchor call from an alarm: adds its full result, every call around it, agent notes, setup commands")
    excerpt_parser.add_argument("--window", type=int, default=8, help="calls before and after the anchor (default 8)")
    excerpt_parser.set_defaults(run=cmd_excerpt)
    alarm_parser = commands.add_parser("alarm", help="evidence the watch hook saved for an automatic report")
    alarm_parser.add_argument("--session-id", dest="session_id", default=None)
    alarm_parser.add_argument("--alarm", type=int, default=None, help="alarm number (default: the latest)")
    alarm_parser.set_defaults(run=cmd_alarm)
    context_parser = commands.add_parser("context", help="environment facts: OS, Python, folder, git, CLI path and versions")
    context_parser.add_argument("--session-id", dest="session_id", default=None)
    context_parser.add_argument("--command", default=None, help="the failed command (to find the CLI path and its version)")
    context_parser.set_defaults(run=cmd_context)
    draft = commands.add_parser("draft-path", help="path to write the issue body draft")
    draft.set_defaults(run=cmd_draft_path)
    redact_parser = commands.add_parser("redact", help="mask secrets and personal identifiers in a file")
    redact_parser.add_argument("--file", required=True)
    redact_parser.add_argument("--in-place", dest="in_place", action="store_true")
    redact_parser.set_defaults(run=cmd_redact)
    return parser


def main(argv=None) -> int:
    try:
        args = build_parser().parse_args(argv)
    except _BadArgumentsExit as error:
        return emit({"ok": False, "code": "bad_args", "error": error.message, "next": "bug_cli.py --help"})
    return emit(args.run(args))


if __name__ == "__main__":
    sys.exit(main())
