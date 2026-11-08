"""사용 중 판정 (OS별 3방식): macOS·Linux 현재 폴더·명령줄 / Linux lsof 없으면 /proc / Windows 이름 바꾸기 시험"""
from __future__ import annotations

import os
from pathlib import Path

from . import shell

SELF_MARKER = "disk_cli.py"
# Windows 시험용 임시 이름 접미사
RENAME_PROBE_SUFFIX = ".disk-cleanup-probe"


class ProcessSnapshot:
    """한 번 찍은 프로세스 목록으로 여러 경로를 판정 (경로마다 lsof 를 다시 돌리지 않음)"""

    def __init__(self):
        self.working_folders: list[str] = []
        self.command_lines: list[str] = []
        self.method = "rename_probe" if shell.IS_WINDOWS else "process_list"
        # Windows 는 프로세스 목록 대신 경로마다 이름 바꾸기 시험 (열린 폴더는 바뀌지 않음)
        self.is_supported = True
        if not shell.IS_WINDOWS:
            self._capture()

    def _capture(self):
        if shell.has_command("lsof"):
            _, out, _ = shell.run(["lsof", "-d", "cwd", "-Fn"], timeout_seconds=60)
            self.working_folders = [line[1:] for line in out.splitlines() if line.startswith("n/")]
        elif Path("/proc").is_dir():
            self.working_folders = _linux_process_working_folders()
        # 대시 없는 BSD 형식: macOS·Linux procps 공통
        _, out, _ = shell.run(["ps", "axww", "-o", "command="], timeout_seconds=30)
        # 이 CLI 자신과 그것을 부른 셸은 경로를 인자로 들고 있으므로 제외
        self.command_lines = [line for line in out.splitlines() if line.strip() and SELF_MARKER not in line]

    def users_of(self, path: Path) -> list[str]:
        """경로를 쓰는 프로세스 단서 목록 (빈 목록 = 안 씀)"""
        if shell.IS_WINDOWS:
            return _rename_probe(path)
        prefix = str(path.resolve())
        hits = [f"cwd {folder}" for folder in self.working_folders
                if folder == prefix or folder.startswith(prefix + os.sep)]
        hits += [f"command {line[:160]}" for line in self.command_lines if prefix in line]
        return hits[:5]

    def is_running(self, *names: str) -> list[str]:
        """이름이 명령줄에 든 프로세스 (xcodebuild·gradle 등). Windows 는 tasklist"""
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
                continue  # 다른 사용자 프로세스·이미 종료
    return folders


def _rename_probe(path: Path) -> list[str]:
    # 이름 바꾸기 > 즉시 원복. 열린 파일·현재 폴더 있으면 Windows 거절 > 사용 중
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
