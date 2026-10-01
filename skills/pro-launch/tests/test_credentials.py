"""이름 붙은 자격증명 저장소 (cred · ssh · --cred) 검증.

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

CLI = Path(__file__).resolve().parents[1] / "scripts" / "launch_cli.py"
sys.path.insert(0, str(CLI.parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import credentials  # noqa: E402


def run(home: Path, *args, path_prepend: Path | None = None, stdin: str | None = None):
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "HOME": str(home), "USERPROFILE": str(home)}
    if path_prepend:
        env["PATH"] = f"{path_prepend}{os.pathsep}{env['PATH']}"
    r = subprocess.run([sys.executable, str(CLI), *map(str, args)], capture_output=True, text=True, env=env,
                       input=stdin, timeout=60)
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        raise AssertionError(f"JSON 아님: {r.stdout!r} / {r.stderr!r}")


def cfg_path(home: Path) -> Path:
    return home / ".projectops" / "config" / "config.json"


def write_cfg(home: Path, data: dict):
    p = cfg_path(home)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data), encoding="utf-8")


@pytest.fixture
def home(tmp_path):
    h = tmp_path / "home"
    h.mkdir()
    return h


# ── 저장·조회 ────────────────────────────────────────────────────────────
def test_저장하고_목록에서_use_when_으로_고를_수_있다(home):
    r = run(home, "cred", "set", "--name", "nas", "--json",
            json.dumps({"kind": "ssh", "host": "h", "user": "u", "password": "Sup3rSecret!",
                        "use_when": "배포 QA", "scope": "test-only"}))
    assert r["ok"] and r["summary"] == "nas 저장 완료"
    lst = run(home, "cred", "list")
    item = lst["credentials"][0]
    assert item["name"] == "nas" and item["kind"] == "ssh" and item["use_when"] == "배포 QA"
    assert item["has_secret"] is True
    assert "Sup3rSecret" not in json.dumps(lst)            # 목록에 값이 나오지 않는다


def test_show_는_비밀을_가리고_reveal_일_때만_보여_준다(home):
    run(home, "cred", "set", "--name", "n", "--json", json.dumps({"password": "pw-12345", "token": "tok-abcdef", "user": "u"}))
    shown = run(home, "cred", "show", "--name", "n")
    assert shown["credential"]["password"] == "<저장됨>" and shown["credential"]["token"] == "<저장됨>"
    assert shown["credential"]["user"] == "u"
    assert "pw-12345" not in json.dumps(shown)
    assert run(home, "cred", "show", "--name", "n", "--reveal")["credential"]["password"] == "pw-12345"


def test_set_은_기본이_병합이고_replace_면_통째로_바꾼다(home):
    run(home, "cred", "set", "--name", "n", "--json", json.dumps({"host": "h", "user": "u"}))
    run(home, "cred", "set", "--name", "n", "--json", json.dumps({"user": "u2", "notes": "x"}))
    e = credentials_load(home, "n")
    assert e == {"host": "h", "user": "u2", "notes": "x"}
    run(home, "cred", "set", "--name", "n", "--replace", "--json", json.dumps({"host": "only"}))
    assert credentials_load(home, "n") == {"host": "only"}


def credentials_load(home, name):
    return json.loads(cfg_path(home).read_text(encoding="utf-8"))["launch"]["credentials"][name]


def test_저장해도_다른_섹션은_그대로이고_파일은_600이다(home):
    write_cfg(home, {"github": {"global_pat": "ghp_x"}, "ssh": [{"name": "a", "host": "h"}]})
    run(home, "cred", "set", "--name", "n", "--json", json.dumps({"kind": "other"}))
    data = json.loads(cfg_path(home).read_text(encoding="utf-8"))
    assert data["github"] == {"global_pat": "ghp_x"} and data["ssh"] == [{"name": "a", "host": "h"}]
    assert "launch" in data
    if os.name != "nt":
        assert stat.S_IMODE(cfg_path(home).stat().st_mode) == 0o600


def test_깨진_config_는_덮어쓰지_않는다(home):
    p = cfg_path(home)
    p.parent.mkdir(parents=True)
    p.write_text("{깨진 json", encoding="utf-8")
    r = run(home, "cred", "set", "--name", "n", "--json", json.dumps({"kind": "x"}))
    assert r["ok"] is False and r["code"] == "config_unreadable"
    assert p.read_text(encoding="utf-8") == "{깨진 json"


@pytest.mark.parametrize("bad", ["", "../x", "a b", "-x", "x" * 65])
def test_이름_형식을_검증한다(home, bad):
    r = run(home, "cred", "set", "--name", bad, "--json", json.dumps({"kind": "x"}))
    assert r["ok"] is False and r["code"] in ("bad_name", "name_required", "bad_args")


def test_없는_이름과_잘못된_json_은_JSON_오류로_알린다(home):
    assert run(home, "cred", "show", "--name", "nope")["code"] == "cred_not_found"
    assert run(home, "cred", "set", "--name", "n", "--json", "{안닫힘")["code"] == "bad_json"
    assert run(home, "cred", "unset", "--name", "nope")["code"] == "not_found"


def test_unset_은_지우고_다른_항목은_남긴다(home):
    run(home, "cred", "set", "--name", "a", "--json", json.dumps({"k": 1}))
    run(home, "cred", "set", "--name", "b", "--json", json.dumps({"k": 2}))
    assert run(home, "cred", "unset", "--name", "a")["ok"] is True
    assert [c["name"] for c in run(home, "cred", "list")["credentials"]] == ["b"]


# ── pro-ssh 서버 참조 ─────────────────────────────────────────────────────
def test_ssh_server_참조는_pro_ssh_의_접속값을_가져오고_직접_적은_값이_이긴다(home):
    write_cfg(home, {"ssh": [{"name": "nas", "host": "h.example", "port": 2022, "user": "u", "password": "pw-99999"}]})
    run(home, "cred", "set", "--name", "c", "--json",
        json.dumps({"kind": "ssh", "ssh_server": "nas", "user": "override"}))
    shown = run(home, "cred", "show", "--name", "c", "--reveal")["credential"]
    assert shown["host"] == "h.example" and shown["port"] == 2022 and shown["password"] == "pw-99999"
    assert shown["user"] == "override"
    # 비밀번호는 pro-ssh 쪽에만 있고 launch 항목에는 복사되지 않는다(한 곳에서만 관리)
    assert "password" not in credentials_load(home, "c")


def test_없는_ssh_server_는_오류다(home):
    run(home, "cred", "set", "--name", "c", "--json", json.dumps({"ssh_server": "ghost"}))
    assert run(home, "cred", "show", "--name", "c")["code"] == "ssh_server_not_found"


# ── 환경변수·마스킹 단위 ───────────────────────────────────────────────────
def test_env_for_는_명령이_읽을_환경변수를_만든다():
    env = credentials.env_for({"name": "n", "kind": "ssh", "host": "h", "port": 2022, "user": "u", "password": "pw-1234"})
    assert env["CRED_HOST"] == "h" and env["CRED_PORT"] == "2022" and env["CRED_USER"] == "u"
    assert env["SSHPASS"] == "pw-1234" and env["CRED_PASSWORD"] == "pw-1234"


def test_mask_는_비밀_값을_가린다():
    e = {"password": "pw-12345", "token": "tok-67890"}
    assert credentials.mask("a pw-12345 b tok-67890", e) == "a *** b ***"
    assert credentials.mask(None, e) == ""


# ── ssh: 비밀번호가 명령줄에 남지 않는다 ─────────────────────────────────────
def _fake_bin(tmp_path: Path) -> Path:
    """가짜 sshpass/ssh. 받은 인자와 표준입력을 파일에 기록한다."""
    b = tmp_path / "bin"
    b.mkdir()
    (b / "sshpass").write_text('#!/bin/bash\necho "SSHPASS_SET=${SSHPASS:+yes}" >> "$REC"\nshift\nexec "$@"\n')
    (b / "ssh").write_text('#!/bin/bash\nprintf "%s\\n" "$@" > "$REC.argv"\ncat > "$REC.stdin"\necho "ok from fake"\n')
    for f in b.iterdir():
        f.chmod(0o755)
    return b


def test_ssh_sudo_는_비밀번호를_명령줄이_아니라_표준입력으로만_넘긴다(home, tmp_path):
    run(home, "cred", "set", "--name", "srv", "--json",
        json.dumps({"kind": "ssh", "host": "h.example", "port": 2022, "user": "u", "password": "pw-TOPSECRET"}))
    rec = tmp_path / "rec"
    os.environ["REC"] = str(rec)
    try:
        r = run(home, "ssh", "--cred", "srv", "--sudo", "--command", "SUDO docker ps", path_prepend=_fake_bin(tmp_path))
    finally:
        os.environ.pop("REC", None)
    assert r["ok"] is True, r
    argv = (tmp_path / "rec.argv").read_text(encoding="utf-8")
    assert "pw-TOPSECRET" not in argv                         # ps 에 보이는 인자에 없다
    assert "u@h.example" in argv and "2022" in argv and "SUDO docker ps" in argv
    assert (tmp_path / "rec.stdin").read_text(encoding="utf-8").startswith("pw-TOPSECRET")
    assert "pw-TOPSECRET" not in json.dumps(r)                # 응답에도 없다


def test_ssh_는_cred_와_command_가_없으면_알려준다(home):
    assert run(home, "ssh", "--command", "true")["code"] == "cred_required"
    run(home, "cred", "set", "--name", "s", "--json", json.dumps({"host": "h"}))
    assert run(home, "ssh", "--cred", "s")["code"] == "command_required"


def test_sudo_인데_비밀번호가_없으면_거절한다(home):
    run(home, "cred", "set", "--name", "s", "--json", json.dumps({"host": "h", "user": "u"}))
    assert run(home, "ssh", "--cred", "s", "--sudo", "--command", "true")["code"] == "sudo_password_missing"


# ── access 와의 경계 ──────────────────────────────────────────────────────
def test_access_에_비밀을_적으면_cred_로_안내한다(home, tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    r = run(home, "access", "set", "--root", root, "--key", "db", "--json", json.dumps({"password": "hunter2hunter2"}))
    assert r["code"] == "secret_in_value" and "cred set" in r["hint"]


def test_logs_는_cred_를_환경변수로_받고_출력의_비밀을_가린다(home, tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    run(home, "cred", "set", "--name", "srv", "--json", json.dumps({"host": "h.example", "user": "u", "password": "pw-LEAKCHECK"}))
    r = run(home, "logs", "--root", root, "--cred", "srv",
            "--command", 'echo "host=$CRED_HOST user=$CRED_USER pass=$CRED_PASSWORD"')
    line = r["lines"][0]
    assert "host=h.example" in line and "user=u" in line
    assert "pw-LEAKCHECK" not in line and "pass=***" in line


# ── 로그인 정보 입력 (web type --cred · app type) ───────────────────────────
def _fake_adb(tmp_path: Path) -> Path:
    b = tmp_path / "adbbin"
    b.mkdir()
    (b / "adb").write_text(
        '#!/bin/bash\n'
        'if [ "$1" = "devices" ]; then printf "List of devices attached\\nEMU1\\tdevice\\n"; exit 0; fi\n'
        'printf "%s\\n" "$@" >> "$REC.argv"\n'
        'if [[ "$*" == *"input text"* ]]; then cat > "$REC.stdin"; fi\n'
        'exit 0\n')
    (b / "adb").chmod(0o755)
    return b


def test_web_type_cred_는_없는_이름과_없는_필드를_브라우저_없이_알려준다(home):
    assert run(home, "web", "type", "--selector", "x", "--cred", "nope")["code"] == "cred_not_found"
    run(home, "cred", "set", "--name", "g", "--json", json.dumps({"kind": "login", "provider": "google", "account": "a@b.c"}))
    r = run(home, "web", "type", "--selector", "x", "--cred", "g")
    assert r["code"] == "cred_field_missing" and "account" in r["fields"]


def test_app_type_은_값을_인자가_아니라_표준입력으로만_보낸다(home, tmp_path):
    run(home, "cred", "set", "--name", "naver", "--json",
        json.dumps({"kind": "login", "provider": "naver", "surface": "android", "account": "me", "password": "Pa ss&w0rd!"}))
    rec = tmp_path / "rec"
    env_rec = {"REC": str(rec)}
    os.environ.update(env_rec)
    try:
        r = run(home, "app", "type", "--device", "EMU1", "--cred", "naver", "--submit", path_prepend=_fake_adb(tmp_path))
    finally:
        os.environ.pop("REC", None)
    assert r["ok"] is True, r
    argv = (tmp_path / "rec.argv").read_text(encoding="utf-8")
    assert "Pa" not in argv and "w0rd" not in argv                 # 명령줄(ps)에 값이 없다
    assert (tmp_path / "rec.stdin").read_text(encoding="utf-8") == "Pa%sss&w0rd!\n"   # 공백은 %s
    assert "keyevent" in argv and "66" in argv                      # --submit
    assert "Pa ss" not in json.dumps(r) and r["chars"] == len("Pa ss&w0rd!")


def test_app_type_은_다른_필드와_비ASCII_를_구분해_처리한다(home, tmp_path):
    run(home, "cred", "set", "--name", "kr", "--json", json.dumps({"kind": "login", "account": "한글계정", "password": "pw"}))
    bin_ = _fake_adb(tmp_path)
    assert run(home, "app", "type", "--device", "EMU1", "--cred", "kr", "--cred-field", "account",
               path_prepend=bin_)["code"] == "non_ascii_unsupported"
    os.environ["REC"] = str(tmp_path / "rec")
    try:
        assert run(home, "app", "type", "--device", "EMU1", "--cred", "kr", path_prepend=bin_)["ok"] is True
    finally:
        os.environ.pop("REC", None)


def test_app_type_은_값을_text_로_받지_않는다(home):
    assert run(home, "app", "type")["code"] == "text_required"
