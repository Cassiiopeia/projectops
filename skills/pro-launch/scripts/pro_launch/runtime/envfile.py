"""Writing `env.sh` — the only place that writes run environment variables (RUN_DIR·SHOT_DIR·DEV·PKG)."""
from __future__ import annotations

import os
import re
from pathlib import Path

from pro_launch.runtime.devices import sole_device


def resolve_run_dir(args) -> Path | None:
    """Where to write env.sh. **No guessing** — picking a recent folder fails silently when wrong."""
    v = getattr(args, "run_dir", None) or os.environ.get("RUN_DIR")
    return Path(v).resolve() if v else None


def _sh_quote(value: str) -> str:
    """Quote so the shell uses the value as is. With double quotes `$` expands into **a different value**."""
    return "'" + value.replace("'", "'\\''") + "'"


def _run_var(skill: str) -> str:
    """Variable holding the run name. launch → LAUNCH_RUN, agent-test → AGENT_TEST_RUN.

    Shared variables (RUN_DIR·SHOT_DIR·DEV·PKG) have the same names whichever skill writes them —
    dozens of doc examples rely on those names.
    """
    return re.sub(r"[^A-Z0-9]+", "_", skill.upper()).strip("_") + "_RUN"


def write_env_sh(run_dir: Path, package: str | None,
                  bindings: list[dict] | None = None, skill: str | None = None) -> Path:
    """Write the run environment. **This is the only place that writes this file.**

    **Role names are never used in shell variable names.** Names with Korean, spaces or hyphens
    make `export DEV_{name}=...` fail and `$DEV_{name}` silently become a wrong value.
    They are fixed by number and the name goes in the value.
    """
    shots = run_dir / "screenshots"
    shots.mkdir(parents=True, exist_ok=True)
    env = run_dir / "env.sh"
    # If the skill name is unknown (device rewriting later), inherit the name written first
    if skill is None and env.is_file():
        m = re.search(r"^export ([A-Z0-9_]+_RUN)=", env.read_text(encoding="utf-8"), re.M)
        var = m.group(1) if m else _run_var("launch")
    else:
        var = _run_var(skill or "launch")

    lines = [
        "# Run environment — load it with `source env.sh`.",
        "# Do not build paths by hand. Create nothing outside the places listed here.",
        "export %s=%s" % (var, _sh_quote(run_dir.name)),
        "export RUN_DIR=%s" % _sh_quote(str(run_dir)),
        "export SHOT_DIR=%s" % _sh_quote(str(shots)),
    ]
    if package:
        lines.append("export PKG=%s" % _sh_quote(package))

    bindings = bindings or []
    if bindings:
        lines += ["",
                  "# Role <-> device. Each ROLE{n} value is the same string as a key in the scenario roles.",
                  "# If the scenario says \"device\": \"B\", find ROLE2==B and use $DEV2.",
                  "export DEV_COUNT=%d" % len(bindings)]
        for n, b in enumerate(bindings, 1):
            note = b.get("note")
            tail = "   # %s" % note if note else ""
            lines.append("export ROLE%d=%s; export DEV%d=%s%s"
                         % (n, _sh_quote(b["role"]), n, _sh_quote(b["serial"]), tail))
        lines += ["", "# Default device for commands that do not use roles", 'export DEV="$DEV1"']
    else:
        # DEV is **always defined.** If empty, it becomes `adb -s ` and dies with a usage error.
        # Devices held by other sessions are excluded — if undecided, leave it empty and point to acquire (#972)
        one = sole_device()
        lines += ["", "# Only one device is free of other sessions, so it is the default"
                      if one else
                      "# No device chosen (devices held by other sessions are left out). Borrow one with"
                      "\n# device acquire --platform ios|android and use DEV=<id>, or bind roles with device bind",
                  "export DEV=%s" % _sh_quote(one or "")]
    lines.append("")
    env.write_text("\n".join(lines), encoding="utf-8")
    return env
