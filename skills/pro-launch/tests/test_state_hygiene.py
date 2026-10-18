"""상태 위생 (#932 · #931): 임시 버킷 · tidy · 대체 표시 · unknown_fields · 별칭 · 최근 실행 폴더 · package_changed."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import knowledge  # noqa: E402
import knowledge_stale  # noqa: E402
import launch_cli  # noqa: E402
from common import state as common_state  # noqa: E402
from test_launch_cli import _repo  # noqa: E402


def _call(capsys, *argv) -> dict:
    """같은 프로세스에서 CLI 를 부르고 JSON 하나를 읽는다 (프로세스·홈 가짜를 쓰려고)."""
    launch_cli.main(list(argv))
    return json.loads(capsys.readouterr().out)


def _age(path: Path, days: float) -> None:
    """폴더와 바로 아래 항목의 수정 시각을 과거로 (tidy 는 이 둘로 최근 사용을 잰다)."""
    stamp = time.time() - days * 86400
    for target in (*path.iterdir(), path):
        os.utime(target, (stamp, stamp))


# ── 임시 폴더 버킷 ────────────────────────────────────────────────────────

def test_non_git_folder_gets_hashed_scratch_bucket(tmp_path):
    first, second = tmp_path / "a" / "tmp", tmp_path / "b" / "tmp"
    first.mkdir(parents=True)
    second.mkdir(parents=True)
    bucket_first = common_state.state_dir("launch", first)
    assert bucket_first.parent.name == "_scratch" and bucket_first.name.startswith("tmp-")
    assert bucket_first != common_state.state_dir("launch", second)   # 같은 이름이어도 갈린다


def test_real_repo_and_marker_folder_keep_their_keys(tmp_path):
    assert common_state.state_dir("launch", _repo(tmp_path)).name == "acme__thing"
    local = _repo(tmp_path, "localonly", remote=None)
    assert common_state.state_dir("launch", local).name == "localonly"
    plain = tmp_path / "plainapp"
    plain.mkdir()
    (plain / "package.json").write_text("{}", encoding="utf-8")
    assert common_state.state_dir("launch", plain).name == "plainapp"


def test_scratch_root_is_not_remembered(tmp_path):
    from pro_launch.runtime import context, recent_roots
    scratch = tmp_path / "scratchdir"
    scratch.mkdir()
    _, marks = context._resolve_root(str(scratch))
    assert marks.get("scratch") is True
    assert recent_roots.load_recent_roots() == []
    assert not recent_roots.recent_roots_path().exists()


# ── tidy ──────────────────────────────────────────────────────────────────

@pytest.fixture
def tidy_env(tmp_path, monkeypatch):
    import maestro_runs
    from pro_launch.commands import tidy
    home = Path(os.environ["PROJECTOPS_HOME"])
    tests_dir = tmp_path / "maestro_tests"
    for name, age in (("old", 30), ("new", 0)):
        folder = tests_dir / name
        folder.mkdir(parents=True)
        (folder / "maestro.log").write_text("x" * 100, encoding="utf-8")
        _age(folder, age)
    monkeypatch.setattr(maestro_runs, "maestro_tests_folder", lambda: tests_dir)
    # 프로세스 목록은 비어 있지 않은 가짜 — 아무 프로필도 안 쓴다
    monkeypatch.setattr(tidy, "process_command_lines", lambda: "unrelated process")
    fake = home / "launch" / "root"
    (fake / ".browser-profile").mkdir(parents=True)
    (fake / ".browser-profile" / "f").write_text("p", encoding="utf-8")
    _age(fake, 20)
    kept = home / "launch" / "tools"      # 데이터 파일이 있는 가짜 이름은 남긴다
    kept.mkdir(parents=True)
    (kept / "access.json").write_text("{}", encoding="utf-8")
    _age(kept, 20)
    real = home / "launch" / "acme__thing"
    real.mkdir(parents=True)
    (real / "devices.json").write_text("{}", encoding="utf-8")
    _age(real, 20)
    return tests_dir, fake, kept, real


def test_tidy_default_is_report_only(tidy_env, capsys):
    tests_dir, fake, _, _ = tidy_env
    result = _call(capsys, "tidy", "--buckets")
    assert result["mode"] == "dry" and fake.exists() and (tests_dir / "old").exists()
    by_name = {row["name"]: row for row in result["buckets"]}
    assert by_name["root"]["action"] == "delete_bucket" and by_name["root"]["classification"] == "fake"
    assert by_name["tools"]["action"].startswith("keep")
    assert by_name["acme__thing"]["classification"] == "real"
    assert result["maestro_tests"]["count"] == 2 and result["maestro_tests"]["old_count"] == 1


def test_tidy_apply_removes_only_idle_junk(tidy_env, capsys):
    tests_dir, fake, kept, real = tidy_env
    result = _call(capsys, "tidy", "--buckets", "--apply", "--days", "7")
    assert result["mode"] == "apply"
    assert not fake.exists() and not (tests_dir / "old").exists()
    assert (tests_dir / "new").exists() and kept.exists() and real.exists()


def test_tidy_never_deletes_profile_in_use(tidy_env, monkeypatch, capsys):
    from pro_launch.commands import tidy
    _, fake, _, _ = tidy_env
    monkeypatch.setattr(tidy, "process_command_lines",
                        lambda: f"chrome --user-data-dir={fake / '.browser-profile'}")
    _call(capsys, "tidy", "--buckets", "--apply", "--days", "7")
    assert fake.exists()


def test_tidy_apply_keeps_real_repo_profile(tidy_env, capsys):
    """실제 레포(owner__repo)의 프로필은 오래 안 써도 지우지 않고 보고만 한다."""
    home = Path(os.environ["PROJECTOPS_HOME"])
    real = home / "launch" / "acme__widget"
    (real / ".browser-profile").mkdir(parents=True)
    (real / ".browser-profile" / "Cookies").write_text("login", encoding="utf-8")
    _age(real, 60)
    result = _call(capsys, "tidy", "--buckets", "--apply", "--days", "7")
    row = next(r for r in result["buckets"] if r["name"] == "acme__widget")
    assert row["action"] == "keep:real_repo_profile" and row["profile_mb"] is not None
    assert (real / ".browser-profile" / "Cookies").exists()


def test_tidy_default_stays_knowledge_consolidation(tidy_env, capsys):
    result = _call(capsys, "tidy")
    assert "moved_to_machine" in result and "buckets" not in result
    assert _call(capsys, "tidy", "--apply")["code"] == "bad_args"


# ── 대체 표시 ─────────────────────────────────────────────────────────────

def test_superseded_entry_is_ranked_last_and_not_surfaced(tmp_path):
    store = tmp_path / "k.json"
    knowledge.learn(store, "web", "web.old", "옛 방법", "ok", today="2026-10-18")
    knowledge.learn(store, "web", "web.new", "새 방법", "ok", today="2026-10-18")
    knowledge.learn(store, "web", "web.new", "새 방법", "ok", today="2026-10-18")
    assert knowledge_stale.mark_superseded(store, "web.old", "kb:web-x") == 1
    rows = knowledge.recall({"machine": store}, "web", today="2026-10-18")
    assert [r["key"] for r in rows] == ["web.new", "web.old"]
    assert rows[1]["superseded_by"] == "kb:web-x" and rows[1]["verify"] is True
    shown = knowledge.surface({"machine": store}, "web", tmp_path / "seen.json", today="2026-10-18")
    assert [r["key"] for r in shown] == ["web.new"]


def test_stale_table_marks_known_keys_and_deletes_leaks(tmp_path):
    store = tmp_path / "k.json"
    knowledge.learn(store, "web", "web.file_upload_cdp", "업로드 직접", "ok")
    knowledge.learn(store, "server", "server.zz-verify.os", "OS Linux", "ok")
    done = knowledge_stale.apply_stale_table(store)
    assert {d["action"] for d in done} == {"supersede", "delete"}
    keys = {e["key"]: e for e in knowledge.load(store)}
    assert "server.zz-verify.os" not in keys
    assert keys["web.file_upload_cdp"]["superseded_by"] == "feature:web upload"


def test_learn_stores_plugin_version(tmp_path):
    from pro_launch.runtime.plugin_version import plugin_version
    entry = knowledge.learn(tmp_path / "k.json", "web", "web.k", "방법", "ok")["entry"]
    assert entry["plugin_version"] == plugin_version()


# ── CLI 계약 ──────────────────────────────────────────────────────────────

def test_unknown_fields_are_reported(capsys):
    result = _call(capsys, "cred", "list", "--fields", "items")
    assert result["unknown_fields"] == ["items"] and "credentials" in result["available_fields"]


def test_recall_platform_is_alias_of_area(capsys):
    assert _call(capsys, "recall", "--platform", "ios")["ok"] is True


def test_cred_show_accepts_positional_name(capsys):
    result = _call(capsys, "cred", "show", "nope-name")
    assert result["code"] != "bad_args" and "invalid choice" not in json.dumps(result)


# ── 최근 실행 폴더 · package_changed ──────────────────────────────────────

def test_shot_folder_follows_last_run_when_shot_dir_unset(tmp_path, monkeypatch):
    from pro_launch.runtime import shots
    monkeypatch.delenv("SHOT_DIR", raising=False)
    root = _repo(tmp_path)
    assert shots.shot_dir_source(root) == "state"
    run_dir = tmp_path / "run"
    (run_dir / "screenshots").mkdir(parents=True)
    shots.record_last_run(root, run_dir, run_dir / "screenshots")
    assert shots.shot_dir_source(root) == "last_run"
    assert shots.shot_folder(root) == run_dir / "screenshots"
    monkeypatch.setenv("SHOT_DIR", str(tmp_path / "env"))
    assert shots.shot_dir_source(root) == "env"


def test_output_path_prefers_detected_package(tmp_path):
    from pro_launch.commands import output_path
    root = _repo(tmp_path, "app")
    (root / "pubspec.yaml").write_text("flutter:\n", encoding="utf-8")
    build = root / "android" / "app"
    build.mkdir(parents=True)
    (build / "build.gradle.kts").write_text('applicationId = "com.new.app"\n', encoding="utf-8")
    assert output_path._resolve_package(None, "kr.old.app", root) == ("com.new.app", "kr.old.app -> com.new.app")
    assert output_path._resolve_package("explicit", "kr.old.app", root) == ("explicit", None)
