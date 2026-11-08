"""사용 중 판정: 실행 중 프로세스의 현재 폴더·명령줄에 경로가 있는지"""
from __future__ import annotations

from pathlib import Path

from . import shell

SELF_MARKER = "disk_cli.py"


class ProcessSnapshot:
    """한 번 찍은 프로세스 목록으로 여러 경로를 판정 (경로마다 lsof 를 다시 돌리지 않음)"""

    def __init__(self):
        self.working_folders: list[str] = []
        self.command_lines: list[str] = []
        # Windows: 표준 라이브러리로 프로세스 현재 폴더를 못 읽음 > 판정 불가(None)
        self.is_supported = not shell.IS_WINDOWS
        if self.is_supported:
            self._capture()

    def _capture(self):
        if shell.has_command("lsof"):
            _, out, _ = shell.run(["lsof", "-d", "cwd", "-Fn"], timeout_seconds=60)
            self.working_folders = [line[1:] for line in out.splitlines() if line.startswith("n/")]
        _, out, _ = shell.run(["ps", "-axww", "-o", "command="], timeout_seconds=30)
        # 이 CLI 자신과 그것을 부른 셸은 경로를 인자로 들고 있으므로 제외
        self.command_lines = [line for line in out.splitlines()
                              if line.strip() and SELF_MARKER not in line]

    def users_of(self, path: Path) -> list[str] | None:
        """경로를 쓰는 프로세스 단서 목록 (빈 목록 = 안 씀, None = 판정 불가)"""
        if not self.is_supported:
            return None
        prefix = str(path.resolve())
        hits = [f"cwd {folder}" for folder in self.working_folders
                if folder == prefix or folder.startswith(prefix + "/")]
        hits += [f"command {line[:160]}" for line in self.command_lines if prefix in line]
        return hits[:5]

    def is_running(self, *names: str) -> list[str]:
        """이름이 명령줄에 든 프로세스 (xcodebuild·gradle·docker 빌드 등)"""
        lowered = [name.lower() for name in names]
        return [line[:160] for line in self.command_lines if any(name in line.lower() for name in lowered)][:5]
