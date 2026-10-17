"""#897 — 버전 무관 진입점 (~/.projectops/bin/launch_cli.py).

지키려는 것:
  · 플러그인 캐시에 버전이 여럿 깔려 있으면 가장 높은 버전을 고른다 (사전순이 아니라 숫자순)
  · PROJECTOPS_LAUNCH_SCRIPTS 가 모든 탐색보다 앞선다
  · 고정 진입점은 한 번만 쓰이고, 옛 버전이 새 진입점을 되돌리지 않는다
  · 고정 진입점이 인자와 종료 코드를 그대로 넘긴다
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import launch_resolver  # noqa: E402

# 가짜 launch_cli.py: 받은 인자를 찍고 마지막 인자를 종료 코드로 쓴다
_FAKE_CLI = (
    "import sys, json\n"
    "print(json.dumps({'from': __file__, 'args': sys.argv[1:]}))\n"
    "sys.exit(int(sys.argv[-1]) if sys.argv[1:] and sys.argv[-1].isdigit() else 0)\n"
)


def _make_scripts_dir(path: Path) -> Path:
    (path / "pro_launch").mkdir(parents=True)
    (path / "pro_launch" / "__init__.py").write_text("", encoding="utf-8")
    (path / "launch_cli.py").write_text(_FAKE_CLI, encoding="utf-8")
    return path


def _make_cache_version(home: Path, version: str, marketplace: str = "projectops-marketplace") -> Path:
    return _make_scripts_dir(home / ".claude/plugins/cache" / marketplace / "projectops" / version
                             / "skills/pro-launch/scripts")


def _outside_cwd(tmp_path: Path) -> Path:
    folder = tmp_path / "somewhere"
    folder.mkdir(exist_ok=True)
    return folder


def test_picks_highest_semver_not_lexical(tmp_path):
    home = tmp_path / "home"
    for version in ("4.9.0", "4.54.0", "4.28.0", "4.100.1"):
        _make_cache_version(home, version)
    (home / ".claude/plugins/cache/projectops-marketplace/projectops/not-a-version").mkdir()
    found = launch_resolver.resolve_scripts_dir(cwd=_outside_cwd(tmp_path), home=home, environment={})
    assert found.parts[-4] == "4.100.1"


def test_versions_across_marketplaces_and_codex(tmp_path):
    home = tmp_path / "home"
    _make_cache_version(home, "4.50.0", marketplace="old-marketplace")
    _make_scripts_dir(home / ".codex/plugins/cache/m/projectops/4.60.0/skills/pro-launch/scripts")
    found = launch_resolver.resolve_scripts_dir(cwd=_outside_cwd(tmp_path), home=home, environment={})
    assert found.parts[-4] == "4.60.0"


def test_override_env_wins(tmp_path):
    home = tmp_path / "home"
    _make_cache_version(home, "9.9.9")
    override = _make_scripts_dir(tmp_path / "mine")
    environment = {launch_resolver.SCRIPTS_OVERRIDE_ENV: str(override)}
    assert launch_resolver.resolve_scripts_dir(cwd=_outside_cwd(tmp_path), home=home,
                                               environment=environment) == override


def test_wrong_override_is_not_silently_ignored(tmp_path):
    home = tmp_path / "home"
    _make_cache_version(home, "4.54.0")
    environment = {launch_resolver.SCRIPTS_OVERRIDE_ENV: str(tmp_path / "missing")}
    assert launch_resolver.resolve_scripts_dir(cwd=_outside_cwd(tmp_path), home=home,
                                               environment=environment) is None


def test_repo_checkout_beats_cache(tmp_path):
    home = tmp_path / "home"
    _make_cache_version(home, "9.9.9")
    checkout = _make_scripts_dir(tmp_path / "repo/skills/pro-launch/scripts")
    deep = tmp_path / "repo/src/deep"
    deep.mkdir(parents=True)
    assert launch_resolver.resolve_scripts_dir(cwd=deep, home=home, environment={}) == checkout.resolve()


def test_cursor_install_is_last_resort(tmp_path):
    home = tmp_path / "home"
    cursor = _make_scripts_dir(home / ".cursor/skills/pro-launch/scripts")
    assert launch_resolver.resolve_scripts_dir(cwd=_outside_cwd(tmp_path), home=home,
                                               environment={}) == cursor
    _make_cache_version(home, "4.54.0")
    assert launch_resolver.resolve_scripts_dir(cwd=_outside_cwd(tmp_path), home=home,
                                               environment={}).parts[-4] == "4.54.0"


def test_stable_entrypoint_written_once(tmp_path):
    projectops_home = tmp_path / ".projectops"
    assert launch_resolver.refresh_stable_entrypoint(projectops_home) is True
    entrypoint = projectops_home / "bin" / "launch_cli.py"
    assert entrypoint.read_text(encoding="utf-8") == (SCRIPTS / "launch_resolver.py").read_text(encoding="utf-8")
    modified_time = entrypoint.stat().st_mtime_ns
    assert launch_resolver.refresh_stable_entrypoint(projectops_home) is False
    assert entrypoint.stat().st_mtime_ns == modified_time
    assert not list(entrypoint.parent.glob("*.tmp"))


def test_older_revision_does_not_overwrite_newer(tmp_path):
    projectops_home = tmp_path / ".projectops"
    entrypoint = projectops_home / "bin" / "launch_cli.py"
    entrypoint.parent.mkdir(parents=True)
    newer = "RESOLVER_REVISION = {}\n# newer\n".format(launch_resolver.RESOLVER_REVISION + 1)
    entrypoint.write_text(newer, encoding="utf-8")
    assert launch_resolver.refresh_stable_entrypoint(projectops_home) is False
    assert entrypoint.read_text(encoding="utf-8") == newer
    entrypoint.write_text("RESOLVER_REVISION = 0\n", encoding="utf-8")
    assert launch_resolver.refresh_stable_entrypoint(projectops_home) is True


def _run_stable_entrypoint(tmp_path: Path, home: Path, *arguments: str) -> subprocess.CompletedProcess:
    projectops_home = tmp_path / ".projectops"
    launch_resolver.refresh_stable_entrypoint(projectops_home)
    environment = {"HOME": str(home), "USERPROFILE": str(home), "PATH": "", "SYSTEMROOT": ""}
    return subprocess.run([sys.executable, str(projectops_home / "bin" / "launch_cli.py"), *arguments],
                          cwd=_outside_cwd(tmp_path), env=environment, capture_output=True, text=True,
                          timeout=30)


def test_stable_entrypoint_forwards_args_and_exit_code(tmp_path):
    home = tmp_path / "home"
    _make_cache_version(home, "4.53.0")
    _make_cache_version(home, "4.54.0")
    completed = _run_stable_entrypoint(tmp_path, home, "web", "text", "--label", "한글 인자", "3")
    assert completed.returncode == 3, completed.stderr
    assert "4.54.0" in completed.stdout
    assert '"args": ["web", "text", "--label"' in completed.stdout


def test_stable_entrypoint_reports_when_nothing_installed(tmp_path):
    completed = _run_stable_entrypoint(tmp_path, tmp_path / "empty-home", "doctor")
    assert completed.returncode == 2
    assert '"code": "scripts_not_found"' in completed.stdout


def test_stale_install_notice_only_for_older_cache_version(tmp_path):
    home = tmp_path / "home"
    old = _make_cache_version(home, "4.28.0")
    newest = _make_cache_version(home, "4.54.0")
    notice = launch_resolver.stale_install_notice(old, home=home)
    assert notice and "4.28.0" in notice and "4.54.0" in notice
    assert launch_resolver.stale_install_notice(newest, home=home) is None
    assert launch_resolver.stale_install_notice(SCRIPTS, home=home) is None
