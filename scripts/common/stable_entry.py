"""Install the stable entry point and warn about old versions (#942).

run_cli calls this on every run. It only reads and compares installed versions, so it is light, and failures never block the command.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

_SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
# Add the warning only once per process
_warned = False


def _projectops_home() -> Path:
    return Path(os.environ.get("PROJECTOPS_HOME") or Path.home() / ".projectops")


def _load_resolver():
    if str(_SCRIPTS_ROOT) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS_ROOT))
    import projectops_cli
    return projectops_cli


def refresh_and_check(running_cli_path: str) -> Optional[dict]:
    """Bring the stable entry point up to date; if running from an old cached version, return {running, installed, use}. Otherwise None"""
    global _warned
    # Keep tests from touching the real ~/.projectops/bin
    if "PYTEST_CURRENT_TEST" in os.environ:
        return None
    try:
        resolver = _load_resolver()
        resolver.refresh_stable_entrypoint(_projectops_home())
        running_dir = Path(running_cli_path).resolve().parent
        skill = next((name for name, (folder, cli) in resolver.SKILL_CLIS.items()
                      if running_dir.parent.name == folder and running_dir.name == "scripts"), None)
        if skill is None or _warned:
            return None
        info = resolver.newer_installed_info(running_dir, skill)
        _warned = info is not None
        return info
    except Exception:  # A failed entry-point update must not block the command
        return None
