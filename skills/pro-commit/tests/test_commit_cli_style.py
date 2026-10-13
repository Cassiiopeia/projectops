"""pro-commit 이 개인·팀 형식을 따르는지 CLI 수준에서 본다 (#864)."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CLI = ROOT / "skills" / "pro-commit" / "scripts" / "commit_cli.py"
URL = "https://github.com/o/r/issues/3"


def _run(args, home, cwd):
    out = subprocess.run([sys.executable, str(CLI), *args], capture_output=True, text=True, cwd=cwd,
                         env={"HOME": str(home), "USERPROFILE": str(home), "PYTHONIOENCODING": "utf-8"})
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
