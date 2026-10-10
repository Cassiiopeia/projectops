"""worktree_cli 복사 세트 기억 계약 (#839).

본다:
1. 처음엔 기억이 없고 모든 후보를 판단 대상으로 준다
2. record 뒤 recall 은 지난 세트를 주고, 새로 생긴 후보만 new_candidates 로 준다
3. 비밀 파일의 **내용은 기억 파일에 절대 남지 않는다** — 경로만
4. 절대경로·`..`·값 같은 입력은 거부한다
5. 원본·워크트리 어디서 불러도 같은 기억을 본다 (repo_key)
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

CLI = Path(__file__).resolve().parents[1] / "scripts" / "worktree_cli.py"
SECRET = "SUPER_SECRET_VALUE_839"


def _run(home: Path, *args, cwd=None) -> dict:
    env = dict(os.environ, HOME=str(home), PROJECTOPS_HOME=str(home / ".projectops"),
               PYTHONIOENCODING="utf-8")
    out = subprocess.run([sys.executable, str(CLI), *args], capture_output=True,
                         text=True, env=env, cwd=cwd, timeout=60)
    assert out.stdout.strip(), out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


def _git(repo: Path, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "proj"
    r.mkdir()
    _git(r, "init", "-q")
    _git(r, "remote", "add", "origin", "https://github.com/acme/proj-839.git")
    (r / ".gitignore").write_text(".env\n*.local\nbuild/\nnode_modules/\n.idea/\nsecrets/\n",
                                  encoding="utf-8")
    (r / ".env").write_text(f"API_KEY={SECRET}\n", encoding="utf-8")
    (r / "app.local").write_text("x", encoding="utf-8")
    (r / "build").mkdir()
    (r / "build" / "out.txt").write_text("x", encoding="utf-8")
    (r / "node_modules").mkdir()
    (r / "node_modules" / "a.js").write_text("x", encoding="utf-8")
    (r / ".idea").mkdir()
    (r / ".idea" / "workspace.xml").write_text("x", encoding="utf-8")
    return r


@pytest.fixture
def home(tmp_path):
    h = tmp_path / "home"
    h.mkdir()
    return h


def test_first_time_lists_candidates_without_caches(repo, home):
    res = _run(home, "recall", "--root", str(repo))
    assert res["ok"] and res["verdict"] == "first_time"
    assert res["candidates"] == [".env", "app.local"]       # build/·node_modules/·.idea/ 제외
    assert res["new_candidates"] == res["candidates"]
    assert "record" in res["next"]


def test_record_then_recall_gives_only_the_diff(repo, home):
    rec = _run(home, "record", "--root", str(repo), "--copied", ".env", "--skipped", "app.local")
    assert rec["ok"], rec
    mem = Path(rec["memory_file"])
    assert mem == home / ".projectops" / "worktree" / "acme__proj-839.json"

    same = _run(home, "recall", "--root", str(repo))
    assert same["verdict"] == "same"
    assert same["copy_now"] == [".env"] and same["new_candidates"] == []
    assert same["last"]["copied"] == [".env"] and same["last"]["skipped"] == ["app.local"]
    assert same["last"]["date"]

    # 새 후보가 생기면 그것만 판단 대상
    (repo / "secrets").mkdir()
    (repo / "secrets" / "key.jks").write_text("k", encoding="utf-8")
    changed = _run(home, "recall", "--root", str(repo))
    assert changed["verdict"] == "changed"
    assert changed["new_candidates"] == ["secrets/"]
    assert changed["copy_now"] == [".env"]

    # 폴더 안 파일을 판단해 기록하면 그 폴더 후보도 판단된 것으로 본다
    _run(home, "record", "--root", str(repo), "--copied", ".env,secrets/key.jks")
    after = _run(home, "recall", "--root", str(repo))
    assert after["new_candidates"] == []
    assert sorted(after["copy_now"]) == [".env", "secrets/key.jks"]
    assert after["last"]["skipped"] == ["app.local"]     # 이번에 다루지 않은 지난 판단은 이어 간다


def test_gone_entries_are_reported_and_dropped(repo, home):
    _run(home, "record", "--root", str(repo), "--copied", ".env,app.local")
    (repo / "app.local").unlink()
    res = _run(home, "recall", "--root", str(repo))
    assert res["gone"] == ["app.local"] and res["copy_now"] == [".env"]
    rec = _run(home, "record", "--root", str(repo), "--copied", ".env")
    assert rec["copied"] == [".env"]


def test_secret_content_is_never_stored(repo, home):
    rec = _run(home, "record", "--root", str(repo), "--copied", ".env")
    text = Path(rec["memory_file"]).read_text(encoding="utf-8")
    assert SECRET not in text
    assert set(json.loads(text)) == {"schema", "copied", "skipped", "date", "runs"}


@pytest.mark.parametrize("bad", [
    "/etc/passwd", "../outside/.env", f"API_KEY={SECRET}", "C:\\Users\\x\\.env",
])
def test_rejects_non_relative_or_value_like_input(repo, home, bad):
    res = _run(home, "record", "--root", str(repo), "--copied", bad)
    assert not res["ok"] and res["code"] == "bad_path"
    assert not (home / ".projectops" / "worktree").exists()
    assert SECRET not in json.dumps(res, ensure_ascii=False)   # 거부 응답에도 값을 되돌려 주지 않는다


def test_empty_record_is_an_error(repo, home):
    res = _run(home, "record", "--root", str(repo))
    assert not res["ok"] and res["code"] == "empty"


def test_same_memory_from_subfolder(repo, home):
    """경로가 아니라 remote 로 키를 잡으므로 하위 폴더·워크트리에서 불러도 같은 기억이다."""
    _run(home, "record", "--root", str(repo), "--copied", ".env")
    sub = repo / "src"
    sub.mkdir()
    res = _run(home, "recall", "--root", str(sub))
    assert res["copy_now"] == [".env"]


def test_same_day_records_do_not_inflate_runs(repo, home):
    _run(home, "record", "--root", str(repo), "--copied", ".env")
    _run(home, "record", "--root", str(repo), "--copied", ".env")
    res = _run(home, "recall", "--root", str(repo))
    assert res["last"]["runs"] == 1


def test_bad_args_are_json(home):
    res = _run(home, "nope")
    assert not res["ok"] and res["code"] == "bad_args"


def test_unignored_folder_is_not_listed_only_its_ignored_file(repo, home):
    """`--directory` 가 섞어 내는 '무시되지 않은 폴더' 는 후보가 아니다 — 안의 무시된 파일만 후보다."""
    (repo / ".gitignore").write_text(".env\n*.local\nconf/*.lock\n", encoding="utf-8")
    (repo / "conf").mkdir()
    (repo / "conf" / "run.lock").write_text("x", encoding="utf-8")
    res = _run(home, "recall", "--root", str(repo))
    assert "conf/" not in res["candidates"]
    assert "conf/run.lock" in res["candidates"]
