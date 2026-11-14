"""get-output-path: where to save the consulting report (path rules owned only by common/paths.py)
"""
from __future__ import annotations

import os
from pathlib import Path

from oss_consult.output import _fail, _out


def cmd_get_output_path(args) -> int:
    # Path rules are owned only by common/paths.py — do not reimplement here (#525)
    from common.paths import resolve_output_path
    cwd = getattr(args, "cwd", None)
    if cwd:
        if not Path(cwd).is_dir():
            return _fail("bad_args", f"--cwd is not a directory: {cwd}", "Pass the path of the repo that will hold the report")
        # Paths are computed from the cwd's git root — point at the working repo, not the script folder
        os.chdir(cwd)
    res = resolve_output_path(args.skill_id, args.title)
    if not res.get("ok", True):
        res.setdefault("summary", res.get("error"))
        if not res.get("next"):
            res["next"] = "Run inside the git repository that will hold the report, or point at it with --cwd"
    elif not res.get("next"):
        res["next"] = "Save the report at this path (show a summary and get approval before saving)"
    return _out(res)
