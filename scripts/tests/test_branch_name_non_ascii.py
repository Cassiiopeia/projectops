# scripts/tests/test_branch_name_non_ascii.py
"""한글 브랜치명이 글자 중간에서 잘리지 않는다 (#938)."""
import io
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for extra in ("scripts", "skills/pro-github/scripts"):
    if str(ROOT / extra) not in sys.path:
        sys.path.insert(0, str(ROOT / extra))

from common import issue_number  # noqa: E402
from common.cli_parser import run_cli  # noqa: E402
from github_cli import build_parser  # noqa: E402

KOREAN_BRANCH = "20260420_#653_FCM_푸시_페이로드에_라우팅용_데이터_포함_필요"
# 비ASCII 브랜치명을 자르는 git 명령 (Apple Git 2.39.5 에서 확인)
TRUNCATING_IDIOMS = ("--abbrev-ref", "symbolic-ref --short")


def test_get_current_branch_keeps_korean_name(tmp_path, monkeypatch):
    for cmd in (["init", "-q"], ["commit", "-q", "--allow-empty", "-m", "x",
                                 "--author", "a <a@a>"], ["checkout", "-q", "-b", KOREAN_BRANCH]):
        subprocess.run(["git", "-c", "user.name=a", "-c", "user.email=a@a", *cmd], cwd=tmp_path, check=True)
    monkeypatch.chdir(tmp_path)
    assert issue_number.get_current_branch() == KOREAN_BRANCH


def test_skill_docs_and_scripts_do_not_use_truncating_git_idioms():
    offenders = []
    targets = [*ROOT.glob("skills/**/*.md"), *ROOT.glob("skills/**/*.py"), *ROOT.glob("scripts/common/**/*.py")]
    for path in targets:
        if "tests" in path.parts or path.name.startswith("test_"):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if any(idiom in text for idiom in TRUNCATING_IDIOMS):
            offenders.append(path.relative_to(ROOT).as_posix())
    assert not offenders, f"git branch --show-current 를 쓴다: {offenders}"


def _run_create_pr(monkeypatch, head, branch_head):
    import github_cli
    monkeypatch.setattr(github_cli, "get_github_pat", lambda o, r: "pat")
    monkeypatch.setattr(github_cli, "get_branch_head", lambda o, r, b, p: branch_head)
    created = []
    monkeypatch.setattr(github_cli, "create_pull_request",
                        lambda *a: created.append(a) or {"number": 1, "url": "u"})
    buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buf)
    rc = run_cli(build_parser(), ["create-pr", "o", "r", "t", "/nonexistent.md", head, "develop"])
    return rc, json.loads(buf.getvalue().strip().splitlines()[-1]), created


def test_create_pr_rejects_truncated_head(monkeypatch):
    rc, out, created = _run_create_pr(monkeypatch, "o:20260420_#653_FCM_�", "sha")
    assert out["code"] == "head_branch_truncated" and not created


def test_create_pr_rejects_head_missing_on_origin(monkeypatch):
    rc, out, created = _run_create_pr(monkeypatch, f"o:{KOREAN_BRANCH}", None)
    assert out["code"] == "head_branch_not_on_origin" and not created


def test_create_pr_proceeds_when_head_exists(monkeypatch):
    rc, out, created = _run_create_pr(monkeypatch, f"o:{KOREAN_BRANCH}", "sha")
    assert out["ok"] is not False and created
