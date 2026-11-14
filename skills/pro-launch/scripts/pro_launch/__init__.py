"""pro-launch implementation package — launches, drives and captures apps, web and servers.

The entry point is `scripts/launch_cli.py`. What lives where is in `ARCHITECTURE.md` in the same folder.

This file only fixes import paths, so the skill's helper modules (credentials · knowledge · stealth …) and
the shared layer (`<repo>/scripts/common`) are found whether run as a script or imported by tests.
"""
from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
# skills/pro-launch/scripts — where the helper modules live
SCRIPTS_DIR = _HERE.parent.parent
# <repo>/scripts — where common/, shared by every skill, lives
COMMON_ROOT = _HERE.parents[4] / "scripts"

for _p in (COMMON_ROOT, SCRIPTS_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
