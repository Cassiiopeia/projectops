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


def _call(capsys, *argv) -> dict:
    """같은 프로세스에서 CLI 를 부르고 JSON 하나를 읽는다 (프로세스·홈 가짜를 쓰려고)."""
    launch_cli.main(list(argv))
    return json.loads(capsys.readouterr().out)


def _age(path: Path, days: float) -> None:
    """폴더와 바로 아래 항목의 수정 시각을 과거로 (tidy 는 이 둘로 최근 사용을 잰다)."""
    stamp = time.time() - days * 86400
    for target in (*path.iterdir(), path):
        os.utime(target, (stamp, stamp))


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


def test_stale_table_marks_known_keys_and_deletes_leaks(tmp_path):
    store = tmp_path / "k.json"
    knowledge.learn(store, "web", "web.file_upload_cdp", "업로드 직접", "ok")
    knowledge.learn(store, "server", "server.zz-verify.os", "OS Linux", "ok")
    done = knowledge_stale.apply_stale_table(store)
    assert {d["action"] for d in done} == {"supersede", "delete"}
    keys = {e["key"]: e for e in knowledge.load(store)}
    assert "server.zz-verify.os" not in keys
    assert keys["web.file_upload_cdp"]["superseded_by"] == "feature:web upload"

