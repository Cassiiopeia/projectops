"""#836 — 레포를 알 수 없는 폴더 · 상태 루트 격리 · docstring · access 성적.

지키려는 것:
  · 스킬·플러그인 캐시 폴더(원격 없음)에서 불려도 `scripts` 같은 가짜 버킷이 생기지 않는다
  · 정상 레포는 예전과 같은 자리에 쓴다
  · PROJECTOPS_HOME 이 상태 루트를 정한다 — 테스트가 실제 홈에 쓰지 않는다
  · 적어 둔 접속 방법이 먹혔는지 도구가 직접 기록하고, 실패가 앞서면 verify 로 알린다
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_launch_cli import _j, _repo, run_cli  # noqa: E402
import launch_cli  # noqa: E402
from common import access as common_access  # noqa: E402
from common import state as common_state  # noqa: E402


def _fake_skill_dir(tmp_path: Path, kind: str = "skills") -> Path:
    """원격 없는 플러그인 캐시를 흉내 낸다 — 이 체크아웃은 원격이 있어 그대로 쓸 수 없다."""
    if kind == "skills":
        d = tmp_path / "cache" / "skills" / "pro-launch" / "scripts"
    else:
        d = tmp_path / ".claude" / "plugins" / "cache" / "projectops" / "scripts"
    d.mkdir(parents=True)
    return d


# ── 상태 루트 ────────────────────────────────────────────────────────────

def test_base_dir_prefers_projectops_home(tmp_path, monkeypatch):
    monkeypatch.setenv("PROJECTOPS_HOME", str(tmp_path / "ph"))
    assert common_state.base_dir() == tmp_path / "ph"
    monkeypatch.delenv("PROJECTOPS_HOME")
    assert common_state.base_dir() == Path.home() / ".projectops"


def test_venv_installed_in_real_home_is_still_found(tmp_path, monkeypatch):
    """상태만 옮긴 것이다 — 이미 받아 둔 Playwright(약 100MB)를 다시 받게 하면 안 된다."""
    if os.name == "nt":
        pytest.skip("POSIX venv 구조만 본다")
    real = tmp_path / "realhome"
    monkeypatch.setenv("HOME", str(real))
    monkeypatch.setenv("PROJECTOPS_HOME", str(tmp_path / "isolated"))
    assert common_state.venv_dir() == tmp_path / "isolated" / "launch" / ".venv"   # 없으면 새 자리
    exe = real / ".projectops" / "launch" / ".venv" / "bin"
    exe.mkdir(parents=True)
    (exe / "python").write_text("", encoding="utf-8")
    assert common_state.venv_dir() == real / ".projectops" / "launch" / ".venv"


# ── 레포를 알 수 없는 폴더 ────────────────────────────────────────────────

@pytest.mark.parametrize("kind", ["skills", "plugins"])
def test_skill_or_plugin_cache_without_remote_is_unknown(tmp_path, kind):
    d = _fake_skill_dir(tmp_path, kind)
    assert common_state.repo_unknown(d)
    assert common_state.state_dir("launch", d) == common_state.base_dir() / "launch" / "_machine"


def test_normal_repo_keeps_its_bucket(tmp_path):
    proj = _repo(tmp_path)
    assert not common_state.repo_unknown(proj)
    assert common_state.state_dir("launch", proj).name == "acme__thing"
    # 원격 없는 로컬 레포도 스킬 폴더가 아니면 예전처럼 폴더 이름을 쓴다
    local = _repo(tmp_path, "localonly", remote=None)
    assert common_state.state_dir("launch", local).name == "localonly"


def test_skill_dir_with_remote_is_a_real_repo(tmp_path):
    """개발 체크아웃처럼 원격이 있으면 레포를 안다."""
    d = _fake_skill_dir(tmp_path)
    subprocess.run(["git", "init", "-q", str(d)], check=True)
    subprocess.run(["git", "-C", str(d), "remote", "add", "origin",
                    "https://github.com/o/projectops.git"], check=True)
    assert not common_state.repo_unknown(d)
    assert common_state.state_dir("launch", d).name == "o__projectops"


def test_unknown_root_warns_and_writes_no_fake_bucket(tmp_path):
    d = _fake_skill_dir(tmp_path)
    env = {k: v for k, v in os.environ.items() if k != "PROJECT_ROOT"}
    r = subprocess.run([sys.executable, str(launch_cli._HERE), "access", "set", "--key", "base_url",
                        "--json", '{"url":"http://localhost:1"}', "--root", str(d)],
                       capture_output=True, text=True, encoding="utf-8", env=env)
    out = _j(r.stdout)
    assert out["root_unknown"] is True and "--root" in out["next"], out
    launch = common_state.base_dir() / "launch"
    assert (launch / "_machine" / "access.json").is_file()
    assert sorted(p.name for p in launch.iterdir()) == ["_machine"], "가짜 버킷이 생겼다"


def test_project_root_env_wins_in_unknown_folder(tmp_path):
    d = _fake_skill_dir(tmp_path)
    proj = _repo(tmp_path)
    _, out, _ = run_cli("access", "show", "--root", str(d), env_extra={"PROJECT_ROOT": str(proj)})
    got = _j(out)
    assert "root_unknown" not in got, got
    assert "acme__thing" in got["file"]


def test_normal_repo_has_no_root_warning(tmp_path):
    _, out, _ = run_cli("access", "show", "--root", str(_repo(tmp_path)))
    assert "root_unknown" not in _j(out)


# ── docstring ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("fn", ["cmd_web", "cmd_db", "cmd_logs", "cmd_http"])
def test_command_docstrings_survive(fn):
    """#833 이 docstring 앞에 문장을 넣어 docstring 이 사라졌다."""
    assert getattr(launch_cli, fn).__doc__, f"{fn} docstring 이 없다"


# ── access 성적 ──────────────────────────────────────────────────────────

def _set(proj, key, value):
    _, out, _ = run_cli("access", "set", "--root", str(proj), "--key", key, "--json", json.dumps(value))
    assert _j(out)["key"] == key


def _status(proj):
    return common_access.load_status(proj)


def test_logs_success_records_verified(tmp_path):
    proj = _repo(tmp_path)
    _set(proj, "logs", {"command": "echo hello"})
    d = _j(run_cli("logs", "--root", str(proj))[1])
    assert d["ok"] is True and "verify" not in d
    st = _status(proj)["logs"]
    assert st["last"] == "ok" and st["verified"] and st["ok"] == 1


def test_logs_failure_records_last_fail_then_flags_verify(tmp_path):
    proj = _repo(tmp_path)
    _set(proj, "logs", {"command": "echo 'boom STDERR_MARK_836' >&2; exit 3"})
    d = _j(run_cli("logs", "--root", str(proj))[1])
    assert d["ok"] is False and "verify" not in d          # 처음 실패는 아직 의심할 기록이 없다
    st = _status(proj)["logs"]
    assert st["last"] == "fail" and st["last_fail"]["code"] == "logs_failed"
    # 오류 원문은 남기지 않는다 — 서버 출력에 비밀이 섞일 수 있다
    assert "STDERR_MARK_836" not in common_access.status_path(proj).read_text(encoding="utf-8")
    d2 = _j(run_cli("logs", "--root", str(proj))[1])
    assert d2["verify"] is True and "access set" in d2["verify_note"]
    assert _status(proj)["logs"]["fail"] == 1               # 같은 날 반복은 한 번만 센다
    shown = _j(run_cli("access", "show", "--root", str(proj))[1])
    assert shown["verify"] == ["logs"]


def test_resetting_the_method_clears_its_grade(tmp_path):
    proj = _repo(tmp_path)
    _set(proj, "logs", {"command": "exit 3"})
    run_cli("logs", "--root", str(proj))
    _set(proj, "logs", {"command": "echo ok"})
    assert "logs" not in _status(proj)
    d = _j(run_cli("logs", "--root", str(proj))[1])
    assert d["ok"] is True and "verify" not in d


def test_db_profile_command_is_graded(tmp_path):
    proj = _repo(tmp_path)
    _set(proj, "db", {"command": "cat >/dev/null; exit 2"})
    d = _j(run_cli("db", "--root", str(proj), "--profile", "db", "--sql", "select 1")[1])
    assert d["code"] == "db_query_failed"
    assert _status(proj)["db"]["last"] == "fail"
    _set(proj, "db", {"command": "cat"})
    run_cli("db", "--root", str(proj), "--profile", "db", "--sql", "select 1")
    assert _status(proj)["db"]["last"] == "ok"


def test_environment_failures_are_not_the_methods_fault(tmp_path):
    """환경변수가 비어 있는 것은 적어 둔 방법이 틀린 것이 아니다 — 세지 않는다."""
    proj = _repo(tmp_path)
    _set(proj, "db", {"engine": "postgres", "host": "h", "password_env": "NO_SUCH_PW_ENV_836"})
    d = _j(run_cli("db", "--root", str(proj), "--profile", "db", "--sql", "select 1")[1])
    assert d["code"] == "password_env_empty"
    assert "db" not in _status(proj)


def _closed_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_http_base_url_failure_is_graded(tmp_path):
    proj = _repo(tmp_path)
    _set(proj, "base_url", {"url": f"http://127.0.0.1:{_closed_port()}"})
    d = _j(run_cli("http", "--root", str(proj), "--url", "/health", "--timeout", "3")[1])
    assert d["ok"] is False
    assert _status(proj)["base_url"]["last_fail"]["code"] == "request_failed"


def test_http_full_url_does_not_touch_grades(tmp_path):
    """적어 둔 base_url 을 쓰지 않은 요청은 그 기록의 성적이 아니다."""
    proj = _repo(tmp_path)
    _set(proj, "base_url", {"url": "http://example.invalid"})
    run_cli("http", "--root", str(proj), "--url", f"http://127.0.0.1:{_closed_port()}/x", "--timeout", "3")
    assert "base_url" not in _status(proj)
