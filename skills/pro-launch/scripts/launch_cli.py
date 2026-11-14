#!/usr/bin/env python3
"""launch_cli — pro-launch CLI (projectops 3-layer standard, Layer 2, #629).

Holds only the ability to **launch, drive and capture** apps, web and servers. What to capture and why is decided
by the calling task skills (pro-agent-test · pro-ui-design · pro-figma).

Principle: **the agent decides, scripts run and record.** It does not guess project structure.

Subcommands:
    doctor           tool install status · storage locations
    detect           what can be launched (marker files · devices · browsers)
    devices          attached devices · booted simulators · AVDs
    device           bind roles to devices (list · bind · unbind · show)
    app              capture (shot) and launch (launch) app screens
    web              browser control (setup · open · goto · click · type · shot · assert ·
                     console · close · viewport · route)
    http             single HTTP request
    access           connection records (show · set · unset)
    db               run SQL (connected as recorded in access)
    logs             server logs (read as recorded in access)
    shrink           downscale · WebP for issue attachments
    mask · redact    cover image regions · hide secrets and personal-data patterns before posting to issues
    recall · learn · forget   remember interaction methods that worked on this computer (more accurate with use)
    get-output-path  this run's location + env.sh

Output: MCP-style JSON (ok/code/summary/next 4 fields guaranteed).
"""
from __future__ import annotations

import sys
from pathlib import Path

# This file is only the entry point. The implementation is in the pro_launch package in the same folder (map: pro_launch/ARCHITECTURE.md).
_HERE = Path(__file__).resolve()
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))

from pro_launch.cli import build_parser, main  # noqa: E402,F401


def _refresh_stable_entrypoint() -> None:
    """Refresh ~/.projectops/bin/launch_cli.py (version-independent entry point) + newer_installed in the response JSON when running an old cached version (#897·#920).

    Put in JSON, not stderr — so a `2>&1 | json.load` pipe does not break. The command runs even if this fails
    """
    try:
        import launch_resolver
        from common.state import base_dir
        from pro_launch.runtime.plugin_version import set_newer_installed
        launch_resolver.refresh_stable_entrypoint(base_dir())
        set_newer_installed(launch_resolver.newer_installed_info(_HERE.parent))
    except Exception:  # noqa: BLE001 — an extra feature must not block the main command
        pass


if __name__ == "__main__":
    _refresh_stable_entrypoint()
    sys.exit(main())
