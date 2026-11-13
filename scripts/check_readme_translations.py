#!/usr/bin/env python3
"""README 번역본 어긋남 점검: 번역본이 따라간 원본 커밋 이후 README.md 변경 목록

번역본 맨 위 표식 `<!-- translated-from: README.md@<커밋> -->` > 그 커밋..HEAD 의 README.md 커밋 > 남은 것 보고
경고만 낸다 (번역은 사람이 맞춤). `--strict` 일 때만 실패 종료
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
# 번역본 표식: <!-- translated-from: README.md@<커밋> -->
MARKER_PATTERN = re.compile(r"<!--\s*translated-from:\s*README\.md@([0-9a-f]{7,40})\s*-->")
# 표식은 파일 앞부분에만 둔다 (본문 예시와 섞이지 않게)
MARKER_SEARCH_LINES = 10
# 릴리스 봇의 README 버전 줄 갱신 — 번역할 내용이 아님
IGNORED_SUBJECT_MARK = "[skip ci]"


def run_git(repo_root: Path, *arguments: str) -> tuple[int, str]:
    """git 실행 > (종료 코드, 출력). 한글 출력에서도 깨지지 않게 utf-8 + replace"""
    completed = subprocess.run(["git", *arguments], cwd=repo_root, capture_output=True,
                               encoding="utf-8", errors="replace")
    return completed.returncode, (completed.stdout or "").strip()


def read_marker_commit(translation_file: Path) -> str | None:
    """번역본 앞부분의 원본 커밋 표식. 없으면 None"""
    head_lines = translation_file.read_text(encoding="utf-8").splitlines()[:MARKER_SEARCH_LINES]
    for line in head_lines:
        match = MARKER_PATTERN.search(line)
        if match:
            return match.group(1)
    return None


def list_untranslated_commits(repo_root: Path, marker_commit: str) -> tuple[list[str] | None, str | None]:
    """표식 커밋 이후 README.md 를 바꾼 커밋 (봇 버전 갱신 제외) > (목록, 오류)"""
    code, _ = run_git(repo_root, "cat-file", "-e", f"{marker_commit}^{{commit}}")
    if code != 0:
        return None, f"commit {marker_commit} not found (shallow clone or wrong hash)"
    code, output = run_git(repo_root, "log", "--format=%h %s", f"{marker_commit}..HEAD", "--", SOURCE_README)
    if code != 0:
        return None, "git log failed"
    return [line for line in output.splitlines() if line and IGNORED_SUBJECT_MARK not in line], None


def check_translation(repo_root: Path, translation_file: Path) -> dict:
    """번역본 1개 판정: ok · behind · no_marker · unknown"""
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
    """GitHub Actions 경고 주석 (실패 아님)"""
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
