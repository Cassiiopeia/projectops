"""worktree_cli create/copy/remove 계약 (#944).

본다: 한글 브랜치명이 환경변수로 macOS/Linux 에서도 읽힌다 · --base 에서 분기한다 ·
기억한 세트 복사는 기존 파일을 덮지 않는다 · 미커밋 변경이 있으면 remove 가 거절한다.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

CLI = Path(__file__).resolve().parents[1] / "scripts" / "worktree_cli.py"
BRANCH = "20260420_#944_작업_제목"
GIT_ID = ["-c", "user.name=a", "-c", "user.email=a@a"]


def _git(repo: Path, *args):
    return subprocess.run(["git", *GIT_ID, *args], cwd=repo, check=True, capture_output=True, text=True).stdout


def _run(home: Path, *args, cwd=None) -> dict:
    env = dict(os.environ, HOME=str(home), PROJECTOPS_HOME=str(home / ".projectops"), PYTHONIOENCODING="utf-8")
    out = subprocess.run([sys.executable, str(CLI), *args], capture_output=True, text=True, env=env, cwd=cwd, timeout=120)
    assert out.stdout.strip(), out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


@pytest.fixture
def repo(tmp_path):
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    r = tmp_path / "proj"
    r.mkdir()
    _git(r, "init", "-q", "-b", "develop")
    (r / ".gitignore").write_text(".env\n", encoding="utf-8")
    _git(r, "add", ".gitignore")
    _git(r, "commit", "-q", "-m", "base")
    _git(r, "remote", "add", "origin", str(origin))
    _git(r, "push", "-q", "origin", "develop")
    _git(r, "checkout", "-q", "-b", "other")  # HEAD 는 develop 이 아니다
    (r / ".env").write_text("A=1\n", encoding="utf-8")
    return r


def test_create_branches_from_base_not_head(tmp_path, repo):
    out = _run(tmp_path, "create", "--root", str(repo), "--branch", BRANCH, "--base", "origin/develop")
    assert out["ok"] is True, out
    assert Path(out["worktree"]).is_dir()
    assert _git(repo, "rev-parse", BRANCH).strip() == _git(repo, "rev-parse", "origin/develop").strip()


def test_copy_skips_existing_and_reports_missing(tmp_path, repo):
    wt = tmp_path / "wt"
    wt.mkdir()
    (wt / ".env").write_text("KEEP=1\n", encoding="utf-8")
    out = _run(tmp_path, "copy", "--root", str(repo), "--to", str(wt), "--files", ".env,nope.txt")
    assert out["kept_existing"] == [".env"] and out["missing"] == ["nope.txt"]
    assert (wt / ".env").read_text(encoding="utf-8") == "KEEP=1\n"
    out = _run(tmp_path, "copy", "--root", str(repo), "--to", str(wt), "--files", ".env", "--overwrite")
    assert out["copied"] == [".env"] and (wt / ".env").read_text(encoding="utf-8") == "A=1\n"


def test_copy_rejects_escaping_paths(tmp_path, repo):
    wt = tmp_path / "wt"
    wt.mkdir()
    assert _run(tmp_path, "copy", "--root", str(repo), "--to", str(wt), "--files", "../x")["code"] == "bad_path"


def test_remove_refuses_dirty_then_force(tmp_path, repo):
    made = _run(tmp_path, "create", "--root", str(repo), "--branch", BRANCH, "--base", "origin/develop")
    wt = Path(made["worktree"])
    (wt / "scratch.txt").write_text("x", encoding="utf-8")
    refused = _run(tmp_path, "remove", "--root", str(repo), "--path", str(wt))
    assert refused["code"] == "dirty" and wt.exists()
    done = _run(tmp_path, "remove", "--root", str(repo), "--path", str(wt), "--force")
    assert done["ok"] is True and not wt.exists()
    assert BRANCH in _git(repo, "branch", "--list", BRANCH)  # 브랜치는 남는다
