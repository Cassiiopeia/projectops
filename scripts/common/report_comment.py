"""pro-report report comment marker: shared by adding (pro-report add-comment) and finding (pro-github finish-issue) (#969)"""
from __future__ import annotations

# First-line marker of a report comment (HTML comment, not rendered)
REPORT_COMMENT_MARKER = "<!-- projectops:report -->"


def with_report_marker(body: str) -> str:
    """Prefix the marker once (unchanged if already present)"""
    return body if REPORT_COMMENT_MARKER in body else f"{REPORT_COMMENT_MARKER}\n{body}"
