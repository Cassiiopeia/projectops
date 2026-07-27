import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _skill_doc_paths():
    return [
        *sorted((ROOT / "skills").glob("*/SKILL.md")),
        *sorted((ROOT / "skills" / "references").glob("*.md")),
    ]


def test_skill_docs_do_not_teach_inline_python_workarounds():
    """Skill docs must route behavior through stable scripts, not heredoc Python."""
    forbidden = {
        "python_heredoc": re.compile(r"(?:python3?|\\\$PYTHON|PYTHONIOENCODING=[^\n]*)\s+-\s+<<|<<'EOF'|<<EOF"),
        "tmp_python": re.compile(r"/tmp/[^`\s]*\.py"),
        "curl_pipe_python": re.compile(r"curl[^\n|]*\|[^\n]*(?:python3?|\\\$PYTHON)"),
        "old_suh_command": re.compile(r"-m suh_template\.suh_command|scripts/suh_template/suh_command\.py"),
    }
    allowed_files = {
        "skills/references/mcp-subcommand-rules.md",
    }
    failures = []
    for path in _skill_doc_paths():
        rel = path.relative_to(ROOT).as_posix()
        if rel in allowed_files:
            continue
        text = path.read_text(encoding="utf-8")
        for name, pattern in forbidden.items():
            if pattern.search(text):
                failures.append(f"{rel}: {name}")
    assert failures == []


def test_github_skill_docs_use_suh_command_instead_of_direct_curl_recipes():
    """GitHub-facing skills should not document direct curl API recipes."""
    github_docs = [
        ROOT / "skills" / "pro-github" / "SKILL.md",
        ROOT / "skills" / "references" / "issue-creation.md",
        ROOT / "skills" / "pro-changelog-deploy" / "SKILL.md",
    ]
    failures = []
    for path in github_docs:
        rel = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        if re.search(r"curl\s+-s[^\n]*api\.github\.com|https://api\.github\.com", text):
            failures.append(rel)
    assert failures == []


def test_common_rules_documents_3layer_architecture():
    """common-rules.md에 3-layer 아키텍처와 7개 skill cli 매핑이 명시되어야 한다."""
    text = (ROOT / "skills" / "references" / "common-rules.md").read_text(encoding="utf-8")
    # issue_cli.py는 pro-issue 통합(#464)으로 삭제됨 — github_cli가 흡수.
    for cli in ["github_cli.py", "commit_cli.py", "report_cli.py",
                "review_cli.py", "note_cli.py", "changelog_cli.py"]:
        assert cli in text, f"{cli} 매핑이 common-rules.md에 없음"
    # 3-layer 핵심 키워드
    for keyword in ["scripts/common/", "skills/<skill>/scripts/", "self-contained 5줄"]:
        assert keyword in text, f"\"{keyword}\" 키워드 누락"


def test_agent_docs_do_not_recommend_direct_curl_for_github_api():
    docs = [ROOT / "CLAUDE.md", ROOT / "AGENTS.md"]
    failures = []
    for path in docs:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        if "GitHub API 호출은 curl 직접 사용 권장" in text:
            failures.append(path.name)
    assert failures == []


def test_commit_cli_bad_args_emits_json():
    """commit_cli.py가 잘못된 인자를 받아도 stdout에 JSON을 emit해야 한다."""
    import subprocess
    import os
    import json
    cli_path = ROOT / "skills" / "pro-commit" / "scripts" / "commit_cli.py"
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.run(
        [sys.executable, str(cli_path), "nonexistent-sub"],
        capture_output=True, text=True, encoding="utf-8",
        env=env,
    )
    assert proc.stdout.strip(), f"stdout empty, stderr={proc.stderr}"
    out = json.loads(proc.stdout.strip().splitlines()[-1])
    assert out["ok"] is False
    assert out["code"] == "bad_args"


def test_report_cli_bad_args_emits_json():
    """report_cli.py가 잘못된 인자를 받아도 stdout에 JSON을 emit해야 한다."""
    import subprocess
    import os
    import json
    cli_path = ROOT / "skills" / "pro-report" / "scripts" / "report_cli.py"
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.run(
        [sys.executable, str(cli_path), "nonexistent-sub"],
        capture_output=True, text=True, encoding="utf-8",
        env=env,
    )
    assert proc.stdout.strip(), f"stdout empty, stderr={proc.stderr}"
    out = json.loads(proc.stdout.strip().splitlines()[-1])
    assert out["ok"] is False
    assert out["code"] == "bad_args"


def test_review_cli_bad_args_emits_json():
    """review_cli.py가 잘못된 인자를 받아도 stdout에 JSON을 emit해야 한다."""
    import subprocess
    import os
    import json
    cli_path = ROOT / "skills" / "pro-review" / "scripts" / "review_cli.py"
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.run(
        [sys.executable, str(cli_path), "nonexistent-sub"],
        capture_output=True, text=True, encoding="utf-8",
        env=env,
    )
    assert proc.stdout.strip(), f"stdout empty, stderr={proc.stderr}"
    out = json.loads(proc.stdout.strip().splitlines()[-1])
    assert out["ok"] is False
    assert out["code"] == "bad_args"


def test_note_cli_bad_args_emits_json():
    """troubleshoot_cli.py가 잘못된 인자를 받아도 stdout에 JSON을 emit해야 한다."""
    import subprocess
    import os
    import json
    cli_path = ROOT / "skills" / "pro-note" / "scripts" / "note_cli.py"
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.run(
        [sys.executable, str(cli_path), "nonexistent-sub"],
        capture_output=True, text=True, encoding="utf-8",
        env=env,
    )
    assert proc.stdout.strip(), f"stdout empty, stderr={proc.stderr}"
    out = json.loads(proc.stdout.strip().splitlines()[-1])
    assert out["ok"] is False
    assert out["code"] == "bad_args"


def test_github_cli_bad_args_emits_json():
    """github_cli.py가 잘못된 인자를 받아도 stdout에 JSON을 emit해야 한다."""
    import subprocess
    import os
    import json
    cli_path = ROOT / "skills" / "pro-github" / "scripts" / "github_cli.py"
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.run(
        [sys.executable, str(cli_path), "nonexistent-sub"],
        capture_output=True, text=True, encoding="utf-8",
        env=env,
    )
    assert proc.stdout.strip(), f"stdout empty, stderr={proc.stderr}"
    out = json.loads(proc.stdout.strip().splitlines()[-1])
    assert out["ok"] is False
    assert out["code"] == "bad_args"


def test_changelog_cli_bad_args_emits_json():
    """changelog_cli.py가 잘못된 인자를 받아도 stdout에 JSON을 emit해야 한다."""
    import subprocess
    import os
    import json
    cli_path = ROOT / "skills" / "pro-changelog-deploy" / "scripts" / "changelog_cli.py"
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.run(
        [sys.executable, str(cli_path), "nonexistent-sub"],
        capture_output=True, text=True, encoding="utf-8",
        env=env,
    )
    assert proc.stdout.strip(), f"stdout empty, stderr={proc.stderr}"
    out = json.loads(proc.stdout.strip().splitlines()[-1])
    assert out["ok"] is False
    assert out["code"] == "bad_args"


def test_mcp_rules_document_json_argparse_standard():
    """mcp-subcommand-rules.md에 JSONArgumentParser 사용 규칙이 명시되어야 한다 (이슈 #329)."""
    path = ROOT / "skills" / "references" / "mcp-subcommand-rules.md"
    text = path.read_text(encoding="utf-8")
    assert "JSONArgumentParser" in text
    assert "bad_args" in text
    assert "available_subcommands" in text


def test_plan_skill_does_not_reference_removed_get_next_seq_subcommand():
    """plan/SKILL.md는 issue_cli의 get-next-seq를 참조하면 안 된다 (이슈 #329)."""
    path = ROOT / "skills" / "pro-plan" / "SKILL.md"
    text = path.read_text(encoding="utf-8")
    assert "issue_cli.py 가 `get-next-seq`" not in text
    assert "`get-next-seq`·`normalize-title` 보유" not in text
