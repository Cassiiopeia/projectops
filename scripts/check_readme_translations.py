#!/usr/bin/env python3
"""README translation drift: README.md commits since the commit each translation follows (#1140)
Marker `<!-- translated-from: README.md@<commit> -->` > commit..HEAD > report (warning only; --strict exits 1)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

SOURCE_README = "README.md"
TRANSLATION_GLOB = "docs/i18n/README.*.md"
# Translation marker: <!-- translated-from: README.md@<commit> -->
MARKER_PATTERN = re.compile(r"<!--\s*translated-from:\s*README\.md@([0-9a-f]{7,40})\s*-->")
# The marker lives only near the top of the file (so it is not confused with examples in the body)
MARKER_SEARCH_LINES = 10
# Release bot's README version-line update — nothing to translate
IGNORED_SUBJECT_MARK = "[skip ci]"
# Automatic version line (absent from translations — a commit changing only this line needs no translation)
VERSION_LINE_PATTERN = re.compile(r"^[+-]## Latest version :")


def run_git(repo_root: Path, *arguments: str) -> tuple[int, str]:
    """Run git > (exit code, output). utf-8 + replace so Korean output does not break"""
    completed = subprocess.run(["git", *arguments], cwd=repo_root, capture_output=True,
                               encoding="utf-8", errors="replace")
    return completed.returncode, (completed.stdout or "").strip()


def read_marker_commit(translation_file: Path) -> str | None:
    """Source commit marker near the top of a translation. None if absent"""
    head_lines = translation_file.read_text(encoding="utf-8").splitlines()[:MARKER_SEARCH_LINES]
    for line in head_lines:
        match = MARKER_PATTERN.search(line)
        if match:
            return match.group(1)
    return None


def list_untranslated_commits(repo_root: Path, marker_commit: str) -> tuple[list[str] | None, str | None]:
    """Commits that changed README.md after the marker commit (excluding bot version updates) > (list, error)"""
    code, _ = run_git(repo_root, "cat-file", "-e", f"{marker_commit}^{{commit}}")
    if code != 0:
        return None, f"commit {marker_commit} not found (shallow clone or wrong hash)"
    code, output = run_git(repo_root, "log", "--no-merges", "--format=%h %s", f"{marker_commit}..HEAD", "--", SOURCE_README)
    if code != 0:
        return None, "git log failed"
    commits = [line for line in output.splitlines() if line and IGNORED_SUBJECT_MARK not in line]
    return [line for line in commits if not is_version_line_only(repo_root, line.split(" ", 1)[0])], None


def is_version_line_only(repo_root: Path, commit: str) -> bool:
    """Is this commit's README.md change only the automatic version line (e.g. pulled in when squashing a main-based PR into develop)"""
    code, output = run_git(repo_root, "show", "--format=", "-U0", commit, "--", SOURCE_README)
    if code != 0:
        return False
    changed = [line for line in output.splitlines()
               if line[:1] in "+-" and not line.startswith(("+++", "---"))]
    return bool(changed) and all(VERSION_LINE_PATTERN.match(line) for line in changed)


def check_translation(repo_root: Path, translation_file: Path) -> dict:
    """Judge one translation: ok · behind · no_marker · unknown"""
    relative_path = translation_file.relative_to(repo_root).as_posix()
    marker_commit = read_marker_commit(translation_file)
    if not marker_commit:
        return {"file": relative_path, "status": "no_marker"}
    commits, error = list_untranslated_commits(repo_root, marker_commit)
    if error:
        return {"file": relative_path, "status": "unknown", "translated_from": marker_commit, "error": error}
    status = "behind" if commits else "ok"
    return {"file": relative_path, "status": status, "translated_from": marker_commit, "untranslated_commits": commits}


def print_actions_warnings(results: list[dict]) -> None:
    """GitHub Actions warning annotation (not a failure)"""
    for result in results:
        if result["status"] == "ok":
            continue
        detail = {"no_marker": "has no translated-from marker",
                  "unknown": result.get("error", ""),
                  "behind": f"is {len(result.get('untranslated_commits', []))} README.md commit(s) behind"}[result["status"]]
        print(f"::warning file={result['file']},title=README translation::{result['file']} {detail}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Report README.md changes not yet carried into the translations")
    parser.add_argument("--root", default=".", help="repository root")
    parser.add_argument("--strict", action="store_true", help="exit 1 when a translation is behind or unmarked")
    args = parser.parse_args()
    repo_root = Path(args.root).resolve()
    results = [check_translation(repo_root, path) for path in sorted(repo_root.glob(TRANSLATION_GLOB))]
    behind_count = sum(1 for result in results if result["status"] != "ok")
    summary = (f"{behind_count} of {len(results)} translation(s) need attention" if behind_count
               else f"all {len(results)} translation(s) follow README.md")
    print(json.dumps({"ok": True, "code": "behind" if behind_count else "ok", "summary": summary,
                      "next": "carry the listed README.md commits into each translation, then move its marker to the newest one"
                      if behind_count else None, "translations": results}, ensure_ascii=False))
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print_actions_warnings(results)
    return 1 if args.strict and behind_count else 0


if __name__ == "__main__":
    sys.exit(main())
