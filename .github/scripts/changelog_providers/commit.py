#!/usr/bin/env python3
"""commit provider — builds pr_body.md from commit analysis (safety net, no AI) (#455).

Input: COMMIT_RANGE (default origin/<PR base>..HEAD, _common.release_commit_range)
Output: pr_body.md + stdout `PROVIDER=commit` + exit 0 (the last resort that always finishes)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import collect_commits, classify, release_commit_range, empty_notes, sections_to_markdown, write_pr_body  # noqa: E402


def main():
    commits = collect_commits(release_commit_range())
    content = sections_to_markdown(classify(commits)) if commits else empty_notes()
    write_pr_body(content)
    print("PROVIDER=commit")


if __name__ == "__main__":
    main()
