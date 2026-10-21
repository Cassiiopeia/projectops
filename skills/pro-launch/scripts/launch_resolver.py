#!/usr/bin/env python3
"""pro-launch 버전 무관 진입점: 설치된 스크립트 중 가장 새것 찾기 > launch_cli.py 로 인자 그대로 넘김 (#897)

이 파일 자체가 `~/.projectops/bin/launch_cli.py`(고정 진입점)로 복사된다 — 표준 라이브러리만 쓰고
다른 모듈을 import 하지 않는다. 복사본은 원래 자리를 모르므로 스스로 찾아야 한다.

찾는 순서 4단계:
  1. PROJECTOPS_LAUNCH_SCRIPTS (직접 지정)
  2. 현재 폴더가 projectops 체크아웃 안이면 그 체크아웃
  3. 플러그인 캐시(Claude · Codex, CLAUDE_CONFIG_DIR · ~/.claude* 포함) 중 가장 높은 버전 폴더
  4. 버전 없는 설치본 (Cursor · GitHub Copilot · Gemini · pi)
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

# 고정 진입점 내용 번호: 깔린 번호보다 높을 때만 덮어씀 (이 파일을 고치면 +1 — 안 올리면 퍼지지 않음)
RESOLVER_REVISION = 3
STABLE_ENTRYPOINT_NAME = "launch_cli.py"
SCRIPTS_OVERRIDE_ENV = "PROJECTOPS_LAUNCH_SCRIPTS"
# Claude Code 설정 폴더 바꾸기 (예: ~/.claude-b) — 그 아래 plugins/cache 에도 설치본이 있다 (#920)
CLAUDE_CONFIG_DIR_ENV = "CLAUDE_CONFIG_DIR"
STABLE_ENTRYPOINT_COMMAND = "python3 ~/.projectops/bin/launch_cli.py"
# 고정 진입점 권한: 직접 실행 가능 (rwxr-xr-x)
STABLE_ENTRYPOINT_MODE = 0o755

# 플러그인 캐시: {base}/{마켓플레이스}/projectops/{버전}/skills/pro-launch/scripts
# ~/.claude* glob 은 ~/.claude 자신과 ~/.claude-b 같은 설정 폴더를 함께 잡는다
_VERSIONED_CACHE_GLOBS = (".claude*/plugins/cache", ".codex/plugins/cache")
# 버전 폴더가 없는 설치본 (best effort — 폴더 모양이 설치 도구마다 다름)
_UNVERSIONED_BASES = (".cursor/skills", ".copilot/skills", ".gemini/extensions", ".pi/agent/git")
_SKILL_SCRIPTS_PARTS = ("skills", "pro-launch", "scripts")
_UNVERSIONED_WALK_MAX_DEPTH = 6
_SEMVER_PATTERN = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)")
_REVISION_PATTERN = re.compile(r"^RESOLVER_REVISION = (\d+)", re.MULTILINE)


def is_launch_scripts_dir(path: Path) -> bool:
    """진짜 pro-launch 스크립트 폴더인가 (진입점 + 구현 패키지). 고정 진입점 폴더 자신은 걸러진다."""
    return (path / "launch_cli.py").is_file() and (path / "pro_launch" / "__init__.py").is_file()


def parse_version(text: str) -> tuple[int, int, int] | None:
    """'4.54.0' > (4, 54, 0), 버전 모양이 아니면 None"""
    match = _SEMVER_PATTERN.match(text)
    return tuple(int(part) for part in match.groups()) if match else None  # type: ignore[return-value]


def find_repo_checkout_scripts(start: Path) -> Path | None:
    """start 부터 위로 올라가며 projectops 체크아웃의 pro-launch 스크립트 폴더 찾기"""
    for folder in (start, *start.parents):
        candidate = folder.joinpath(*_SKILL_SCRIPTS_PARTS)
        if is_launch_scripts_dir(candidate):
            return candidate
    return None


def versioned_cache_roots(home: Path, environment: dict | None = None) -> list[Path]:
    """플러그인 캐시 폴더 후보 (CLAUDE_CONFIG_DIR > ~/.claude* > ~/.codex), 같은 실제 경로는 한 번만"""
    environment = os.environ if environment is None else environment
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


def find_versioned_cache_scripts(home: Path, environment: dict | None = None
                                 ) -> list[tuple[tuple[int, int, int], Path]]:
    """플러그인 캐시의 (버전, 스크립트 폴더) 전부. 버전 모양이 아닌 폴더는 제외"""
    found = []
    for cache_root in versioned_cache_roots(home, environment):
        for candidate in cache_root.glob("*/projectops/*/" + "/".join(_SKILL_SCRIPTS_PARTS)):
            version = parse_version(candidate.parents[2].name)
            if version and is_launch_scripts_dir(candidate):
                found.append((version, candidate))
    return found


def _walk_unversioned(base: Path) -> Path | None:
    """깊이 제한 탐색 (node_modules · .git 제외)"""
    if not base.is_dir():
        return None
    for root, directories, _files in os.walk(base):
        root_path = Path(root)
        if root_path.parts[-3:] == _SKILL_SCRIPTS_PARTS and is_launch_scripts_dir(root_path):
            return root_path
        depth = len(root_path.relative_to(base).parts)
        directories[:] = [] if depth >= _UNVERSIONED_WALK_MAX_DEPTH else [
            name for name in directories if name not in ("node_modules", ".git", "__pycache__")]
    return None


def find_newest_installed_version(home: Path, environment: dict | None = None) -> tuple[int, int, int] | None:
    """플러그인 캐시에 깔린 가장 높은 버전 (없으면 None)"""
    versions = find_versioned_cache_scripts(home, environment)
    return max(versions)[0] if versions else None


def resolve_scripts_dir(cwd: Path | None = None, home: Path | None = None,
                        environment: dict | None = None) -> Path | None:
    """찾는 순서 4단계(모듈 설명) 중 처음 나온 것"""
    environment = os.environ if environment is None else environment
    cwd = Path.cwd() if cwd is None else cwd
    home = Path.home() if home is None else home

    # 1. 직접 지정 (틀린 경로면 조용히 넘어가지 않고 None — 호출자가 알림)
    override = environment.get(SCRIPTS_OVERRIDE_ENV)
    if override:
        override_path = Path(override).expanduser()
        return override_path if is_launch_scripts_dir(override_path) else None
    # 2. 체크아웃 (기여자가 고친 코드가 바로 돌게)
    checkout = find_repo_checkout_scripts(cwd.resolve())
    if checkout:
        return checkout
    # 3. 캐시 최고 버전
    versioned = find_versioned_cache_scripts(home, environment)
    if versioned:
        # 같은 버전이면 먼저 훑은 쪽 (CLAUDE_CONFIG_DIR > ~/.claude* > ~/.codex) — 경로 사전순이 아니라
        return max(versioned, key=lambda version_and_path: version_and_path[0])[1]
    # 4. 버전 없는 설치본
    for base in _UNVERSIONED_BASES:
        found = _walk_unversioned(home / base)
        if found:
            return found
    return None


def newer_installed_info(running_scripts_dir: Path, home: Path | None = None,
                         environment: dict | None = None) -> dict | None:
    """캐시의 옛 버전에서 돌고 있으면 {running, installed, use}, 아니면 None (체크아웃·Cursor 는 비교하지 않음)"""
    running_parts = running_scripts_dir.resolve().parts
    # 캐시 모양: .../projectops/{버전}/skills/pro-launch/scripts
    if len(running_parts) < 5 or running_parts[-5] != "projectops":
        return None
    running_version = parse_version(running_parts[-4])
    newest_version = find_newest_installed_version(Path.home() if home is None else home, environment)
    if not running_version or not newest_version or newest_version <= running_version:
        return None
    return {"running": ".".join(map(str, running_version)), "installed": ".".join(map(str, newest_version)),
            "use": STABLE_ENTRYPOINT_COMMAND}


def _installed_revision(entrypoint: Path) -> int:
    try:
        match = _REVISION_PATTERN.search(entrypoint.read_text(encoding="utf-8"))
    except OSError:
        return -1
    return int(match.group(1)) if match else -1


def refresh_stable_entrypoint(projectops_home: Path) -> bool:
    """{projectops_home}/bin/launch_cli.py 를 이 파일 내용으로 맞춤. 바뀌었으면 True

    매 실행 호출 — 깔린 번호만 읽고 비교. 같거나 높은 번호면 쓰지 않음
    (옛 버전 경로로 직접 불려도 새 진입점을 되돌리지 않게).
    """
    entrypoint = projectops_home / "bin" / STABLE_ENTRYPOINT_NAME
    if _installed_revision(entrypoint) >= RESOLVER_REVISION:
        _ensure_executable(entrypoint)
        return False
    entrypoint.parent.mkdir(parents=True, exist_ok=True)
    # 임시 파일 > 권한 > 교체 (다른 세션이 동시에 읽어도 반쯤 쓴 파일을 보지 않게)
    temporary = entrypoint.with_name(entrypoint.name + ".{}.tmp".format(os.getpid()))
    temporary.write_text(Path(__file__).read_text(encoding="utf-8"), encoding="utf-8")
    os.chmod(temporary, STABLE_ENTRYPOINT_MODE)
    os.replace(temporary, entrypoint)
    return True


def _ensure_executable(entrypoint: Path) -> None:
    """번호가 같아도 실행 권한이 없으면 붙임 (rev 1 은 644 로 깔림, #920). stat 한 번이라 매 실행 괜찮음"""
    try:
        if not entrypoint.stat().st_mode & 0o100:
            os.chmod(entrypoint, STABLE_ENTRYPOINT_MODE)
    except OSError:
        pass


def main(arguments: list[str]) -> int:
    """찾기 > 실행 (종료 코드 그대로). 못 찾으면 MCP-style JSON 으로 알림"""
    scripts_dir = resolve_scripts_dir()
    if scripts_dir is None:
        override = os.environ.get(SCRIPTS_OVERRIDE_ENV)
        summary = ("{} does not point to a pro-launch scripts dir: {}".format(SCRIPTS_OVERRIDE_ENV, override)
                   if override else "no installed pro-launch scripts found")
        print('{{"ok": false, "code": "scripts_not_found", "summary": "{}", "next": '
              '"install the projectops plugin or set {}"}}'.format(summary.replace('"', "'"),
                                                                  SCRIPTS_OVERRIDE_ENV))
        return 2
    command = [sys.executable, str(scripts_dir / "launch_cli.py"), *arguments]
    # POSIX 는 프로세스 교체(신호·stdin 그대로), Windows 는 execv 가 새 콘솔을 띄우므로 자식 실행
    if os.name == "posix":
        sys.stdout.flush()
        os.execv(sys.executable, command)
    return subprocess.call(command)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
