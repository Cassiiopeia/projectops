"""pro-ui-design implementation package: local mockup sessions + designer requests. The agent judges; this only runs and gathers facts
Entry point scripts/ui_design_cli.py. This file only sets up the shared common import path
"""
from __future__ import annotations

import sys
from pathlib import Path

# <repo>/scripts — where the common/ shared by all skills lives
COMMON_ROOT = Path(__file__).resolve().parents[4] / "scripts"

if str(COMMON_ROOT) not in sys.path:
    sys.path.insert(0, str(COMMON_ROOT))
