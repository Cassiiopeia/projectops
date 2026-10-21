"""이름 붙은 자격증명 저장소 (cred · ssh · --cred) 검증.

실제 ~/.projectops 를 건드리지 않도록 모든 호출은 임시 HOME 에서 돌린다.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

CLI = Path(__file__).resolve().parents[1] / "scripts" / "launch_cli.py"


def run(home: Path, *args, path_prepend: Path | None = None, stdin: str | None = None,
        env_extra: dict | None = None):
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "HOME": str(home), "USERPROFILE": str(home),
           **(env_extra or {})}
    if path_prepend:
        env["PATH"] = f"{path_prepend}{os.pathsep}{env['PATH']}"
    # 한글이 든 출력을 로케일(윈도우 cp949)로 읽으면 깨진다 — 스크립트는 UTF-8 로 쓴다
    r = subprocess.run([sys.executable, str(CLI), *map(str, args)], capture_output=True, text=True,
                       encoding="utf-8", env=env, input=stdin, timeout=60)
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        raise AssertionError(f"JSON 아님: {r.stdout!r} / {r.stderr!r}")


def cfg_path(home: Path) -> Path:
    return home / ".projectops" / "config" / "config.json"


# test_ssh_merge 가 가져다 쓴다
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
def test_show_는_비밀을_가리고_reveal_일_때만_보여_준다(home):
    run(home, "cred", "set", "--name", "n", "--json", json.dumps({"password": "pw-12345", "token": "tok-abcdef", "user": "u"}))
    shown = run(home, "cred", "show", "--name", "n")
    assert shown["credential"]["password"] == "<저장됨>" and shown["credential"]["token"] == "<저장됨>"
    assert shown["credential"]["user"] == "u"
    assert "pw-12345" not in json.dumps(shown)
    assert run(home, "cred", "show", "--name", "n", "--reveal")["credential"]["password"] == "pw-12345"


# ── ssh: 비밀번호가 명령줄에 남지 않는다 ─────────────────────────────────────
def _fake_bin(tmp_path: Path) -> Path:
    """가짜 sshpass/ssh. 받은 인자와 표준입력을 파일에 기록한다."""
    b = tmp_path / "bin"
    b.mkdir()
    (b / "sshpass").write_text('#!/bin/bash\necho "SSHPASS_SET=${SSHPASS:+yes}" >> "$REC"\nshift\nexec "$@"\n')
    # 첫 호출(실제 명령)만 기록한다 — 뒤따르는 서버 사실 탐침이 덮어쓰지 않게
    (b / "ssh").write_text('#!/bin/bash\nif [ ! -e "$REC.argv" ]; then printf "%s\\n" "$@" > "$REC.argv"; cat > "$REC.stdin"; fi\necho "ok from fake"\n')
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


# ── access 와의 경계 ──────────────────────────────────────────────────────
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


# ── 로컬 맥 sudo (#784) ─────────────────────────────────────────────

def _fake_sudo(tmp_path: Path) -> Path:
    b = tmp_path / "fakebin_sudo"
    b.mkdir(exist_ok=True)
    # 받은 인자와 표준입력을 기록한다. 실제 sudo 처럼 첫 줄을 비밀번호로 읽고, 틀리면 실패한다.
    (b / "sudo").write_text(
        '#!/bin/bash\nprintf "%s\\n" "$@" > "$REC.argv"\nIFS= read -r PW\nprintf "%s" "$PW" > "$REC.pw"\n'
        'if [ "$PW" != "right-PW-123" ]; then echo "Sorry, try again." >&2; exit 1; fi\n'
        'echo "ran as root: $*"\n')
    (b / "sudo").chmod(0o755)
    return b


def _run_sudo(home, tmp_path, *args):
    rec = tmp_path / "rec"
    os.environ["REC"] = str(rec)
    try:
        return run(home, *args, path_prepend=_fake_sudo(tmp_path))
    finally:
        os.environ.pop("REC", None)


def test_local_sudo_는_비밀번호를_명령줄이_아니라_표준입력으로만_넘긴다(home, tmp_path):
    run(home, "cred", "set", "--name", "mac", "--json",
        json.dumps({"kind": "local", "use_when": "이 맥에서 관리자 권한이 필요할 때", "sudo_password": "right-PW-123"}))
    r = _run_sudo(home, tmp_path, "local", "sudo", "--cred", "mac", "--", "installer", "-pkg", "/x.pkg", "-target", "/")
    assert r["ok"] is True, r
    argv = (tmp_path / "rec.argv").read_text(encoding="utf-8")
    assert "right-PW-123" not in argv                       # ps 에 보이는 인자에 없다
    assert "installer" in argv and "/x.pkg" in argv
    assert (tmp_path / "rec.pw").read_text(encoding="utf-8") == "right-PW-123"
    assert "right-PW-123" not in json.dumps(r)              # 응답에도 없다
    assert "ran as root" in r["stdout"]
