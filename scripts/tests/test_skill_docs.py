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


def test_skill_doc_reference_paths_exist():
    """문서가 지시한 참조 경로가 실제로 있는지 전수 확인한다.

    #543: SKILL.md 에서 공용 문서를 `references/x.md` 로 가리키면 자기 스킬 폴더
    안을 뜻하므로 `../references/x.md` 여야 한다. 이 접두사를 틀려 16개 스킬 50곳이
    없는 경로를 가리켰고, 이슈 생성 절차 문서를 못 찾아 중복 검사·승인 게이트를
    건너뛴 사고가 났다.

    common-rules.md 가 이 검사를 heredoc 스니펫으로 적어 뒀지만 손으로 돌려야 해서
    실제로는 아무도 돌리지 않았다. 여기로 옮겨 CI 가 매번 돌린다 (#612).

    디렉터리 접두사가 붙은 것만 본다 — 맨 파일명(`impl.md`)은 임시 파일명이나 표
    항목과 구분되지 않아 오탐이 난다.
    """
    # `../<다른 스킬>/references/x.md` 같은 스킬 간 참조도 본다. 꼬리만 잡으면
    # 앞의 경로가 날아가 자기 폴더로 해석되고, 그러면 깨진 참조를 놓친다.
    pattern = re.compile(r"`((?:\.\./)*(?:[a-z0-9_.-]+/)*references/[a-z0-9_-]+\.md)`")
    broken, checked = [], 0
    for path in _skill_doc_paths():
        for m in pattern.finditer(path.read_text(encoding="utf-8")):
            checked += 1
            target = (path.parent / m.group(1)).resolve()
            if not target.exists():
                broken.append(f"{path.relative_to(ROOT).as_posix()}: {m.group(1)}")

    assert checked > 0, "참조를 하나도 못 찾았다 — 검사가 헛돌고 있다"
    assert broken == [], "존재하지 않는 문서를 가리킨다:\n" + "\n".join(broken)


def test_no_reference_doc_is_orphaned():
    """스킬의 참조 문서는 어디선가 실제로 읽혀야 한다.

    아무도 가리키지 않는 문서는 **쓴 사람만 아는 문서**다. 시간이 지나면 내용이
    낡는데 아무도 모르고, 고쳐야 할 때 있는 줄도 모른다. 실제로 `pro-agent-test` 의
    109줄짜리 문서가 오래 그 상태였고 산출물 규칙이 바뀐 뒤에도 옛 내용으로 남아
    있었다 (#584).

    자기 SKILL.md 나 형제 참조 문서 중 한 곳에서 `references/<파일>` 로 가리키면 된다.
    """
    orphans = []
    for skill in sorted((ROOT / "skills").glob("pro-*")):
        refs = sorted((skill / "references").glob("*.md"))
        if not refs:
            continue
        corpus = ""
        main = skill / "SKILL.md"
        if main.is_file():
            corpus += main.read_text(encoding="utf-8")
        corpus += "".join(r.read_text(encoding="utf-8") for r in refs)
        orphans += [f"{skill.name}/references/{r.name}"
                    for r in refs if f"references/{r.name}" not in corpus]

    assert orphans == [], (
        "아무 데서도 읽지 않는 참조 문서가 있다. SKILL.md 에서 가리키거나 지우세요:\n"
        + "\n".join(orphans))


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
