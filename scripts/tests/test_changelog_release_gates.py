# scripts/tests/test_changelog_release_gates.py
"""changelog-deploy create-pr 거절 계약 · deploy 브랜치형 판정 (#970)."""
import importlib.util
import io
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills" / "pro-changelog-deploy" / "scripts"
for extra in (ROOT / "scripts", SCRIPTS):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from common.cli_parser import run_cli  # noqa: E402
from common.gh_client import GitHubAPIError  # noqa: E402

_spec = importlib.util.spec_from_file_location("changelog_cli_970", SCRIPTS / "changelog_cli.py")
changelog_cli = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(changelog_cli)
release_pr = sys.modules["release_pr"]


def _run(monkeypatch, argv):
    buffer = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buffer)
    return_code = run_cli(changelog_cli.build_parser(), argv)
    return return_code, json.loads(buffer.getvalue().strip().splitlines()[-1])


def _patch_github(monkeypatch, existing_pr=None, create_error=None, app_release=None):
    created = []
    monkeypatch.setattr(release_pr, "get_github_pat", lambda o, r: "pat")
    monkeypatch.setattr(release_pr, "load_config", lambda path: None)
    monkeypatch.setattr(release_pr, "read_app_release", lambda config, o, r: app_release)
    monkeypatch.setattr(release_pr, "find_open_pr_by_base", lambda *a, **k: existing_pr)
    monkeypatch.setattr(release_pr, "get_ahead_by", lambda *a: None)

    def fake_create(*args):
        if create_error:
            raise create_error
        created.append(args)
        return {"number": 9, "url": "u"}

    monkeypatch.setattr(release_pr, "create_pull_request", fake_create)
    return created


def _app_repo(tmp_path):
    (tmp_path / "version.yml").write_text('project_types: ["flutter"]\n', encoding="utf-8")
    return tmp_path


def test_앱_심사_레포는_승인_없이_PR_을_만들지_않는다(monkeypatch, tmp_path):
    # 실사고 (#970): 앱 심사 레포에서 승인 없이 deploy PR 생성
    created = _patch_github(monkeypatch)
    base_argv = ["create-pr", "o", "r", "t", "", "develop", "main", "--project-root", str(_app_repo(tmp_path))]
    return_code, out = _run(monkeypatch, base_argv)
    assert return_code == 1 and out["code"] == "needs_user_approval" and not created
    # 사용자가 일반 배포로 기록한 레포(app_release=false)는 막지 않는다
    created = _patch_github(monkeypatch, app_release=False)
    assert _run(monkeypatch, base_argv)[1]["ok"] and created


def test_기존_PR_은_pr_exists_커밋_없음은_nothing_to_deploy(monkeypatch, tmp_path):
    (tmp_path / ".github" / "workflows").mkdir(parents=True)  # 앱 신호 없는 일반 레포
    argv = ["create-pr", "o", "r", "t", "", "develop", "main", "--project-root", str(tmp_path)]
    _patch_github(monkeypatch, existing_pr={"number": 5, "url": "pu"})
    out = _run(monkeypatch, argv)[1]
    assert out["code"] == "pr_exists" and out["number"] == 5 and out["next"].endswith("--pr 5")
    no_commits = GitHubAPIError(422, "Validation Failed (PullRequest/custom/No commits between main and develop)")
    _patch_github(monkeypatch, create_error=no_commits)
    assert _run(monkeypatch, argv)[1]["code"] == "nothing_to_deploy"


def test_개발_브랜치_없이_deploy_만_있으면_deploy_branch_형(monkeypatch, tmp_path):
    # 실사고 (#970): main > deploy 레포에서 없는 develop 을 head 로 냄
    origin = tmp_path / "origin.git"
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    repo.mkdir()

    def git(*args):
        subprocess.run(["git", "-c", "user.name=a", "-c", "user.email=a@a", *args], cwd=repo,
                       check=True, capture_output=True)

    git("init", "-q", "-b", "main")
    git("remote", "add", "origin", str(origin))
    git("commit", "-q", "--allow-empty", "-m", "base")
    git("push", "-q", "origin", "main", "main:deploy")
    git("fetch", "-q", "origin")
    return_code, out = _run(monkeypatch, ["detect-release-context", "--project-root", str(repo),
                                          "--owner", "o", "--repo", "r", "--config", str(tmp_path / "none.json")])
    assert return_code == 0 and out["release_shape"] == "deploy_branch"
    assert out["release_branches"] == {"head": "main", "base": "deploy"}
    assert isinstance(out["summary"], str) and out["summary"]
