"""진단 계약: bad_args 원인 (#886) · 루트 해석 (#885) · 호스트 자원 (#883) · 비밀값 오탐 (#882) · 기억 유실 (#863)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

CLI = Path(__file__).resolve().parents[1] / "scripts" / "launch_cli.py"


def run_cli(*args, cwd: Path | None = None, env_extra: dict | None = None) -> dict:
    env = {k: v for k, v in os.environ.items() if k != "PROJECT_ROOT"}
    env.update(PYTHONIOENCODING="utf-8", **(env_extra or {}))
    result = subprocess.run([sys.executable, str(CLI), *args], capture_output=True, text=True,
                            encoding="utf-8", env=env, cwd=str(cwd) if cwd else None)
    return json.loads(result.stdout)


def _repo(tmp_path: Path, name: str = "proj") -> Path:
    folder = tmp_path / name
    folder.mkdir()
    subprocess.run(["git", "init", "-q", str(folder)], check=True)
    subprocess.run(["git", "-C", str(folder), "remote", "add", "origin",
                    f"https://github.com/acme/{name}.git"], check=True)
    return folder


def test_detail_note_is_saved_and_recall_match_finds_it(tmp_path):
    project = _repo(tmp_path)
    run_cli("learn", "--area", "android", "--key", "android.gesture", "--result", "ok",
            "--how", "app swipe 로 민다. 먼저 화면을 찍어 y 를 정한다",
            "--detail", "광고 배너 때문에 줄 y 가 87% 에서 80% 로 바뀌었다. swipe 전에 app shot", "--root", str(project))
    got = run_cli("recall", "--match", "배너", "--root", str(project))
    assert [e["key"] for e in got["entries"]] == ["android.gesture"], got
    note = Path(got["entries"][0]["detail_path"])
    assert note.is_file() and "광고 배너" in note.read_text(encoding="utf-8")
    assert run_cli("recall", "--match", "nothing-like-this", "--root", str(project))["code"] == "empty"
