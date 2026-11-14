"""`get-output-path` — this run's output location and env.sh."""
from __future__ import annotations

import os
from pathlib import Path

from pro_launch.registry import Command
from pro_launch.runtime.app_identity import detected_app_package
from pro_launch.runtime.context import project_root
from pro_launch.runtime.devices import load_devices, save_devices
from pro_launch.runtime.envfile import write_env_sh
from pro_launch.runtime.output import out
from pro_launch.runtime.shots import record_last_run


def cmd_output_path(args) -> int:
    """Create and report this run's output location.

    A calling task skill that wants output in its own folder passes its id with --skill
    (ui-design uses --skill ui-design). **Only skills that produce evidence are accepted** — captures piled into a docs
    skill folder have no tracking exclusion and get committed to the repo.
    """
    try:
        from common.paths import EVIDENCE_SKILLS, resolve_output_path
    except ImportError:
        return out({"ok": False, "code": "common_not_found",
                    "error": "scripts/common/paths.py not found",
                    "hint": "Check that the projectops installation is complete"})
    # Compute the location from the repo --root points at. A missing path is not silently ignored (#713)
    if args.root and args.root != ".":
        root_dir = Path(args.root).expanduser()
        if not root_dir.is_dir():
            return out({"ok": False, "code": "not_found",
                        "error": f"--root path does not exist: {root_dir}"})
        os.chdir(root_dir)
    else:
        # Even when called outside a repo, place it under $PROJECT_ROOT or the recently used root (#885) — otherwise git_not_found
        resolved = project_root(args)
        if resolved.is_dir() and resolved != Path.cwd().resolve():
            os.chdir(resolved)
    skill = args.skill or "launch"
    if skill not in EVIDENCE_SKILLS:
        return out({"ok": False, "code": "not_evidence_skill",
                    "error": f"'{skill}' is not registered as an evidence skill",
                    "hint": ("Add it to EVIDENCE_SKILLS in scripts/common/paths.py so the folder gets "
                             "a tracking exclusion. Registered: " + ", ".join(sorted(EVIDENCE_SKILLS)))})

    r = resolve_output_path(skill, args.title)
    if r.get("ok") is False:
        return out(r)
    md = Path(r["path"])        # <umbrella>/<skill>/{date}_{number}_{title}.md
    run_dir = md.parent / md.stem
    try:
        run_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return out({"ok": False, "code": "mkdir_failed", "error": str(e)})

    root = project_root(args)
    known = load_devices(root)
    package, package_changed = _resolve_package(args.package, known["package"], root)
    if package and package != known["package"]:
        save_devices(root, package, known["bindings"])
    env = write_env_sh(run_dir, package, known["bindings"], skill=skill)
    # So captures from Bash calls that did not source env.sh also land in this run folder (#931)
    record_last_run(root, run_dir, run_dir / "screenshots")
    state = r.get("gitignore")
    return out({
        "skill": skill, "run": md.stem, "run_dir": str(run_dir),
        "screenshots": str(run_dir / "screenshots"), "env_file": str(env),
        "output_root": r.get("output_root"), "gitignore": state,
        "mismatch": r.get("mismatch"), "package": package,
        **({"package_changed": package_changed} if package_changed else {}),
        "summary": f"Output location {run_dir} (git exclusion {state})",
        "next": f'source "{env}" to load SHOT_DIR. Put all captures and evidence under it',
    })


def _resolve_package(given: str | None, stored: str | None, root: Path) -> tuple[str | None, str | None]:
    """App package: --package > project files (applicationId, bundle id) > value saved in devices.json.

    If the saved value differs from the project files, the project files win — env.sh was once written with an old package (#931).
    > (package, "old -> new" if changed)
    """
    if given:
        return given, None
    detected = detected_app_package(root)
    if detected and stored and detected != stored:
        return detected, f"{stored} -> {detected}"
    return stored or detected, None


def configure_get_output_path(p) -> None:
    p.add_argument("--skill", default=None,
                   help="Skill id to get a location for (default launch). Evidence skills only")
    p.add_argument("--title", default=None, help="Title. Defaults to one derived from the worktree path or branch name")
    p.add_argument("--package", default=None, help="App package name — written to env.sh as PKG")
    p.add_argument("--root", default=".")


COMMANDS = [
    Command(name="get-output-path", help="Output location for this run + env.sh", run=cmd_output_path,
            configure=configure_get_output_path),
]
