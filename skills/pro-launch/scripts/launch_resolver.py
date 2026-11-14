#!/usr/bin/env python3
"""Version-independent pro-launch entry point: find the newest installed scripts > pass args through to launch_cli.py (#897)

This file itself is copied to `~/.projectops/bin/launch_cli.py` (fixed entry point) — it uses only the standard library
and imports no other module. The copy does not know its origin, so it must find it itself.

4-step lookup order:
  1. PROJECTOPS_LAUNCH_SCRIPTS (set explicitly)
  2. the checkout, if the current folder is inside a projectops checkout
  3. the highest version folder in plugin caches (Claude · Codex, including CLAUDE_CONFIG_DIR · ~/.claude*)
  4. unversioned installs (Cursor · GitHub Copilot · Gemini · pi)
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

# Fixed entry point content revision: overwrite only when higher than the installed one (+1 when editing this file — otherwise it does not spread)
RESOLVER_REVISION = 4
STABLE_ENTRYPOINT_NAME = "launch_cli.py"
SCRIPTS_OVERRIDE_ENV = "PROJECTOPS_LAUNCH_SCRIPTS"
# Overridden Claude Code config folder (e.g. ~/.claude-b) — installs also live under its plugins/cache (#920)
CLAUDE_CONFIG_DIR_ENV = "CLAUDE_CONFIG_DIR"
# On Windows python3 may be the Microsoft Store stub
STABLE_ENTRYPOINT_COMMAND = f"{'python' if sys.platform == 'win32' else 'python3'} ~/.projectops/bin/launch_cli.py"
# Fixed entry point permissions: directly executable (rwxr-xr-x)
STABLE_ENTRYPOINT_MODE = 0o755

# Plugin cache: {base}/{marketplace}/projectops/{version}/skills/pro-launch/scripts
# The ~/.claude* glob catches ~/.claude itself and config folders like ~/.claude-b
_VERSIONED_CACHE_GLOBS = (".claude*/plugins/cache", ".codex/plugins/cache")
# Installs without a version folder (best effort — folder layout differs per install tool)
_UNVERSIONED_BASES = (".cursor/skills", ".copilot/skills", ".gemini/extensions", ".pi/agent/git")
_SKILL_SCRIPTS_PARTS = ("skills", "pro-launch", "scripts")
_UNVERSIONED_WALK_MAX_DEPTH = 6
_SEMVER_PATTERN = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)")
_REVISION_PATTERN = re.compile(r"^RESOLVER_REVISION = (\d+)", re.MULTILINE)


def is_launch_scripts_dir(path: Path) -> bool:
    """Is this a real pro-launch scripts folder (entry point + implementation package). The fixed entry point folder itself is filtered out."""
    return (path / "launch_cli.py").is_file() and (path / "pro_launch" / "__init__.py").is_file()


def parse_version(text: str) -> tuple[int, int, int] | None:
    """'4.54.0' > (4, 54, 0), None if not version-shaped"""
    match = _SEMVER_PATTERN.match(text)
    return tuple(int(part) for part in match.groups()) if match else None  # type: ignore[return-value]


def find_repo_checkout_scripts(start: Path) -> Path | None:
    """Walk up from start to find the pro-launch scripts folder of a projectops checkout"""
    for folder in (start, *start.parents):
        candidate = folder.joinpath(*_SKILL_SCRIPTS_PARTS)
        if is_launch_scripts_dir(candidate):
            return candidate
    return None


def versioned_cache_roots(home: Path, environment: dict | None = None) -> list[Path]:
    """Plugin cache folder candidates (CLAUDE_CONFIG_DIR > ~/.claude* > ~/.codex), each real path only once"""
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
    """All (version, scripts folder) in plugin caches. Non-version-shaped folders are excluded"""
    found = []
    for cache_root in versioned_cache_roots(home, environment):
        for candidate in cache_root.glob("*/projectops/*/" + "/".join(_SKILL_SCRIPTS_PARTS)):
            version = parse_version(candidate.parents[2].name)
            if version and is_launch_scripts_dir(candidate):
                found.append((version, candidate))
    return found


def _walk_unversioned(base: Path) -> Path | None:
    """Depth-limited search (excluding node_modules · .git)"""
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
    """Highest version installed in plugin caches (None if none)"""
    versions = find_versioned_cache_scripts(home, environment)
    return max(versions)[0] if versions else None


def readable_cwd(environment: dict | None = None) -> Path | None:
    """Current folder path. If getcwd fails (macOS protected folder EPERM · deleted folder) re-enter via $PWD and retry; None if it still fails (#1131)"""
    try:
        return Path.cwd()
    except OSError:
        pass
    shell_folder = (os.environ if environment is None else environment).get("PWD", "")
    if not os.path.isabs(shell_folder):
        return None
    try:
        os.chdir(shell_folder)
        return Path.cwd()
    except OSError:
        return None


def resolve_scripts_dir(cwd: Path | None = None, home: Path | None = None,
                        environment: dict | None = None) -> Path | None:
    """First hit of the 4-step lookup order (see module docstring)"""
    environment = os.environ if environment is None else environment
    cwd = readable_cwd(environment) if cwd is None else cwd
    home = Path.home() if home is None else home

    # 1. Explicit (a wrong path returns None instead of silently moving on — the caller reports it)
    override = environment.get(SCRIPTS_OVERRIDE_ENV)
    if override:
        override_path = Path(override).expanduser()
        return override_path if is_launch_scripts_dir(override_path) else None
    # 2. Checkout (so contributors' edits run immediately)
    checkout = find_repo_checkout_scripts(cwd.resolve()) if cwd else None
    if checkout:
        return checkout
    # 3. Highest cached version
    versioned = find_versioned_cache_scripts(home, environment)
    if versioned:
        # On equal versions, the one scanned first (CLAUDE_CONFIG_DIR > ~/.claude* > ~/.codex) — not path lexical order
        return max(versioned, key=lambda version_and_path: version_and_path[0])[1]
    # 4. Unversioned install
    for base in _UNVERSIONED_BASES:
        found = _walk_unversioned(home / base)
        if found:
            return found
    return None


def newer_installed_info(running_scripts_dir: Path, home: Path | None = None,
                         environment: dict | None = None) -> dict | None:
    """{running, installed, use} when running from an old cached version, otherwise None (checkout·Cursor are not compared)"""
    running_parts = running_scripts_dir.resolve().parts
    # Cache layout: .../projectops/{version}/skills/pro-launch/scripts
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
    """Sync {projectops_home}/bin/launch_cli.py to this file's content. True if changed

    Called every run — reads and compares only the installed revision. Not written when the revision is equal or higher
    (so being called directly via an old version path does not roll back a newer entry point).
    """
    entrypoint = projectops_home / "bin" / STABLE_ENTRYPOINT_NAME
    if _installed_revision(entrypoint) >= RESOLVER_REVISION:
        _ensure_executable(entrypoint)
        return False
    entrypoint.parent.mkdir(parents=True, exist_ok=True)
    # temp file > permissions > swap (so concurrent readers never see a half-written file)
    temporary = entrypoint.with_name(entrypoint.name + ".{}.tmp".format(os.getpid()))
    temporary.write_text(Path(__file__).read_text(encoding="utf-8"), encoding="utf-8")
    os.chmod(temporary, STABLE_ENTRYPOINT_MODE)
    os.replace(temporary, entrypoint)
    return True


def _ensure_executable(entrypoint: Path) -> None:
    """Add the execute bit even when the revision matches (rev 1 was installed as 644, #920). One stat, so fine every run"""
    try:
        if not entrypoint.stat().st_mode & 0o100:
            os.chmod(entrypoint, STABLE_ENTRYPOINT_MODE)
    except OSError:
        pass


def main(arguments: list[str]) -> int:
    """Find > run (exit code passed through). If not found, report as MCP-style JSON"""
    # Child CLIs also resolve relative paths against the current folder, so stop with JSON instead of a traceback
    if readable_cwd() is None:
        print('{"ok": false, "code": "cwd_unreadable", "summary": "cannot read the current folder (macOS privacy '
              'protection or a deleted folder)", "next": "cd into the project folder again (or cd ~ and pass '
              'absolute paths), then retry"}')
        return 2
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
    # POSIX replaces the process (signals·stdin kept); on Windows execv opens a new console, so run a child
    if os.name == "posix":
        sys.stdout.flush()
        os.execv(sys.executable, command)
    return subprocess.call(command)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
