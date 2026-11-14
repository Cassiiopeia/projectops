"""Settings: disk-cleanup section of ~/.projectops/config/config.json (defaults if missing)"""
from __future__ import annotations

import json
import time
from pathlib import Path

from . import shell

CONFIG_SECTION = "disk-cleanup"
# Anything touched within this window is not deleted (hours)
DEFAULT_IDLE_HOURS = 2
# Backup: ~/.projectops/backups/disk-cleanup/{yyyyMMdd}/{repo}/{branch}
DEFAULT_BACKUP_PARTS = (".projectops", "backups", "disk-cleanup")


def _section() -> dict:
    path = Path.home() / ".projectops" / "config" / "config.json"
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    section = loaded.get(CONFIG_SECTION) if isinstance(loaded, dict) else None
    return section if isinstance(section, dict) else {}


def worktree_roots(cli_roots: list[str] | None) -> tuple[list[Path], str]:
    """Work folder search roots > (paths, source). Flag > settings > parent folder of the current repo"""
    if cli_roots:
        return [Path(root).expanduser() for root in cli_roots], "flag"
    configured = _section().get("roots")
    if isinstance(configured, list) and configured:
        return [Path(str(root)).expanduser() for root in configured], "config"
    code, top_level = shell.git(str(Path.cwd()), "rev-parse", "--path-format=absolute", "--git-common-dir")
    if code == 0 and top_level:
        return [Path(top_level).parent.parent], "current_repo_parent"
    return [Path.cwd()], "current_folder"


def idle_hours(cli_value: float | None) -> float:
    if cli_value is not None:
        return cli_value
    configured = _section().get("idle_hours")
    return float(configured) if isinstance(configured, (int, float)) else DEFAULT_IDLE_HOURS


def backup_root(cli_value: str | None) -> Path:
    configured = cli_value or _section().get("backup_dir")
    base = Path(str(configured)).expanduser() if configured else Path.home().joinpath(*DEFAULT_BACKUP_PARTS)
    return base / time.strftime("%Y%m%d")
