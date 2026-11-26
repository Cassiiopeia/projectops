"""Shared subcommand responses and input cleanup: missing PAT, GitHub API errors, csv arguments."""
from __future__ import annotations

from common.emit import emit


def missing_pat() -> int:
    return emit({"ok": False, "code": "missing_pat", "error": "no PAT configured"})


def api_error(error) -> int:
    """GitHubAPIError > {"code": "github_api_<status code>"}"""
    return emit({"ok": False, "code": f"github_api_{error.status_code}", "error": str(error)})


def add_body_file_arguments(parser) -> None:
    """Body file as a positional or as --body-file: both are natural guesses, so both work (#1242)"""
    parser.add_argument("body_file", nargs="?")
    parser.add_argument("--body-file", dest="body_file_option", default=None, metavar="PATH",
                        help="body file path (same as the body_file positional)")


def merge_body_file_argument(args, usage: str, is_required: bool = True) -> int | None:
    """--body-file wins over the positional > args.body_file. Response code when required and missing, otherwise None"""
    args.body_file = args.body_file_option or args.body_file
    if is_required and not args.body_file:
        return emit({"ok": False, "code": "missing_argument", "error": "a body file is required", "usage": usage})
    return None


def split_csv(text: str) -> list[str]:
    """"a, b,,c" > ["a", "b", "c"] (whitespace trimmed, empty items dropped)"""
    return [item.strip() for item in text.split(",") if item.strip()]
