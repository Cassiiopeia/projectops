"""로그인 중간 화면 정책 (login_policy) 검증 (#905).

판정 순서(계정 > 전체 > ask) · 저장 · CLI 계약 · 결과에 싣는 공통 헬퍼.
실제 ~/.projectops 를 건드리지 않도록 모든 호출은 임시 HOME 에서 돌린다.
"""
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
CLI = SCRIPTS_DIR / "launch_cli.py"
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import credentials  # noqa: E402


def cfg_path(home: Path) -> Path:
    return home / ".projectops" / "config" / "config.json"


def write_cfg(home: Path, data: dict) -> None:
    path = cfg_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def read_cfg(home: Path) -> dict:
    return json.loads(cfg_path(home).read_text(encoding="utf-8"))


@pytest.fixture
def home(tmp_path, monkeypatch):
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.setenv("HOME", str(home_dir))
    monkeypatch.setenv("USERPROFILE", str(home_dir))
    return home_dir


# ── 판정 ────────────────────────────────────────────────────────────────
def test_계정_값이_전체_값을_키_단위로_이긴다(home):
    write_cfg(home, {"launch": {"login_policy": {"trust_device": "always", "skip_nags": "always"},
                                "credentials": {"g": {"kind": "login", "login_policy": {"trust_device": "never"}}}}})
    policy = credentials.resolve_login_policy("g")
    assert policy["trust_device"] == {"value": "never", "source": "credential"}
    assert policy["skip_nags"] == {"value": "always", "source": "global"}
    assert policy["keep_signed_in"] == {"value": "ask", "source": "default"}


# ── 저장 ────────────────────────────────────────────────────────────────
def test_계정_정책_저장과_제거는_다른_값을_건드리지_않는다(home):
    write_cfg(home, {"launch": {"credentials": {"g": {"kind": "login", "password": "pw"}}},
                     "github": {"global_pat": "x"}})
    credentials.set_login_policy("g", "trust_device", "always")
    data = read_cfg(home)
    assert data["launch"]["credentials"]["g"] == {"kind": "login", "password": "pw",
                                                  "login_policy": {"trust_device": "always"}}
    assert data["github"] == {"global_pat": "x"}
    if os.name != "nt":
        assert stat.S_IMODE(cfg_path(home).stat().st_mode) == 0o600
    assert credentials.unset_login_policy("g", "trust_device") is True
    assert "login_policy" not in read_cfg(home)["launch"]["credentials"]["g"]
    assert credentials.unset_login_policy("g", "trust_device") is False


# ── CLI: cred policy get|set|unset ──────────────────────────────────────
def run(home: Path, *args) -> dict:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "HOME": str(home), "USERPROFILE": str(home)}
    completed = subprocess.run([sys.executable, str(CLI), *map(str, args)], capture_output=True, text=True,
                               encoding="utf-8", env=env, timeout=60)
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError:
        raise AssertionError(f"JSON 아님: {completed.stdout!r} / {completed.stderr!r}")


def test_cli_정책_결과에_비밀이_실리지_않는다(home):
    run(home, "cred", "set", "--name", "g", "--json", '{"kind":"login","password":"s3cret-pw"}')
    run(home, "cred", "policy", "set", "--name", "g", "--key", "trust_device", "--value", "always")
    assert "s3cret-pw" not in json.dumps(run(home, "cred", "policy", "get", "--name", "g"))
