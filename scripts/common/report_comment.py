"""pro-report 보고서 댓글 표식: 붙이기(pro-report add-comment) · 찾기(pro-github finish-issue) 공통 (#969)"""
from __future__ import annotations

# 보고서 댓글 첫 줄 표식 (렌더링되지 않는 HTML 주석)
REPORT_COMMENT_MARKER = "<!-- projectops:report -->"


def with_report_marker(body: str) -> str:
    """본문 앞에 표식 1회 (이미 있으면 그대로)"""
    return body if REPORT_COMMENT_MARKER in body else f"{REPORT_COMMENT_MARKER}\n{body}"
