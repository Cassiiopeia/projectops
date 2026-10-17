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
def test_아무것도_없으면_모든_키가_ask(home):
    policy = credentials.resolve_login_policy(None)
    assert set(policy) == {"trust_device", "keep_signed_in", "skip_nags"}
    assert all(item == {"value": "ask", "source": "default"} for item in policy.values())


def test_계정_값이_전체_값을_키_단위로_이긴다(home):
    write_cfg(home, {"launch": {"login_policy": {"trust_device": "always", "skip_nags": "always"},
                                "credentials": {"g": {"kind": "login", "login_policy": {"trust_device": "never"}}}}})
    policy = credentials.resolve_login_policy("g")
    assert policy["trust_device"] == {"value": "never", "source": "credential"}
    assert policy["skip_nags"] == {"value": "always", "source": "global"}
    assert policy["keep_signed_in"] == {"value": "ask", "source": "default"}


def test_손으로_잘못_고친_값은_ask_로_본다(home):
    write_cfg(home, {"launch": {"login_policy": {"trust_device": "yes", "keep_signed_in": ["x"]},
                                "credentials": {"g": {"login_policy": "always"}}}})
    policy = credentials.resolve_login_policy("g")
    assert policy["trust_device"] == {"value": "ask", "source": "default"}
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


def test_이름이_없으면_전체_기본값에_저장한다(home):
    credentials.set_login_policy(None, "skip_nags", "always")
    data = read_cfg(home)
    assert data["launch"]["login_policy"] == {"skip_nags": "always"}
    assert "credentials" not in data["launch"]
    assert credentials.resolve_login_policy(None)["skip_nags"] == {"value": "always", "source": "global"}


@pytest.mark.parametrize("name,key,value,code", [
    (None, "unknown", "always", "invalid_policy_key"),
    (None, "trust_device", "yes", "invalid_policy_value"),
    ("nope", "trust_device", "always", "cred_not_found"),
])
def test_잘못된_키_값_계정은_거절하고_파일을_바꾸지_않는다(home, name, key, value, code):
    write_cfg(home, {"github": {"global_pat": "x"}})
    before = cfg_path(home).read_text(encoding="utf-8")
    with pytest.raises(credentials.CredError) as error:
        credentials.set_login_policy(name, key, value)
    assert error.value.code == code
    assert cfg_path(home).read_text(encoding="utf-8") == before


def test_깨진_config_는_덮어쓰지_않는다(home):
    cfg_path(home).parent.mkdir(parents=True, exist_ok=True)
    cfg_path(home).write_text("{broken", encoding="utf-8")
    with pytest.raises(credentials.CredError) as error:
        credentials.set_login_policy(None, "trust_device", "always")
    assert error.value.code == "config_unreadable"
    assert cfg_path(home).read_text(encoding="utf-8") == "{broken"


# ── CLI: cred policy get|set|unset ──────────────────────────────────────
def run(home: Path, *args) -> dict:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "HOME": str(home), "USERPROFILE": str(home)}
    completed = subprocess.run([sys.executable, str(CLI), *map(str, args)], capture_output=True, text=True,
                               encoding="utf-8", env=env, timeout=60)
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError:
        raise AssertionError(f"JSON 아님: {completed.stdout!r} / {completed.stderr!r}")


def test_cli_정책_저장_조회_제거(home):
    run(home, "cred", "set", "--name", "g", "--json", '{"kind":"login"}')
    saved = run(home, "cred", "policy", "set", "--name", "g", "--key", "trust_device", "--value", "always")
    assert saved["ok"] is True and saved["scope"] == "credential"
    assert saved["login_policy"]["trust_device"] == {"value": "always", "source": "credential"}
    shown = run(home, "cred", "policy", "get", "--name", "g")
    assert shown["ok"] is True and shown["login_policy"]["trust_device"]["value"] == "always"
    assert shown["next"]
    removed = run(home, "cred", "policy", "unset", "--name", "g", "--key", "trust_device")
    assert removed["code"] == "ok" and removed["login_policy"]["trust_device"]["source"] == "default"
    assert run(home, "cred", "policy", "unset", "--name", "g", "--key", "trust_device")["code"] == "not_found"


def test_cli_이름_없이_저장하면_전체_기본값(home):
    saved = run(home, "cred", "policy", "set", "--key", "skip_nags", "--value", "always")
    assert saved["scope"] == "global"
    assert run(home, "cred", "policy", "get")["login_policy"]["skip_nags"] == {"value": "always", "source": "global"}


@pytest.mark.parametrize("args,code", [
    (("cred", "policy"), "policy_action_required"),
    (("cred", "policy", "set", "--key", "trust_device"), "value_required"),
    (("cred", "policy", "set", "--value", "always"), "key_required"),
    (("cred", "policy", "unset"), "key_required"),
    (("cred", "policy", "set", "--key", "x", "--value", "always"), "invalid_policy_key"),
    (("cred", "policy", "set", "--key", "trust_device", "--value", "yes"), "invalid_policy_value"),
    (("cred", "policy", "set", "--name", "nope", "--key", "trust_device", "--value", "always"), "cred_not_found"),
])
def test_cli_오류는_JSON_code_로_돌려준다(home, args, code):
    result = run(home, *args)
    assert result["ok"] is False and result["code"] == code and result["next"]


def test_cli_정책_결과에_비밀이_실리지_않는다(home):
    run(home, "cred", "set", "--name", "g", "--json", '{"kind":"login","password":"s3cret-pw"}')
    run(home, "cred", "policy", "set", "--name", "g", "--key", "trust_device", "--value", "always")
    assert "s3cret-pw" not in json.dumps(run(home, "cred", "policy", "get", "--name", "g"))


# ── 로그인 입력 결과에 정책 싣기 (웹·앱 공통 헬퍼) ─────────────────────────
from pro_launch.runtime.creds import with_login_policy  # noqa: E402

LOGIN_ENTRY_POINTS = (
    SCRIPTS_DIR / "pro_launch" / "commands" / "web" / "__init__.py",
    SCRIPTS_DIR / "pro_launch" / "commands" / "app" / "actions" / "type_.py",
)


def test_성공과_사용자_인계_결과에_정책을_싣는다(home):
    write_cfg(home, {"launch": {"login_policy": {"trust_device": "always"}}})
    payload = with_login_policy({"action": "type"}, None)
    assert payload["login_policy"]["trust_device"] == {"value": "always", "source": "global"}
    assert "login_policy" in with_login_policy({"ok": False, "code": "needs_user"}, None)


def test_계정_이름이_있으면_계정_정책을_싣는다(home):
    write_cfg(home, {"launch": {"credentials": {"g": {"kind": "login", "password": "pw-secret",
                                                      "login_policy": {"keep_signed_in": "never"}}}}})
    payload = with_login_policy({"action": "type"}, "g")
    assert payload["login_policy"]["keep_signed_in"] == {"value": "never", "source": "credential"}
    assert "pw-secret" not in json.dumps(payload)


def test_실패_결과에는_싣지_않고_깨진_config_에도_죽지_않는다(home):
    assert "login_policy" not in with_login_policy({"ok": False, "code": "web_action_failed"}, None)
    cfg_path(home).parent.mkdir(parents=True, exist_ok=True)
    cfg_path(home).write_text("{broken", encoding="utf-8")
    # 읽지 못하면 저장된 선택이 없는 것으로 본다 > 전부 ask (사용자에게 묻는 쪽이 안전)
    payload = with_login_policy({"action": "type"}, None)
    assert all(item["value"] == "ask" for item in payload["login_policy"].values())


def test_로그인_입력_진입점은_공통_헬퍼만_쓴다():
    for path in LOGIN_ENTRY_POINTS:
        source = path.read_text(encoding="utf-8")
        assert "with_login_policy(" in source, f"{path.name} 가 with_login_policy 를 부르지 않는다"
        assert "resolve_login_policy(" not in source, f"{path.name} 가 정책을 직접 판정한다"


# ── 리뷰 지적 회귀 방지 ───────────────────────────────────────────────────
def test_cli_ssh_server_참조가_깨진_계정도_정책은_조회된다(home):
    write_cfg(home, {"launch": {"credentials": {"a": {"kind": "ssh", "ssh_server": "zz"}}}})
    assert run(home, "cred", "policy", "set", "--name", "a", "--key", "trust_device", "--value", "always")["ok"] is True
    shown = run(home, "cred", "policy", "get", "--name", "a")
    assert shown["ok"] is True and shown["login_policy"]["trust_device"]["value"] == "always"
    assert run(home, "cred", "policy", "get", "--name", "nope")["code"] == "cred_not_found"


def test_config_가_객체가_아니면_조회는_ask_쓰기는_거절(home):
    write_cfg(home, [1])
    assert all(item["value"] == "ask" for item in credentials.resolve_login_policy(None).values())
    assert run(home, "cred", "policy", "get")["ok"] is True
    with pytest.raises(credentials.CredError) as error:
        credentials.set_login_policy(None, "trust_device", "always")
    assert error.value.code == "config_unreadable"
    assert read_cfg(home) == [1]
