#!/usr/bin/env python3
"""projectops 스킬 CLI 공통 고정 진입점: 설치된 가장 새 스크립트를 찾아 인자를 그대로 넘긴다 (#942).

    python3 ~/.projectops/bin/projectops_cli.py <skill> <서브커맨드> [인자...]
    예) projectops_cli.py github get-issue o r 12  /  commit commit --message-file m.txt

이 파일 자체가 `~/.projectops/bin/projectops_cli.py` 로 복사된다 — 표준 라이브러리만 쓰고 다른 모듈을
import 하지 않는다. 복사본은 원래 자리를 모르므로 스스로 찾는다. pro-launch 의 고정 진입점
(`launch_cli.py`)과 같은 찾기 규칙을 모든 스킬에 쓴다.

찾는 순서: PROJECTOPS_SKILLS_ROOT(직접 지정) > 현재 폴더가 체크아웃이면 그 체크아웃 > 플러그인 캐시 최고 버전
> 버전 없는 설치본.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

# 고정 진입점 내용 번호: 깔린 번호보다 높을 때만 덮어씀 (이 파일을 고치면 +1)
RESOLVER_REVISION = 2
STABLE_ENTRYPOINT_NAME = "projectops_cli.py"
STABLE_ENTRYPOINT_MODE = 0o755
SKILLS_ROOT_ENV = "PROJECTOPS_SKILLS_ROOT"
CLAUDE_CONFIG_DIR_ENV = "CLAUDE_CONFIG_DIR"
STABLE_ENTRYPOINT_COMMAND = "python3 ~/.projectops/bin/projectops_cli.py <skill>"

# 스킬 이름 > (스킬 폴더, CLI 파일)
SKILL_CLIS = {
    "github": ("pro-github", "github_cli.py"),
    "commit": ("pro-commit", "commit_cli.py"),
    "report": ("pro-report", "report_cli.py"),
    "review": ("pro-review", "review_cli.py"),
    "testcase": ("pro-testcase", "testcase_cli.py"),
    "changelog-deploy": ("pro-changelog-deploy", "changelog_cli.py"),
    "init-worktree": ("pro-init-worktree", "worktree_cli.py"),
    "figma": ("pro-figma", "figma_cli.py"),
    "agent-test": ("pro-agent-test", "e2e_cli.py"),
    "design-brief": ("pro-design-brief", "design_brief_cli.py"),
    "oss-consult": ("pro-oss-consult", "oss_cli.py"),
    "launch": ("pro-launch", "launch_cli.py"),
}

_VERSIONED_CACHE_GLOBS = (".claude*/plugins/cache", ".codex/plugins/cache")
_UNVERSIONED_BASES = (".cursor/skills", ".copilot/skills", ".gemini/extensions", ".pi/agent/git")
_UNVERSIONED_WALK_MAX_DEPTH = 6
_SEMVER_PATTERN = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)")
_REVISION_PATTERN = re.compile(r"^RESOLVER_REVISION = (\d+)", re.MULTILINE)


def normalize_skill_name(name: str) -> str:
    """'pro-github' > 'github'"""
    return name[4:] if name.startswith("pro-") else name


def is_scripts_dir(path: Path, skill: str) -> bool:
    folder, cli_file = SKILL_CLIS[skill]
    return path.name == "scripts" and path.parent.name == folder and (path / cli_file).is_file()


def parse_version(text: str):
    match = _SEMVER_PATTERN.match(text)
    return tuple(int(part) for part in match.groups()) if match else None


def versioned_cache_roots(home: Path, environment: dict) -> list:
    """플러그인 캐시 폴더 후보 (CLAUDE_CONFIG_DIR > ~/.claude* > ~/.codex), 같은 실제 경로는 한 번만"""
    candidates = []
    config_dir = environment.get(CLAUDE_CONFIG_DIR_ENV)
    if config_dir:
        candidates.append(Path(config_dir).expanduser() / "plugins" / "cache")
    for pattern in _VERSIONED_CACHE_GLOBS:
        candidates.extend(sorted(home.glob(pattern)))
    roots, seen = [], set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if candidate.is_dir() and resolved not in seen:
            seen.add(resolved)
            roots.append(candidate)
    return roots


def find_versioned_scripts(skill: str, home: Path, environment: dict) -> list:
    """플러그인 캐시의 (버전, 스크립트 폴더) 전부"""
    folder = SKILL_CLIS[skill][0]
    found = []
    for cache_root in versioned_cache_roots(home, environment):
        for candidate in cache_root.glob(f"*/projectops/*/skills/{folder}/scripts"):
            version = parse_version(candidate.parents[2].name)
            if version and is_scripts_dir(candidate, skill):
                found.append((version, candidate))
    return found


def find_checkout_scripts(skill: str, start: Path):
    folder = SKILL_CLIS[skill][0]
    for parent in (start, *start.parents):
        candidate = parent / "skills" / folder / "scripts"
        if is_scripts_dir(candidate, skill):
            return candidate
    return None


def _walk_unversioned(base: Path, skill: str):
    if not base.is_dir():
        return None
    for root, directories, _files in os.walk(base):
        root_path = Path(root)
        if root_path.name == "scripts" and is_scripts_dir(root_path, skill):
            return root_path
        depth = len(root_path.relative_to(base).parts)
        directories[:] = [] if depth >= _UNVERSIONED_WALK_MAX_DEPTH else [
            name for name in directories if name not in ("node_modules", ".git", "__pycache__")]
    return None


def resolve_scripts_dir(skill: str, cwd=None, home=None, environment=None):
    """찾는 순서(모듈 설명)의 처음 나온 스크립트 폴더. 못 찾으면 None"""
    environment = os.environ if environment is None else environment
    cwd = Path.cwd() if cwd is None else cwd
    home = Path.home() if home is None else home
    override = environment.get(SKILLS_ROOT_ENV)
    if override:
        candidate = Path(override).expanduser() / "skills" / SKILL_CLIS[skill][0] / "scripts"
        return candidate if is_scripts_dir(candidate, skill) else None
    checkout = find_checkout_scripts(skill, cwd.resolve())
    if checkout:
        return checkout
    versioned = find_versioned_scripts(skill, home, environment)
    if versioned:
        return max(versioned, key=lambda version_and_path: version_and_path[0])[1]
    for base in _UNVERSIONED_BASES:
        found = _walk_unversioned(home / base, skill)
        if found:
            return found
    return None


def newer_installed_info(running_scripts_dir: Path, skill: str, home=None, environment=None):
    """캐시의 옛 버전에서 돌고 있으면 {running, installed, use}, 아니면 None (체크아웃은 비교하지 않음)"""
    running_parts = running_scripts_dir.resolve().parts
    if len(running_parts) < 5 or running_parts[-5] != "projectops":
        return None
    running_version = parse_version(running_parts[-4])
    environment = os.environ if environment is None else environment
    versions = find_versioned_scripts(skill, Path.home() if home is None else home, environment)
    newest = max(versions)[0] if versions else None
    if not running_version or not newest or newest <= running_version:
        return None
    return {"running": ".".join(map(str, running_version)), "installed": ".".join(map(str, newest)),
            "use": f"{STABLE_ENTRYPOINT_COMMAND}"}


def _installed_revision(entrypoint: Path) -> int:
    try:
        match = _REVISION_PATTERN.search(entrypoint.read_text(encoding="utf-8"))
    except OSError:
        return -1
    return int(match.group(1)) if match else -1


def refresh_stable_entrypoint(projectops_home: Path) -> bool:
    """{projectops_home}/bin/projectops_cli.py 를 이 파일 내용으로 맞춤. 바뀌었으면 True (같거나 높은 번호면 안 씀)"""
    entrypoint = projectops_home / "bin" / STABLE_ENTRYPOINT_NAME
    if _installed_revision(entrypoint) >= RESOLVER_REVISION:
        return False
    entrypoint.parent.mkdir(parents=True, exist_ok=True)
    temporary = entrypoint.with_name(f"{entrypoint.name}.{os.getpid()}.tmp")
    temporary.write_text(Path(__file__).read_text(encoding="utf-8"), encoding="utf-8")
    os.chmod(temporary, STABLE_ENTRYPOINT_MODE)
    os.replace(temporary, entrypoint)
    return True


def main(arguments: list) -> int:
    if not arguments or normalize_skill_name(arguments[0]) not in SKILL_CLIS:
        print('{"ok": false, "code": "bad_args", "summary": "usage: projectops_cli.py <skill> <subcommand> ...", '
              '"available_skills": %s, "next": "첫 인자에 스킬 이름을 준다"}' % str(sorted(SKILL_CLIS)).replace("'", '"'))
        return 1
    skill = normalize_skill_name(arguments[0])
    scripts_dir = resolve_scripts_dir(skill)
    if scripts_dir is None:
        print('{"ok": false, "code": "scripts_not_found", "summary": "no installed pro-%s scripts found", '
              '"next": "install the projectops plugin or set %s"}' % (skill, SKILLS_ROOT_ENV))
        return 1
    return subprocess.call([sys.executable, str(scripts_dir / SKILL_CLIS[skill][1]), *arguments[1:]])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
