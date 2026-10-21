# scripts/tests/test_projectops_cli_resolver.py
"""모든 스킬 공통 고정 진입점이 가장 새 설치본을 찾고 옛 버전 실행을 알린다 (#942)."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import projectops_cli as resolver  # noqa: E402


def _install(cache: Path, version: str, skill_folder="pro-github", cli="github_cli.py") -> Path:
    scripts = cache / "market" / "projectops" / version / "skills" / skill_folder / "scripts"
    scripts.mkdir(parents=True)
    (scripts / cli).write_text("# stub\n", encoding="utf-8")
    return scripts


def test_가장_높은_버전을_고른다(tmp_path):
    cache = tmp_path / ".claude" / "plugins" / "cache"
    _install(cache, "4.9.0")
    newest = _install(cache, "4.62.0")
    assert resolver.resolve_scripts_dir("github", cwd=tmp_path, home=tmp_path, environment={}) == newest


def test_CLAUDE_CONFIG_DIR_의_캐시도_본다(tmp_path):
    config_dir = tmp_path / "elsewhere"
    scripts = _install(config_dir / "plugins" / "cache", "4.62.0")
    assert resolver.resolve_scripts_dir("github", cwd=tmp_path, home=tmp_path,
                                        environment={"CLAUDE_CONFIG_DIR": str(config_dir)}) == scripts


def test_다른_스킬은_자기_폴더에서만_찾는다(tmp_path):
    cache = tmp_path / ".claude" / "plugins" / "cache"
    _install(cache, "4.62.0", "pro-commit", "commit_cli.py")
    assert resolver.resolve_scripts_dir("github", cwd=tmp_path, home=tmp_path, environment={}) is None
    assert resolver.resolve_scripts_dir("commit", cwd=tmp_path, home=tmp_path, environment={}) is not None


def test_체크아웃이_캐시보다_먼저다(tmp_path):
    cache = tmp_path / ".claude" / "plugins" / "cache"
    _install(cache, "4.62.0")
    checkout = tmp_path / "repo" / "skills" / "pro-github" / "scripts"
    checkout.mkdir(parents=True)
    (checkout / "github_cli.py").write_text("# stub\n", encoding="utf-8")
    assert resolver.resolve_scripts_dir("github", cwd=tmp_path / "repo", home=tmp_path, environment={}) == checkout


def test_옛_버전에서_돌고_있으면_newer_installed(tmp_path):
    cache = tmp_path / ".claude" / "plugins" / "cache"
    old = _install(cache, "4.49.0")
    _install(cache, "4.62.0")
    info = resolver.newer_installed_info(old, "github", home=tmp_path, environment={})
    assert info["running"] == "4.49.0" and info["installed"] == "4.62.0"
    assert resolver.newer_installed_info(resolver.resolve_scripts_dir("github", cwd=tmp_path, home=tmp_path,
                                                                      environment={}), "github", home=tmp_path,
                                         environment={}) is None


def test_스킬_이름의_pro_접두사를_받는다():
    assert resolver.normalize_skill_name("pro-github") == "github" and resolver.normalize_skill_name("github") == "github"


def test_고정_진입점은_번호가_높을_때만_덮는다(tmp_path):
    assert resolver.refresh_stable_entrypoint(tmp_path) is True
    entrypoint = tmp_path / "bin" / "projectops_cli.py"
    assert entrypoint.exists() and entrypoint.stat().st_mode & 0o100
    assert resolver.refresh_stable_entrypoint(tmp_path) is False


def test_모르는_스킬은_JSON_으로_알린다(capsys):
    assert resolver.main(["nope"]) == 1
    assert '"code": "bad_args"' in capsys.readouterr().out


def test_홈에_복사한_설치본도_찾는다_Cursor_Copilot(tmp_path):
    # npx projectops 가 복사한 설치본: ~/.cursor/skills · ~/.copilot/skills (#200)
    copilot = tmp_path / ".copilot" / "skills" / "pro-github" / "scripts"
    copilot.mkdir(parents=True)
    (copilot / "github_cli.py").write_text("# stub\n", encoding="utf-8")
    assert resolver.resolve_scripts_dir("github", cwd=tmp_path, home=tmp_path, environment={}) == copilot
