# scripts/tests/test_cli_signatures_doc_sync.py
"""각 _cli.py 서브커맨드가 SKILL.md에 호출 예시로 등장하는지 점검 (이슈 #329)."""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


CLI_TO_SKILL = {
    "pro-commit/scripts/commit_cli.py": ["pro-commit/SKILL.md"],
    "pro-report/scripts/report_cli.py": ["pro-report/SKILL.md"],
    "pro-review/scripts/review_cli.py": ["pro-review/SKILL.md"],
    "pro-note/scripts/note_cli.py": ["pro-note/SKILL.md"],
    # pro-github는 이슈 생성 워크플로우를 references/issue-creation.md로 분리했으므로 함께 본다.
    "pro-github/scripts/github_cli.py": [
        "pro-github/SKILL.md",
        "references/issue-creation.md",
    ],
    "pro-changelog-deploy/scripts/changelog_cli.py": ["pro-changelog-deploy/SKILL.md"],
}


# 현재 SKILL.md에 호출예가 없는 서브커맨드 — 후속 작업으로 보강 시 셋에서 제거한다.
EXPECTED_MISSING = {
    # TODO #329 후속: SKILL.md에 호출예 추가 후 제거
    ("pro-commit/scripts/commit_cli.py", "get-issue-number"),
    # TODO #329 후속: SKILL.md에 호출예 추가 후 제거
    ("pro-commit/scripts/commit_cli.py", "normalize-title"),
    # TODO #329 후속: SKILL.md에 호출예 추가 후 제거
    ("pro-commit/scripts/commit_cli.py", "get-commit-template"),
    # TODO #329 후속: SKILL.md에 호출예 추가 후 제거
    ("pro-report/scripts/report_cli.py", "get-output-path"),
    # TODO #329 후속: SKILL.md에 호출예 추가 후 제거
    ("pro-changelog-deploy/scripts/changelog_cli.py", "list-prs"),
}


def _extract_subcommands(cli_path: Path) -> list:
    """add_parser("subname", ...) 호출에서 첫 인자(서브커맨드명)를 모두 수집."""
    tree = ast.parse(cli_path.read_text(encoding="utf-8"))
    names = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "add_parser" and node.args:
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                names.append(first.value)
    return names


def test_each_cli_subcommand_is_documented():
    """각 _cli.py 서브커맨드는 해당 SKILL.md에 정확한 이름으로 등장해야 한다."""
    failures = []
    for cli_rel, skill_rels in CLI_TO_SKILL.items():
        cli_path = ROOT / "skills" / cli_rel
        if not cli_path.exists():
            continue
        names = _extract_subcommands(cli_path)
        docs_text = "\n".join(
            (ROOT / "skills" / s).read_text(encoding="utf-8")
            for s in skill_rels if (ROOT / "skills" / s).exists()
        )
        for name in names:
            if (cli_rel, name) in EXPECTED_MISSING:
                continue
            # 정확한 이름 매칭 (코드 백틱 또는 단어 경계)
            if re.search(rf"\b{re.escape(name)}\b", docs_text):
                continue
            failures.append(f"{cli_rel}: {name!r} 호출예가 SKILL.md에 없음")
    if failures:
        failures.append("\nSKILL.md에 호출 예시 추가하거나 EXPECTED_MISSING 셋에 임시 등록 후 #329 후속 이슈로 보강.")
    assert failures == [], "\n".join(failures)
