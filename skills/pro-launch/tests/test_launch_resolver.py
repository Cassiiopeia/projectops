"""#897 — 버전 무관 진입점 (~/.projectops/bin/launch_cli.py).

지키려는 것:
  · 플러그인 캐시에 버전이 여럿 깔려 있으면 가장 높은 버전을 고른다 (사전순이 아니라 숫자순)
  · CLAUDE_CONFIG_DIR · ~/.claude-b 같은 설정 폴더의 캐시도 본다 (#920)
"""
from __future__ import annotations

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


def _make_cache_version(home: Path, version: str, marketplace: str = "projectops-marketplace",
                        config_dir: str = ".claude") -> Path:
    return _make_scripts_dir(home / config_dir / "plugins/cache" / marketplace / "projectops" / version
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


def test_claude_config_dir_and_alternate_config_folders_are_scanned(tmp_path):
    # 실측: CLAUDE_CONFIG_DIR=~/.claude-b 의 새 버전을 두고 ~/.claude 의 옛 버전이 돌았다
    home = tmp_path / "home"
    _make_cache_version(home, "4.54.0")
    _make_cache_version(home, "4.59.0", config_dir=".claude-b")
    found = launch_resolver.resolve_scripts_dir(cwd=_outside_cwd(tmp_path), home=home, environment={})
    assert found.parts[-4] == "4.59.0"
    elsewhere = tmp_path / "custom-config"
    _make_scripts_dir(elsewhere / "plugins/cache/m/projectops/4.60.0/skills/pro-launch/scripts")
    environment = {launch_resolver.CLAUDE_CONFIG_DIR_ENV: str(elsewhere)}
    assert launch_resolver.resolve_scripts_dir(cwd=_outside_cwd(tmp_path), home=home,
                                               environment=environment).parts[-4] == "4.60.0"
    # 환경변수와 glob 이 같은 폴더를 가리켜도 한 번만
    same = {launch_resolver.CLAUDE_CONFIG_DIR_ENV: str(home / ".claude-b")}
    assert len(launch_resolver.find_versioned_cache_scripts(home, same)) == 2
    # 같은 버전이면 CLAUDE_CONFIG_DIR 쪽 (지금 세션이 읽는 SKILL.md 와 같은 사본)
    _make_scripts_dir(home / ".codex/plugins/cache/m/projectops/4.59.0/skills/pro-launch/scripts")
    chosen = launch_resolver.resolve_scripts_dir(cwd=_outside_cwd(tmp_path), home=home, environment=same)
    assert ".claude-b" in chosen.parts
