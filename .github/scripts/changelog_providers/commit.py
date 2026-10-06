#!/usr/bin/env python3
"""commit provider — 커밋 분석으로 pr_body.md 생성 (안전망, AI 무의존) (#455).

입력: COMMIT_RANGE (기본 origin/main..HEAD)
출력: pr_body.md + stdout `PROVIDER=commit` + exit 0 (항상 완주하는 최후 보루)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import collect_commits, classify, empty_notes, sections_to_markdown, write_pr_body  # noqa: E402


def main():
    range_expr = os.environ.get("COMMIT_RANGE", "origin/main..HEAD")
    commits = collect_commits(range_expr)
    content = sections_to_markdown(classify(commits)) if commits else empty_notes()
    write_pr_body(content)
    print("PROVIDER=commit")


if __name__ == "__main__":
    main()
