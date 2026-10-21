# scripts/tests/test_output_path_root_issue.py
"""get-output-path 가 프로젝트 밖에서도 --root/$PROJECT_ROOT 로 풀리고 --issue 를 받는다 (#943)."""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from common.paths import resolve_output_path  # noqa: E402


@pytest.fixture
def project(tmp_path):
    repo = tmp_path / "proj"
    repo.mkdir()
    for cmd in (["init", "-q"], ["checkout", "-q", "-b", "20260420_#77_작업_제목"],
                ["commit", "-q", "--allow-empty", "-m", "x"]):
        subprocess.run(["git", "-c", "user.name=a", "-c", "user.email=a@a", *cmd], cwd=repo, check=True)
    return repo


@pytest.fixture
def outside(tmp_path, monkeypatch):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    monkeypatch.delenv("PROJECT_ROOT", raising=False)
    return elsewhere


def test_without_root_outside_git_returns_hint(outside):
    out = resolve_output_path("report", "제목")
    assert out["code"] == "git_not_found" and "--root" in out["next"]


def test_root_argument_resolves_from_outside(outside, project):
    out = resolve_output_path("report", "제목", root=str(project))
    assert out["path"].startswith(str(project.resolve())) and "_77_" in out["path"]


def test_project_root_env_is_used(outside, project, monkeypatch):
    monkeypatch.setenv("PROJECT_ROOT", str(project))
    assert "_77_" in resolve_output_path("report", "제목")["path"]


def test_issue_argument_overrides_branch_number(outside, project):
    out = resolve_output_path("report", "제목", root=str(project), issue=123)
    assert "_123_" in out["path"] and out["mismatch"] is False


def test_missing_root_is_reported(outside):
    assert resolve_output_path("report", "제목", root="/no/such/dir")["code"] == "root_not_found"


def test_title_tags_and_repeated_issue_number_are_dropped(outside, project):
    # 실사고: 파일명에 태그가 남고(`버그클라홈_…`) 번호가 두 번 들어감(`574_574_`) (#971)
    out = resolve_output_path("report", "❗[버그][클라홈] #574 홈 화면 수정", root=str(project), issue=574)
    assert Path(out["path"]).name.endswith("_574_홈_화면_수정.md")
