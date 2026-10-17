"""진단 계약: bad_args 원인 (#886) · 루트 해석 (#885) · 호스트 자원 (#883) · 비밀값 오탐 (#882) · 기억 유실 (#863)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

CLI = Path(__file__).resolve().parents[1] / "scripts" / "launch_cli.py"
sys.path.insert(0, str(CLI.parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import knowledge  # noqa: E402
import pro_launch  # noqa: E402,F401  — import 경로 준비
from common.access import find_secrets  # noqa: E402
from pro_launch.runtime import host_resources, output as rt_output  # noqa: E402


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


# ── #886 bad_args 가 무엇이 틀렸는지 말한다 ────────────────────────────────

@pytest.mark.parametrize("argv, wrong, right", [
    (["recall", "--project-root", "/x"], "--project-root", "--root"),
    (["lern", "--area", "web"], "lern", "learn"),
])
def test_bad_args_names_the_wrong_part_and_suggests(argv, wrong, right):
    got = run_cli(*argv)
    assert got["code"] == "bad_args", got
    assert wrong in got["unknown"], got
    assert got["did_you_mean"][wrong] == right, got
    assert right in got["next"], got


# ── #885 레포 밖에서 불려도 루트를 찾는다 ──────────────────────────────────

def test_outside_repo_uses_last_used_root(tmp_path):
    project = _repo(tmp_path)
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    run_cli("recall", cwd=project)
    got = run_cli("get-output-path", cwd=outside)
    assert got["ok"] is True and got["run_dir"].startswith(str(project.resolve())), got
    assert got["root_source"] == "last_used", got


# ── #883 호스트 자원 압박 ────────────────────────────────────────────────

@pytest.mark.parametrize("memory, level", [
    ({"total_mb": 16000, "available_mb": 8000, "swap_total_mb": 4000, "swap_used_mb": 100}, "ok"),
    ({"total_mb": 16000, "available_mb": 8000, "swap_total_mb": 4000, "swap_used_mb": 3200}, "high"),
    ({"total_mb": 16000, "available_mb": 500, "swap_total_mb": 0, "swap_used_mb": 0}, "critical"),
    ({"total_mb": None, "available_mb": None, "swap_total_mb": None, "swap_used_mb": None}, "unknown"),
])
def test_pressure_level(memory, level):
    assert host_resources.pressure_level(memory) == level


# ── #882 낱말이 아니라 값을 막는다 ─────────────────────────────────────────

@pytest.mark.parametrize("text", [
    "fill #account_name_text_field then #password_text_field",
    "token=$GH_TOKEN 으로 부른다",
    "비밀번호 입력란을 누른다",
])
def test_harmless_text_passes(text):
    assert find_secrets(text) == []


@pytest.mark.parametrize("text", [
    '{"password": "abcd"}', "ghp_" + "a" * 36, "-----BEGIN RSA PRIVATE KEY-----",
])
def test_secret_values_fail(text):
    assert find_secrets(text), text


def test_learn_refusal_carries_matched_span(tmp_path):
    got = run_cli("learn", "--area", "web", "--key", "web.login", "--result", "ok",
                  "--how", "login with password=hunter2", "--root", str(_repo(tmp_path)))
    assert got["code"] == "secret_detected" and got["matched_span"] == ["password=***"], got


# ── #863 긴 지식이 사라지지 않는다 ─────────────────────────────────────────

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


def test_session_check_lists_unlearned_resolved_area(tmp_path):
    project = _repo(tmp_path)
    folder = knowledge.store_path("repo", project).parent
    folder.mkdir(parents=True, exist_ok=True)
    (folder / rt_output.RESOLVED_FILE).write_text(json.dumps(
        [{"area": "ios", "fails": 4, "last_code": "tap_failed", "at": time.time()}]), encoding="utf-8")
    got = run_cli("session-check", "--root", str(project))
    assert got["code"] == "learn_candidates" and got["unlearned"][0]["area"] == "ios", got
    run_cli("learn", "--area", "ios", "--key", "ios.tap", "--result", "ok",
            "--how", "app tap 으로 누른다", "--root", str(project))
    assert run_cli("session-check", "--root", str(project))["code"] == "ok"


def test_no_device_stops_boot_advice_under_critical_memory(monkeypatch, capsys):
    # 기기가 없고 메모리 critical 이면 부팅 안내 대신 host_memory_pressure (#883)
    from pro_launch.runtime import devices as runtime_devices
    from pro_launch.runtime import host_resources as resources_module
    monkeypatch.setattr(resources_module, "memory_summary",
                        lambda: {"pressure": "critical", "available_percent": 3, "swap_used_percent": 95})
    empty = {"android": [], "ios_booted": [], "android_avds": ["Pixel"]}
    runtime_devices.no_device_response(empty, None)
    data = json.loads(capsys.readouterr().out)
    assert data["code"] == "host_memory_pressure" and data["action"] == "device boot"
