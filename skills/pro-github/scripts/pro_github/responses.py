"""Shared subcommand responses and input cleanup: missing PAT, GitHub API errors, csv arguments."""
from __future__ import annotations

from common.emit import emit


def missing_pat() -> int:
    return emit({"ok": False, "code": "missing_pat", "error": "no PAT configured"})


def api_error(error) -> int:
    """GitHubAPIError > {"code": "github_api_<status code>"}"""
    return emit({"ok": False, "code": f"github_api_{error.status_code}", "error": str(error)})


def split_csv(text: str) -> list[str]:
    """"a, b,,c" > ["a", "b", "c"] (whitespace trimmed, empty items dropped)"""
    return [item.strip() for item in text.split(",") if item.strip()]
