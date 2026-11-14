#!/usr/bin/env python3
"""figma_cli — compares a design against the implemented screen (projectops 3-layer Layer 2).

**The eye does not catch it.** A button once shipped with three of its four effect rows
(the inner ones) missing entirely. It passed even with a full-screen golden — a 10px inner
shadow inside 361x68 is a few pixels at that size, so it looks the same with or without it.

Value assertions (`expect(shadow.blur, 10)`) only stop half of it. They guard **only what you
thought to assert**. A missing row was never asserted, so nobody counts it.

So it does two things.

  coverage — lists **every** style entry in the dump, forcing each one to be classified.
             The point is to separate values that could not be ported from ones chosen not to be.
  diff     — overlays the images and extracts the differing regions as blobs.

A person makes the call. This script **only counts, lists and draws**.
"""
from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_PROJECT_ROOT = _HERE.parents[3]
_SCRIPTS_ROOT = _PROJECT_ROOT / "scripts"
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))
# Implementation package (figma_tools) sits next to this file — found relative to the entry file regardless of install location
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))

from figma_tools.cli import build_parser, main  # noqa: E402,F401
from figma_tools.commands.assets import cmd_assets  # noqa: E402,F401
from figma_tools.commands.compose import cmd_store_compose  # noqa: E402,F401
from figma_tools.commands.conform import cmd_conform  # noqa: E402,F401
from figma_tools.commands.coverage import cmd_coverage  # noqa: E402,F401
from figma_tools.commands.diff import cmd_diff  # noqa: E402,F401
from figma_tools.commands.fetch import cmd_fetch  # noqa: E402,F401
from figma_tools.commands.fresh import cmd_check_fresh  # noqa: E402,F401
from figma_tools.commands.screens import cmd_screens  # noqa: E402,F401
from figma_tools.commands.svg_check import cmd_svg_check  # noqa: E402,F401
from figma_tools.commands.ingest import cmd_ingest  # noqa: E402,F401
from figma_tools.commands.output_path import cmd_output_path  # noqa: E402,F401
from figma_tools.commands.token import cmd_token  # noqa: E402,F401
from figma_tools.commands.store import cmd_store_check, cmd_store_specs  # noqa: E402,F401
from figma_tools.commands.store_pages import cmd_store_pages  # noqa: E402,F401
from figma_tools.commands.store_upload import (  # noqa: E402,F401
    cmd_store_upload_mark, cmd_store_upload_plan, cmd_store_upload_status,
)
# Names the pure value-check tests read directly from the entry module
from figma_tools.conform_probes import (  # noqa: E402,F401
    _CORNER_LIMIT, _CORNER_PROBE, _fill_kind, _parse_radius, _shadow_offsets,
)


if __name__ == "__main__":
    sys.exit(main())
