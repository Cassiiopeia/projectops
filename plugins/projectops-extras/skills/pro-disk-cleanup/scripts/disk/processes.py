"""In-use check (3 ways per OS): macOS/Linux cwd and command line / Linux /proc without lsof / Windows rename test"""
from __future__ import annotations

import os
from pathlib import Path

from . import shell

SELF_MARKER = "disk_cli.py"
# Temporary name suffix for the Windows test
RENAME_PROBE_SUFFIX = ".disk-cleanup-probe"


class ProcessSnapshot:
    """Check many paths against one process snapshot (no lsof rerun per path)"""

    def __init__(self):
        self.working_folders: list[str] = []
        self.command_lines: list[str] = []
        self.method = "rename_probe" if shell.IS_WINDOWS else "process_list"
        # Windows: rename test per path instead of a process list (open folders can't be renamed)
        self.is_supported = True
        if not shell.IS_WINDOWS:
            self._capture()

    def _capture(self):
        if shell.has_command("lsof"):
            _, out, _ = shell.run(["lsof", "-d", "cwd", "-Fn"], timeout_seconds=60)
            self.working_folders = [line[1:] for line in out.splitlines() if line.startswith("n/")]
        elif Path("/proc").is_dir():
            self.working_folders = _linux_process_working_folders()
        # BSD format without dashes: works on macOS and Linux procps
        _, out, _ = shell.run(["ps", "axww", "-o", "command="], timeout_seconds=30)
        # Exclude this CLI and the shell that called it, since they hold the paths as arguments
        self.command_lines = [line for line in out.splitlines() if line.strip() and SELF_MARKER not in line]

    def users_of(self, path: Path) -> list[str]:
        """Hints of processes using the path (empty list = unused)"""
        if shell.IS_WINDOWS:
            return _rename_probe(path)
        prefix = str(path.resolve())
        hits = [f"cwd {folder}" for folder in self.working_folders
                if folder == prefix or folder.startswith(prefix + os.sep)]
        hits += [f"command {line[:160]}" for line in self.command_lines if prefix in line]
        return hits[:5]

    def is_running(self, *names: str) -> list[str]:
        """Processes whose command line contains the name (xcodebuild, gradle, etc.). Windows uses tasklist"""
        if shell.IS_WINDOWS and not self.command_lines:
            _, out, _ = shell.run(["tasklist", "/fo", "csv", "/nh"], timeout_seconds=30)
            self.command_lines = [line.split(",")[0].strip('"') for line in out.splitlines() if line.strip()]
        lowered = [name.lower() for name in names]
        return [line[:160] for line in self.command_lines if any(name in line.lower() for name in lowered)][:5]


def _linux_process_working_folders() -> list[str]:
    folders = []
    for entry in os.listdir("/proc"):
        if entry.isdigit():
            try:
                folders.append(os.readlink(f"/proc/{entry}/cwd"))
            except OSError:
                continue  # another user's process or already exited
    return folders


def _rename_probe(path: Path) -> list[str]:
    # Rename > restore immediately. Windows refuses if files are open or it is a cwd > in use
    if not path.exists():
        return []
    probe = path.with_name(path.name + RENAME_PROBE_SUFFIX)
    if probe.exists():
        return [f"probe name already exists: {probe}"]
    try:
        os.rename(path, probe)
    except PermissionError as error:
        return [f"locked: {error.strerror or error}"]
    except OSError as error:
        return [f"rename probe failed: {error}"]
    try:
        os.rename(probe, path)
    except OSError as error:
        return [f"PROBE NOT RESTORED, rename {probe} back to {path.name}: {error}"]
    return []
