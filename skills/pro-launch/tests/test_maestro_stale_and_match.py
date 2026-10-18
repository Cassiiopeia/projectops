"""iOS Maestro 잔여 드라이버 · 부하 · 시작 잠금 (#922) · 라벨 매칭 (#927). 기기 없이 돈다."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import maestro_drivers  # noqa: E402
import maestro_runs  # noqa: E402
import node_match  # noqa: E402
from pro_launch.commands.app import gestures  # noqa: E402
from pro_launch.runtime import host_resources  # noqa: E402

UDID = "3F328F1A-16D1-453B-A0D3-94CDC21C4189"
DRIVER = (f"/usr/bin/xcodebuild test-without-building -xctestrun /x/maestro-driver-ios-config.xctestrun "
          f"-destination id={UDID}")


def _node(text="", desc="", id_=""):
    return {"text": text, "desc": desc, "id": id_, "clickable": True, "bounds": [0, 0, 10, 10], "center": [5, 5]}


# ── #927 매칭 ───────────────────────────────────────────────────────────

def test_doubled_flutter_label_matches_single_text():
    nodes = [_node(text="GitHub로 계속하기\nGitHub로 계속하기")]
    found, by, kind = node_match.find_nodes(nodes, "text", "GitHub로 계속하기")
    assert found == nodes and by == "text" and kind == "normalized"


def test_text_miss_falls_back_to_desc_and_names_the_field():
    found, by, _ = node_match.find_nodes([_node(desc="홈")], "text", "홈")
    assert found and by == "desc"


def test_invisible_marks_and_desc_lines_match():
    assert node_match.match_nodes([_node(text="‎로그인 ")], "text", "로그인")
    assert node_match.match_nodes([_node(desc="카카오로 계속하기\n다른 줄")], "desc", "다른 줄")


def test_exact_beats_partial_and_short_id_still_works():
    nodes = [_node(text="로그인 없이 둘러보기"), _node(text="로그인", id_="pkg:id/login")]
    assert [n["text"] for n in node_match.match_nodes(nodes, "text", "로그인")] == ["로그인"]
    assert node_match.match_nodes(nodes, "id", "login")[0]["text"] == "로그인"


def test_did_you_mean_points_at_the_field_that_has_it():
    assert node_match.did_you_mean([_node(desc="홈 탭")], "홈") == "--desc '홈 탭'"
    assert node_match.did_you_mean([_node(text="zzz")], "홈") is None


# ── #922 드라이버 가르기 ────────────────────────────────────────────────

def _proc(pid, ppid, command, age=600):
    return {"pid": pid, "ppid": ppid, "age_seconds": age, "command": command}


def test_parent_gone_driver_is_orphan_and_session_child_is_not():
    processes = [_proc(100, 1, DRIVER), _proc(200, 150, DRIVER), _proc(150, 1, "python relay"),
                 _proc(300, 4242, DRIVER)]
    drivers = {d["pid"]: d for d in maestro_drivers.classify(processes, relay_pids={150}, own_pid=-1)}
    assert drivers[100]["owner"] == "orphan" and drivers[200]["owner"] == "session"
    assert drivers[300]["owner"] == "active"          # 부른 쪽이 살아 있으면 보고만


def test_auto_clean_is_conservative():
    old = {"owner": "orphan", "kind": maestro_drivers.KIND_XCODEBUILD_DRIVER, "udid": UDID, "age_seconds": 600}
    assert maestro_drivers.is_auto_cleanable(old, UDID)
    assert not maestro_drivers.is_auto_cleanable({**old, "udid": "OTHER"}, UDID)
    assert not maestro_drivers.is_auto_cleanable({**old, "udid": None}, UDID)
    assert not maestro_drivers.is_auto_cleanable({**old, "age_seconds": 5}, UDID)
    assert not maestro_drivers.is_auto_cleanable({**old, "owner": "active"}, UDID)


def test_failure_fields_list_stale_with_pid_kind_age(monkeypatch):
    monkeypatch.setattr(maestro_drivers, "list_processes", lambda: [_proc(100, 1, DRIVER, 77)])
    monkeypatch.setattr(maestro_drivers, "live_session_relay_pids", lambda: set())
    fields = maestro_drivers.failure_fields(UDID)
    assert fields["stale_maestro_drivers"] == [{"pid": 100, "kind": "xcodebuild_driver", "age_seconds": 77}]


def test_parse_elapsed():
    assert maestro_drivers.parse_elapsed("01:30") == 90
    assert maestro_drivers.parse_elapsed("2-01:00:05") == 2 * 86400 + 3605


# ── #922 부하 · 마지막 오류 · 잠금 ───────────────────────────────────────

def test_overloaded_host_raises_driver_startup_timeout_but_respects_user_value(monkeypatch):
    monkeypatch.setattr(host_resources, "read_load", lambda: {"load_1m": 90.0, "load_5m": 50.0, "load_15m": 1.0,
                                                              "cpu_count": 12, "is_overloaded": True})
    gestures.prepare_ios_maestro(UDID)
    assert os.environ[gestures.DRIVER_STARTUP_TIMEOUT_ENV] == "180000"
    monkeypatch.setenv(gestures.DRIVER_STARTUP_TIMEOUT_ENV, "5000")
    gestures.prepare_ios_maestro(UDID)
    assert os.environ[gestures.DRIVER_STARTUP_TIMEOUT_ENV] == "5000"


def test_load_overload_threshold_is_twice_the_cores(monkeypatch):
    monkeypatch.setattr(host_resources.os, "cpu_count", lambda: 4)
    monkeypatch.setattr(host_resources.os, "getloadavg", lambda: (8.5, 1.0, 1.0))
    assert host_resources.read_load()["is_overloaded"] is True
    monkeypatch.setattr(host_resources.os, "getloadavg", lambda: (7.9, 1.0, 1.0))
    assert host_resources.read_load()["is_overloaded"] is False


def test_last_error_line_comes_from_own_run_log_and_skips_input_text(tmp_path, monkeypatch):
    home = tmp_path / "home"
    folder = home / ".maestro" / "tests" / time.strftime(maestro_runs.FOLDER_NAME_FORMAT)
    folder.mkdir(parents=True)
    (folder / "maestro.log").write_text(
        "10:53:18.395 [ INFO] start\n"
        "10:53:19.000 [ERROR] java.net.ConnectException: Failed to connect to /127.0.0.1:6218\n"
        "10:53:20.000 [ INFO] InputText Exception secret\n", encoding="utf-8")
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    monkeypatch.setattr(maestro_runs, "LAST_RUN", {"started_at": time.time() - 2, "ended_at": time.time()})
    assert maestro_runs.last_error_line() == "java.net.ConnectException: Failed to connect to /127.0.0.1:6218"


def test_start_lock_waits_for_live_holder_and_reports(monkeypatch):
    monkeypatch.setattr(maestro_runs, "LOCK_POLL_SECONDS", 0.05)
    monkeypatch.setattr(maestro_runs, "LOCK_WAIT", {"waited_seconds": 0.0, "holder_pid": None, "is_timed_out": False})
    path = maestro_runs.lock_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    holder = os.getppid()                              # 살아 있는 다른 프로세스
    path.write_text(json.dumps({"pid": holder, "acquired_at": time.time()}))
    with maestro_runs.start_lock(wait_seconds=0.3):
        pass
    report = maestro_runs.lock_wait_report()["maestro_lock"]
    assert report["waited_seconds"] >= 0.2 and report["holder_pid"] == holder and report["is_timed_out"]


def test_start_lock_takes_over_dead_holder_and_releases():
    path = maestro_runs.lock_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"pid": 2**22 + 12345, "acquired_at": time.time()}))
    with maestro_runs.start_lock(wait_seconds=0.2):
        assert json.loads(path.read_text())["pid"] == os.getpid()
    assert not path.exists()
