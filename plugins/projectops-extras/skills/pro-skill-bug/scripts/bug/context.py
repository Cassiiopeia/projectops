"""재현 환경 수집 (#1000): OS · Python · 작업 폴더 · git · 실행된 CLI 경로와 버전 · 설치 버전 · Claude Code 버전"""
from __future__ import annotations

import json
import platform
import re
import subprocess
import sys
from pathlib import Path

from bug import transcript
from bug.redact import redact_text

# 명령 속 CLI 경로 (~ 또는 / 로 시작, *_cli.py 로 끝남)
CLI_PATH_PATTERN = re.compile(r"(~?/[^\s\"']*?_cli\.py)")
# 설치 버전을 찾을 플러그인 이름 2개
PLUGIN_NAMES = ("projectops", "projectops-extras")
# 고정 진입점: 실행할 때마다 최신 설치본 스크립트로 넘긴다 (#942)
ENTRY_POINT_FILE_NAME = "projectops_cli.py"
# 외부 명령 대기 상한 (초)
COMMAND_TIMEOUT_SECONDS = 3


def collect_context(command: str | None, cwd: Path | None = None) -> dict:
    """환경 사실 모음 (홈 경로는 ~ 로 가림). cwd 는 실패 당시 작업 폴더 (지금 없으면 git 칸은 null)"""
    cwd = cwd or Path.cwd()
    is_folder_present = cwd.is_dir()
    cli_path = find_cli_path(command or "")
    installed_versions = {name: newest_installed_version(name) for name in PLUGIN_NAMES}
    facts = {
        "os": f"{platform.system()} {platform.release()} ({platform.machine()})",
        "os_version": platform.mac_ver()[0] or platform.version(),
        "python": sys.version.split()[0],
        "cwd": str(cwd),
        "cwd_exists_now": is_folder_present,
        "is_git_repo": _git(cwd, "rev-parse", "--is-inside-work-tree") == "true" if is_folder_present else None,
        "git_branch": _git(cwd, "branch", "--show-current") if is_folder_present else None,
        "cli_path": str(cli_path) if cli_path else None,
        "cli_plugin_version": cli_version(cli_path, installed_versions) if cli_path else None,
        "installed_versions": installed_versions,
        "claude_code_version": _run(["claude", "--version"]),
    }
    return json.loads(redact_text(json.dumps(facts, ensure_ascii=False))[0])


def find_cli_path(command: str) -> Path | None:
    """명령 > 실제 있는 CLI 파일 경로 (고정 진입점 projectops_cli.py 면 그 파일)"""
    for raw in CLI_PATH_PATTERN.findall(command):
        path = Path(raw).expanduser()
        if path.is_file():
            return path.resolve()
    return None


def cli_version(cli_path: Path, installed_versions: dict) -> str | None:
    """CLI 버전: 플러그인 안 파일이면 그 매니페스트, 고정 진입점이면 그것이 넘겨주는 최신 설치 버전"""
    version = plugin_version_near(cli_path)
    if version or cli_path.name != ENTRY_POINT_FILE_NAME:
        return version
    newest = installed_versions.get("projectops")
    return f"{newest} (newest installed, via {ENTRY_POINT_FILE_NAME})" if newest else None


def plugin_version_near(path: Path) -> str | None:
    """CLI 경로에서 위로 올라가며 처음 만나는 .claude-plugin/plugin.json 의 version"""
    for folder in path.parents:
        manifest = folder / ".claude-plugin" / "plugin.json"
        if manifest.is_file():
            try:
                return json.loads(manifest.read_text(encoding="utf-8")).get("version")
            except (OSError, ValueError):
                return None
    return None


def newest_installed_version(plugin_name: str) -> str | None:
    """<설정 폴더>/plugins/cache/*/<이름>/<버전>/ 중 가장 높은 버전"""
    versions = []
    for base in transcript.config_dirs():
        for folder in (base / "plugins" / "cache").glob(f"*/{plugin_name}/*"):
            if folder.is_dir() and re.fullmatch(r"\d+(\.\d+)*", folder.name):
                versions.append(folder.name)
    return max(versions, key=lambda version: tuple(int(part) for part in version.split("."))) if versions else None


def _git(cwd: Path, *args: str) -> str | None:
    return _run(["git", "-C", str(cwd), *args])


def _run(arguments: list[str]) -> str | None:
    """외부 명령 1줄 결과 (실패 · 시간 초과 · 미설치면 None)"""
    try:
        completed = subprocess.run(arguments, capture_output=True, text=True, timeout=COMMAND_TIMEOUT_SECONDS)
    except (OSError, subprocess.SubprocessError):
        return None
    output = completed.stdout.strip()
    return output.splitlines()[0] if completed.returncode == 0 and output else None
