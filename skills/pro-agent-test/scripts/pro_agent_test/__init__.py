"""pro-agent-test implementation package — QA procedure (detect · scenario · note · api · other).

The entry point is `scripts/e2e_cli.py`. Launching and capturing apps, web and servers lives in pro-launch.

This file only sets the import path, so the shared layer (`<repo>/scripts/common`) is found whether run as a script or imported by a test.

  launch_bridge   pro-launch subprocess calls · forwarding of moved commands
  storage         record location · scenario file lookup · precondition expansion
  scenario_rules  scenario templates · validation
  notes/          learned.json read/write · memory loading · screen targets · tidy
  commands/       cmd_* per subcommand (detect · scenario · note · api · other)
"""
from __future__ import annotations

import sys
from pathlib import Path

# <repo>/scripts — where common/ shared by all skills lives
COMMON_ROOT = Path(__file__).resolve().parents[4] / "scripts"

if str(COMMON_ROOT) not in sys.path:
    sys.path.insert(0, str(COMMON_ROOT))
