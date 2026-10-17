"""서브커맨드 공통 응답·입력 정리: PAT 없음, GitHub API 오류, csv 인자."""
from __future__ import annotations

from common.emit import emit


def missing_pat() -> int:
    return emit({"ok": False, "code": "missing_pat", "error": "PAT 없음"})


def api_error(error) -> int:
    """GitHubAPIError > {"code": "github_api_<상태코드>"}"""
    return emit({"ok": False, "code": f"github_api_{error.status_code}", "error": str(error)})


def split_csv(text: str) -> list[str]:
    """"a, b,,c" > ["a", "b", "c"] (공백 제거, 빈 항목 제외)"""
    return [item.strip() for item in text.split(",") if item.strip()]
