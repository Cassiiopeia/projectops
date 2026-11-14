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
    """Check that every reference path the docs point to actually exists.

    #543: in SKILL.md, `references/x.md` means the skill's own folder, so shared docs
    must be `../references/x.md`. Getting this prefix wrong left 50 places in 16 skills
    pointing at missing paths; the issue-creation procedure doc could not be found and
    the duplicate check and approval gate were skipped.

    common-rules.md had this check as a heredoc snippet, but it had to be run by hand,
    so nobody ran it. Moved here so CI runs it every time (#612).

    Only paths with a directory prefix are checked — bare file names (`impl.md`) cannot be
    told apart from temp file names or table entries and cause false positives.
    """
    # Also check cross-skill references like `../<other skill>/references/x.md`. Matching only the tail
    # drops the leading path, resolves it to the own folder, and misses broken references.
    pattern = re.compile(r"`((?:\.\./)*(?:[a-z0-9_.-]+/)*references/[a-z0-9_-]+\.md)`")
    broken, checked = [], 0
    for path in _skill_doc_paths():
        for m in pattern.finditer(path.read_text(encoding="utf-8")):
            checked += 1
            target = (path.parent / m.group(1)).resolve()
            if not target.exists():
                broken.append(f"{path.relative_to(ROOT).as_posix()}: {m.group(1)}")

    assert checked > 0, "found no references at all — the check is running empty"
    assert broken == [], "points to docs that do not exist:\n" + "\n".join(broken)


def test_no_reference_doc_is_orphaned():
    """Every skill reference doc must actually be read from somewhere.

    A doc nobody points to is **known only to its author**. Over time it goes stale without
    anyone noticing, and nobody knows it exists when it needs fixing. A 109-line doc in
    `pro-agent-test` sat like that for a long time and kept outdated content after the
    output rules changed (#584).

    It is enough for the own SKILL.md or a sibling reference doc to point to it as `references/<file>`.
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
        "some reference docs are never read. Point to them from SKILL.md or delete them:\n"
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


def test_script_invocation_documents_3layer_architecture():
    """script-invocation.md (canonical invocation standard, #1133) must state the 3-layer architecture and the skill CLI mapping."""
    text = (ROOT / "skills" / "references" / "script-invocation.md").read_text(encoding="utf-8")
    # issue_cli.py was removed by the pro-issue merge (#464) — absorbed by github_cli. note_cli.py left with pro-note's removal (#853).
    for cli in ["github_cli.py", "report_cli.py",
                "review_cli.py", "changelog_cli.py"]:
        assert cli in text, f"{cli} mapping missing from script-invocation.md"
    # 3-layer key keywords
    for keyword in ["scripts/common/", "skills/<skill>/scripts/", "self-contained 5-line"]:
        assert keyword in text, f"\"{keyword}\" keyword missing"


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
    """commit_cli.py must emit JSON on stdout even for bad arguments."""
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
    """report_cli.py must emit JSON on stdout even for bad arguments."""
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
    """review_cli.py must emit JSON on stdout even for bad arguments."""
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


def test_github_cli_bad_args_emits_json():
    """github_cli.py must emit JSON on stdout even for bad arguments."""
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
    """changelog_cli.py must emit JSON on stdout even for bad arguments."""
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
    """mcp-subcommand-rules.md must state the JSONArgumentParser usage rule (issue #329)."""
    path = ROOT / "skills" / "references" / "mcp-subcommand-rules.md"
    text = path.read_text(encoding="utf-8")
    assert "JSONArgumentParser" in text
    assert "bad_args" in text
    assert "available_subcommands" in text


# Calls that handle no non-ASCII and need no PYTHONIOENCODING (file path, reason).
# Adding one here requires evidence that input and output are digits and English only.
_ASCII_ONLY_PYTHON_CALLS = {
    # Prints only the PR number (integer)
    ("skills/pro-changelog-deploy/SKILL.md", "get('number','')"),
    # Only checks package presence via exit code (no output)
    ("skills/pro-ssh/SKILL.md", 'import paramiko'),
}


def _bash_logical_lines(text):
    """Return ```bash blocks as logical commands, joining backslash continuations."""
    for block in re.findall(r"```(?:bash|sh)\n(.*?)```", text, re.S):
        block = re.sub(r"\\\n\s*", " ", block)
        yield from block.splitlines()


def test_python_calls_in_skill_docs_force_utf8_stdio():
    """#653: `$PYTHON` calls that carry Korean text must set PYTHONIOENCODING=utf-8.

    On Windows, where the default encoding is not UTF-8, python writes stdout as cp949 etc.,
    so Korean captured by command substitution got committed garbled. In practice only the
    second call (`-c`) in pro-commit step 6 was missing it.

    Kept narrow: variable assignment (`PYTHON=`), `-z` checks and `-m pip` are out of scope,
    and digit-only calls go in the allow list above with a reason.
    """
    call = re.compile(r'"?\$PYTHON"?\s+(?:-c\b|"?[\w$/{}.~-]+\.py\b|"\$\w+(?:_PATH|_SCRIPT)")')
    failures = []
    for path in _skill_doc_paths():
        rel = path.relative_to(ROOT).as_posix()
        for line in _bash_logical_lines(path.read_text(encoding="utf-8")):
            stripped = line.strip()
            if stripped.startswith(("PYTHON=", "[ -z", "if ", "#")):
                continue
            if not call.search(line) or "PYTHONIOENCODING=utf-8" in line:
                continue
            if any(rel == f and key in line for f, key in _ASCII_ONLY_PYTHON_CALLS):
                continue
            failures.append(f"{rel}: {stripped[:100]}")
    assert failures == []


def test_every_skill_documents_customize_section():
    """Keep the documented promise that every skill accepts per-person settings (#864)."""
    missing = [p.parent.name for p in sorted((ROOT / "skills").glob("pro-*/SKILL.md"))
               if "## Customize" not in p.read_text(encoding="utf-8")]
    assert missing == []


def test_common_rules_load_preferences():
    text = (ROOT / "skills" / "references" / "common-rules.md").read_text(encoding="utf-8")
    assert "prefs_cli.py resolve" in text


def test_skills_do_not_route_commits_through_pro_commit():
    """Commit style differs per person. Skill docs outside pro-commit do not force commits through a specific skill (#864)."""
    hits = []
    for path in sorted((ROOT / "skills").rglob("*.md")):
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith("skills/pro-commit/") or "__pycache__" in rel:
            continue
        text = path.read_text(encoding="utf-8")
        if "/pro-commit" in text or "commit_cli" in text:
            hits.append(rel)
    assert hits == []


def _frontmatter_description(path):
    """frontmatter description value. Strips double and single quotes; block scalars fail instead of passing silently."""
    m = re.search(r"^description:[ \t]*(.*)$", path.read_text(encoding="utf-8"), re.MULTILINE)
    if not m:
        return ""
    value = m.group(1).strip()
    assert not re.match(r"^[|>][+-]?\d*$", value), f"{path}: block scalar description is not supported"
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    return value


def test_descriptions_short_and_english():
    """description is loaded into every session context. Short, and in English for users worldwide (#864)."""
    paths = [*sorted((ROOT / "skills").glob("pro-*/SKILL.md")),
             *sorted((ROOT / "plugins").glob("*/skills/pro-*/SKILL.md"))]
    bad = []
    for p in paths:
        d = _frontmatter_description(p)
        if not d or len(d) > 300 or re.search(r"[가-힣]", d):
            bad.append(f"{p.parent.name}: {len(d)}")
    assert bad == []
