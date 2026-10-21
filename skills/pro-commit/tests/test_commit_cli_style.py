"""pro-commit 이 개인·팀 형식을 따르는지 CLI 수준에서 본다 (#864)."""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CLI = ROOT / "skills" / "pro-commit" / "scripts" / "commit_cli.py"
URL = "https://github.com/o/r/issues/3"


def _env(home) -> dict:
    """PATH·SYSTEMROOT 는 살리고 HOME 계열과 PYTHONPATH 만 격리한다 (기여자 config 가 새지 않게)."""
    # GIT_* 를 빼고 전역·시스템 gitconfig 를 끈다 — 기여자의 insteadOf·hooks 가 git 호출에 끼지 않게
    env = {k: v for k, v in os.environ.items()
           if k not in ("HOME", "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "PYTHONPATH") and not k.startswith("GIT_")}
    env.update({"HOME": str(home), "USERPROFILE": str(home), "PYTHONIOENCODING": "utf-8",
                "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"})
    return env


def _run(args, home, cwd):
    out = subprocess.run([sys.executable, str(CLI), *args], capture_output=True, text=True, cwd=cwd,
                         env=_env(home))
    return json.loads(out.stdout)


def _home(tmp_path, data):
    home = tmp_path / "home"
    (home / ".projectops" / "config").mkdir(parents=True)
    (home / ".projectops" / "config" / "config.json").write_text(json.dumps(data), encoding="utf-8")
    return home


def test_personal_preset_in_plain_repo(tmp_path):
    home = _home(tmp_path, {"skills": {"pro-commit": {"preset": "conventional", "tone": "imperative"}}})
    repo = tmp_path / "r"; repo.mkdir()
    p = _run(["get-commit-template", "[Bug] 로그인", URL, "--repo-root", str(repo)], home, repo)
    assert p["ok"] and p["template"] == f"fix: {{description}}\n\n{URL}"
    s = _run(["resolve-style", "--repo-root", str(repo)], home, repo)
    assert s["tone"] == "imperative" and s["preset"] == "conventional"


def test_team_template_in_projectops_repo(tmp_path):
    home = _home(tmp_path, {"skills": {"pro-commit": {"preset": "gitmoji"}}})
    repo = tmp_path / "r"; repo.mkdir()
    (repo / "version.yml").write_text("metadata:\n  template: {}\n", encoding="utf-8")
    p = _run(["get-commit-template", "⚙️[기능추가] 검색", URL, "--repo-root", str(repo)], home, repo)
    assert p["template"] == f"검색 : feat : {{description}} {URL}" and p["source"] == "team-default"


def test_repo_root_flag_vs_cwd(tmp_path):
    home = _home(tmp_path, {"skills": {"pro-commit": {"preset": "conventional"}}})
    repo = tmp_path / "r"; repo.mkdir()
    (repo / "version.yml").write_text("metadata:\n  template: {}\n", encoding="utf-8")
    plain = tmp_path / "plain"; plain.mkdir()
    args = ["get-commit-template", "[Bug] 로그인", URL]
    # cwd 는 일반 폴더, --repo-root 로 설치 레포를 가리키면 팀 형식
    assert _run(args + ["--repo-root", str(repo)], home, tmp_path)["source"] == "team-default"
    # 플래그 없이 cwd 만으로도 판정
    assert _run(args, home, repo)["source"] == "team-default"
    assert _run(args, home, plain)["template"].startswith("fix: ")


def test_subfolder_of_git_repo_uses_root_version_yml(tmp_path):
    """--repo-root 없이 하위 폴더에서 불러도 git 루트의 팀 형식을 쓴다 (#864 최종 리뷰)."""
    home = _home(tmp_path, {"skills": {"pro-commit": {"preset": "conventional"}}})
    repo = tmp_path / "r"; repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True, env=_env(home))
    (repo / "version.yml").write_text("metadata:\n  template: {}\n", encoding="utf-8")
    sub = repo / "src" / "deep"; sub.mkdir(parents=True)
    p = _run(["get-commit-template", "[Bug] 로그인", URL], home, sub)
    assert p["source"] == "team-default" and p["template"] == f"로그인 : fix : {{description}} {URL}"


def test_legacy_user_gets_projectops_with_source(tmp_path):
    home = _home(tmp_path, {"github": {"commit": {"auto_approve": False}}})
    repo = tmp_path / "r"; repo.mkdir()
    s = _run(["resolve-style", "--repo-root", str(repo)], home, repo)
    assert s["source"] == "legacy-default" and s["preset"] == "projectops"


def test_team_commit_type_map_applies(tmp_path):
    home = _home(tmp_path, {})
    repo = tmp_path / "r"; repo.mkdir()
    (repo / "version.yml").write_text(
        "issue_helper:\n  commit_type_map:\n    정리: chore\n", encoding="utf-8")
    p = _run(["get-commit-template", "[정리] 로그", URL, "--repo-root", str(repo)], home, repo)
    assert p["template"] == f"로그 : chore : {{description}} {URL}"


def test_commit_paths_skips_already_staged_deletion(tmp_path):
    # 실사고: git rm 으로 스테이징된 삭제 경로를 --paths 에 넣으면 pathspec 오류로 stage_failed (#971)
    home = _home(tmp_path, {})
    env = {**_env(home), "GIT_AUTHOR_NAME": "a", "GIT_AUTHOR_EMAIL": "a@a",
           "GIT_COMMITTER_NAME": "a", "GIT_COMMITTER_EMAIL": "a@a"}
    repo = tmp_path / "r"; repo.mkdir()
    git = ["git", "-C", str(repo)]
    subprocess.run([*git, "init", "-q"], check=True, env=env)
    (repo / "old.txt").write_text("x", encoding="utf-8")
    subprocess.run([*git, "add", "old.txt"], check=True, env=env)
    subprocess.run([*git, "commit", "-q", "-m", "init"], check=True, env=env)
    subprocess.run([*git, "rm", "-q", "old.txt"], check=True, env=env)
    (repo / "new.txt").write_text("y", encoding="utf-8")
    # 줄바꿈으로 이어진 경로 하나도 함께 재현
    out = subprocess.run([sys.executable, str(CLI), "commit", "--message", "m", "--root", str(repo),
                          "--paths", "old.txt\nnew.txt"], capture_output=True, text=True, cwd=repo, env=env)
    assert json.loads(out.stdout).get("commit"), out.stdout
    tracked = subprocess.run([*git, "ls-files"], capture_output=True, text=True, env=env).stdout.split()
    assert tracked == ["new.txt"]
    # 실사고: .gitignore 대상 경로가 섞이면 이유 없이 stage_failed — 원인 code 로 돌려준다
    (repo / ".gitignore").write_text("docs/\n", encoding="utf-8")
    (repo / "docs").mkdir()
    (repo / "docs" / "spec.md").write_text("z", encoding="utf-8")
    out = subprocess.run([sys.executable, str(CLI), "commit", "--message", "m", "--root", str(repo),
                          "--paths", ".gitignore", "docs/spec.md"], capture_output=True, text=True, cwd=repo, env=env)
    result = json.loads(out.stdout)
    assert result["code"] == "path_ignored" and result["paths"] == ["docs/spec.md"], out.stdout
