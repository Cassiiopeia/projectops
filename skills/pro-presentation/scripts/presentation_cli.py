#!/usr/bin/env python3
"""presentation_cli — pro-presentation CLI (projectops 3-layer standard, Layer 2, #1097).

Serves the practice screen from an HTML deck folder, transcribes recordings, checks, and exports to PDF/PPT.
**The agent decides** — coaching, per-slide recording ranges and slide content are edited by the agent in the deck files. This only runs things and reports facts.

Subcommands:
    start · status · stop        create deck (template, first-run questions) + practice server
    import                       existing PPT/PDF > slide images + source text
    recording add                recording file · video URL · subtitle file > transcript.txt
    check                        missing files · term violations · estimated time · per-slide time by recording take · parts better as images
    export                       PDF · text PPT + review
    config show|set|options      presentation settings (config.json)
    get-output-path              default place for the deck

Output: MCP-style JSON (ok/code/summary/next, all 4 fields guaranteed).
"""
from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))

import pro_presentation  # noqa: E402,F401  (sets the common import path)
from common.cli_parser import JSONArgumentParser, run_cli  # noqa: E402


def _run(module_name: str, function_name: str):
    """Import subcommand modules only when called (so an optional dependency does not block other commands)"""
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
    p.add_argument("--converter", choices=("auto", "builtin", "dom-to-pptx"), default=None,
                   help="PPT converter (default: the pptx_converter setting)")
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
