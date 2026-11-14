"""Repro environment (#1000): OS · Python · working folder · git · CLI path and version run · installed version · Claude Code version"""
from __future__ import annotations

import json
import platform
import re
import subprocess
import sys
from pathlib import Path

from bug import transcript
from bug.redact import redact_text

# CLI path in a command (starts with ~ or /, ends with *_cli.py)
CLI_PATH_PATTERN = re.compile(r"(~?/[^\s\"']*?_cli\.py)")
# 2 plugin names to look up installed versions
PLUGIN_NAMES = ("projectops", "projectops-extras")
# Stable entry point: hands off to the newest installed script on every run (#942)
ENTRY_POINT_FILE_NAME = "projectops_cli.py"
# Wait limit for external commands (seconds)
COMMAND_TIMEOUT_SECONDS = 3


def collect_context(command: str | None, cwd: Path | None = None) -> dict:
    """Environment facts (home path masked as ~). cwd is the working folder at failure time (git fields null if it no longer exists)"""
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
    """Command > existing CLI file path (that file if it is the stable entry point projectops_cli.py)"""
    for raw in CLI_PATH_PATTERN.findall(command):
        path = Path(raw).expanduser()
        if path.is_file():
            return path.resolve()
    return None


def cli_version(cli_path: Path, installed_versions: dict) -> str | None:
    """CLI version: the manifest for files inside a plugin, the newest installed version it hands off to for the stable entry point"""
    version = plugin_version_near(cli_path)
    if version or cli_path.name != ENTRY_POINT_FILE_NAME:
        return version
    newest = installed_versions.get("projectops")
    return f"{newest} (newest installed, via {ENTRY_POINT_FILE_NAME})" if newest else None


def plugin_version_near(path: Path) -> str | None:
    """version from the first .claude-plugin/plugin.json found walking up from the CLI path"""
    for folder in path.parents:
        manifest = folder / ".claude-plugin" / "plugin.json"
        if manifest.is_file():
            try:
                return json.loads(manifest.read_text(encoding="utf-8")).get("version")
            except (OSError, ValueError):
                return None
    return None


def newest_installed_version(plugin_name: str) -> str | None:
    """Highest version among <config dir>/plugins/cache/*/<name>/<version>/"""
    versions = []
    for base in transcript.config_dirs():
        for folder in (base / "plugins" / "cache").glob(f"*/{plugin_name}/*"):
            if folder.is_dir() and re.fullmatch(r"\d+(\.\d+)*", folder.name):
                versions.append(folder.name)
    return max(versions, key=lambda version: tuple(int(part) for part in version.split("."))) if versions else None


def _git(cwd: Path, *args: str) -> str | None:
    return _run(["git", "-C", str(cwd), *args])


def _run(arguments: list[str]) -> str | None:
    """One-line output of an external command (None on failure, timeout or not installed)"""
    try:
        completed = subprocess.run(arguments, capture_output=True, text=True, errors="replace", timeout=COMMAND_TIMEOUT_SECONDS)
    except (OSError, subprocess.SubprocessError):
        return None
    output = completed.stdout.strip()
    return output.splitlines()[0] if completed.returncode == 0 and output else None
