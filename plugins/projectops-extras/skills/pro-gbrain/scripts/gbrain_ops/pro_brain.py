"""Bridge to pro-brain (same plugin): the repo switch, rule block and personal brain source stay pro-brain's job."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from . import common

# pro-gbrain/scripts/gbrain_ops/pro_brain.py > skills/pro-brain/scripts
PRO_BRAIN_SCRIPTS = Path(__file__).resolve().parents[3] / "pro-brain" / "scripts"


def pro_brain_scripts_directory() -> Path:
    if not (PRO_BRAIN_SCRIPTS / "brain_cli.py").exists():
        raise common.StepError("pro_brain_missing", "pro-brain scripts are not next to pro-gbrain",
                               "reinstall or update the projectops-extras plugin")
    return PRO_BRAIN_SCRIPTS


def run_brain_cli(arguments: list[str], repo_root: Path | None = None) -> dict:
    """brain_cli.py <arguments> > its JSON (ok, code, summary, next, ...)"""
    command = [sys.executable, str(pro_brain_scripts_directory() / "brain_cli.py"), *arguments]
    if repo_root is not None and "--repo" not in arguments:
        command += ["--repo", str(repo_root)]
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    exit_code, output = common.run(command, env=env)
    try:
        return json.loads(output.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"ok": False, "code": "pro_brain_failed", "summary": output[-500:], "exit_code": exit_code}
