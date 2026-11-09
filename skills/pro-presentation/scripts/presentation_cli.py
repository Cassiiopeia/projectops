#!/usr/bin/env python3
"""presentation_cli — pro-presentation 전용 CLI (projectops 3-layer 표준, Layer 2, #1097).

HTML 덱 폴더를 원본으로 연습 화면을 띄우고, 녹화를 받아쓰고, 검사하고, PDF·PPT 로 내보낸다.
**판단은 agent** — 코칭, 장별 녹화 구간, 슬라이드 내용은 agent 가 덱 파일을 직접 고친다. 여기는 실행과 사실만.

서브커맨드:
    start · status · stop        덱 만들기(템플릿·첫 실행 질문) + 연습 서버
    import                       기존 PPT·PDF > 장 그림 + 원본 글
    recording add                녹화 파일 · 영상 주소 · 자막 파일 > transcript.txt
    check                        빠진 파일 · 용어 위반 · 예상 시간 · 녹화 차수별 장 시간 · 그림으로 갈 부분
    export                       PDF · 글자 PPT + 검수
    config show|set|options      presentation 설정 (config.json)
    get-output-path              덱을 둘 기본 자리

출력: MCP-style JSON (ok/code/summary/next 4필드 보장).
"""
from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))

import pro_presentation  # noqa: E402,F401  (common import 경로를 맞춘다)
from common.cli_parser import JSONArgumentParser, run_cli  # noqa: E402


def _run(module_name: str, function_name: str):
    """서브커맨드 모듈은 부를 때만 import (선택 의존성이 다른 명령을 막지 않게)"""
    def runner(args):
        module = __import__(f"pro_presentation.{module_name}", fromlist=[function_name])
        return getattr(module, function_name)(args)
    return runner


def build_parser() -> JSONArgumentParser:
    parser = JSONArgumentParser(prog="presentation_cli.py", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("start", help="Create a deck from the template (or open one) and run its practice server")
    p.add_argument("--deck", default=None,
                   help="Deck folder (created from the template if it has no deck.json; default: deck_root or get-output-path)")
    p.add_argument("--title", default=None, help="Talk title for a new deck")
    p.add_argument("--open", action="store_true", help="Open the page in the default browser")
    p.add_argument("--root", default=".")
    p.set_defaults(func=_run("session", "cmd_start"))

    for name, help_text, function in (("status", "Server state and url of a deck", "cmd_status"),
                                      ("stop", "Stop a deck's server; files are kept", "cmd_stop")):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--deck", default=None, help="Deck folder (default: the last one opened in this project)")
        p.add_argument("--root", default=".")
        p.set_defaults(func=_run("session", function))

    p = sub.add_parser("import", help="Existing PPT or PDF > one picture per slide + its text as a note")
    p.add_argument("--deck", required=True)
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument("--pptx", default=None)
    source.add_argument("--pdf", default=None)
    p.set_defaults(func=_run("importer", "cmd_import"))

    p = sub.add_parser("recording", help="Recorded takes")
    recording_sub = p.add_subparsers(dest="recording_command", required=True)
    p = recording_sub.add_parser("add", help="A take > recordings/<label>/transcript.txt (local file, video link, or captions)")
    p.add_argument("--deck", required=True)
    take = p.add_mutually_exclusive_group()
    take.add_argument("--file", default=None, help="Audio or video recorded locally (mp4, m4a, mp3, wav, mov, webm)")
    take.add_argument("--url", default=None, help="Video link (captions first, else transcribed)")
    take.add_argument("--transcript", default=None, help="Existing captions or transcript (srt, vtt, txt)")
    p.add_argument("--label", default=None,
                   help="Folder name, e.g. take-2 (default: take-<n>-<date>). Alone: transcribe that take recorded on the practice page")
    p.add_argument("--language", default=None, help="Caption language (default: deck.json language)")
    p.set_defaults(func=_run("recording", "cmd_recording_add"))

    p = sub.add_parser("check", help="Missing files, glossary hits, timing against the limit, per-take timing, picture parts")
    p.add_argument("--deck", required=True)
    p.set_defaults(func=_run("check", "cmd_check"))

    p = sub.add_parser("export", help="PDF and/or editable-text PPT, then verify the PPT against the HTML")
    p.add_argument("--deck", required=True)
    p.add_argument("--pdf", action="store_true")
    p.add_argument("--pptx", action="store_true")
    p.add_argument("--timeout", type=int, default=300, help="Seconds for the browser step")
    p.set_defaults(func=_run("export", "cmd_export"))

    p = sub.add_parser("config", help="Settings in the presentation section of config.json")
    config_sub = p.add_subparsers(dest="config_command", required=True)
    for name, help_text in (("show", "Resolved settings with the source of each value"), ("options", "Every option")):
        q = config_sub.add_parser(name, help=help_text)
        q.add_argument("--root", default=".")
        q.set_defaults(func=_run("config", "cmd_config"))
    q = config_sub.add_parser("set", help="Save one option (section default, or --project for one repo)")
    q.add_argument("name")
    q.add_argument("value")
    q.add_argument("--project", default=None, help="owner/repo or absolute repo path")
    q.add_argument("--root", default=".")
    q.set_defaults(func=_run("config", "cmd_config"))

    p = sub.add_parser("get-output-path", help="Default place for a new deck in this project")
    p.add_argument("--root", default=None)
    p.add_argument("--title", default=None)
    p.set_defaults(func=_run("output_path", "cmd_output_path"))
    return parser


def main(argv: list[str] | None = None) -> int:
    return run_cli(build_parser(), argv)


if __name__ == "__main__":
    sys.exit(main())
