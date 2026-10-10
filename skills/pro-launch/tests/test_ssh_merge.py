"""pro-ssh 통합 (#841) — 서버 기억 필터 · 첫 접속 사실 기록 · import-ssh · 비밀 미출력. 서버 없이 가짜 ssh 로."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(HERE.parents[2] / "scripts"))
import knowledge  # noqa: E402
from test_credentials import run, write_cfg  # noqa: E402


@pytest.fixture
def home(tmp_path):
    h = tmp_path / "home"
    h.mkdir()
    return h


def _fake_ssh(tmp_path: Path, uname_out: str) -> Path:
    b = tmp_path / "fbin"
    b.mkdir(exist_ok=True)
    # 탐침(uname 포함)에는 사실을, 그 외에는 평범한 출력을 낸다
    (b / "ssh").write_text(
        '#!/bin/bash\ncat > /dev/null\nlast="${@: -1}"\n'
        f'case "$last" in *uname*) printf "{uname_out}";; *) echo "ok";; esac\n')
    (b / "ssh").chmod(0o755)
    return b


def _machine(tmp_path: Path) -> list[dict]:
    p = tmp_path / "home" / ".projectops" / "launch" / "_machine" / "knowledge.json"
    return knowledge.load(p)


def _key_cred(home, name="nas"):
    run(home, "cred", "set", "--name", name, "--json",
        json.dumps({"kind": "ssh", "host": "h.example", "user": "u", "key_path": "/nonexistent/key"}))


def test_첫_접속_성공이면_OS와_시놀로지_docker_경로를_이_컴퓨터_범위에_남긴다(home, tmp_path):
    _key_cred(home)
    r = run(home, "ssh", "--cred", "nas", "--command", "true",
            path_prepend=_fake_ssh(tmp_path, "Linux\\nSYNO_DOCKER\\n"))
    assert r["ok"] is True
    rows = {e["key"]: e for e in _machine(tmp_path)}
    assert "Linux" in rows["server.nas.os"]["how"]
    assert "/var/packages/ContainerManager" in rows["server.nas.docker"]["how"]
    assert all(e["area"] == "server" for e in rows.values())
    # 호스트·계정은 기억 내용에 없다
    assert "h.example" not in json.dumps(rows) and "key" not in rows["server.nas.os"]["how"].lower().replace("키", "")


def test_OS를_이미_알면_다시_탐침하지_않고_Windows처럼_uname이_없으면_기록하지_않는다(home, tmp_path):
    _key_cred(home)
    run(home, "ssh", "--cred", "nas", "--command", "true", path_prepend=_fake_ssh(tmp_path, "Windows_NT\\n"))
    assert _machine(tmp_path) == []                      # 알려진 OS 가 아니면 쓰지 않는다


def test_ssh_응답은_그_서버_기억만_싣는다(home, tmp_path):
    _key_cred(home, "nas")
    _key_cred(home, "ec2")
    m = tmp_path / "home" / ".projectops" / "launch" / "_machine" / "knowledge.json"
    knowledge.learn(m, "server", "server.nas.containers", "컨테이너 app, db", "ok")
    knowledge.learn(m, "server", "server.ec2.logs", "로그는 /var/log/app", "ok")
    r = run(home, "ssh", "--cred", "nas", "--command", "true", path_prepend=_fake_ssh(tmp_path, "x"))
    keys = {e["key"] for e in r.get("memory", [])}
    assert "server.nas.containers" in keys and "server.ec2.logs" not in keys
    # 다른 서버는 같은 날이라도 자기 몫을 따로 받는다
    r2 = run(home, "ssh", "--cred", "ec2", "--command", "true", path_prepend=_fake_ssh(tmp_path, "x"))
    assert {e["key"] for e in r2.get("memory", [])} == {"server.ec2.logs"}


def test_surface_key_prefix_는_노출_기록을_접두사별로_센다(tmp_path):
    p = tmp_path / "k.json"
    knowledge.learn(p, "server", "server.a.x", "A 사실", "ok")
    knowledge.learn(p, "server", "server.b.x", "B 사실 다름", "ok")
    seen = tmp_path / "seen.json"
    a = knowledge.surface({"machine": p}, "server", seen, key_prefix="server.a.")
    assert [e["key"] for e in a] == ["server.a.x"]
    assert knowledge.surface({"machine": p}, "server", seen, key_prefix="server.a.") == []   # 하루 한 번
    assert [e["key"] for e in knowledge.surface({"machine": p}, "server", seen, key_prefix="server.b.")] == ["server.b.x"]


# ── import-ssh ───────────────────────────────────────────────────────────
def test_import_ssh_dry_run_은_아무것도_쓰지_않고_비밀을_가린다(home):
    write_cfg(home, {"ssh": [{"name": "nas", "host": "h", "user": "u", "password": "pw-SECRET99"}]})
    before = (home / ".projectops" / "config" / "config.json").read_text(encoding="utf-8")
    r = run(home, "cred", "import-ssh", "--dry-run", "--inline")
    assert r["ok"] and r["dry_run"] and r["servers"][0]["status"] == "would_import"
    assert "pw-SECRET99" not in json.dumps(r)
    assert (home / ".projectops" / "config" / "config.json").read_text(encoding="utf-8") == before


def test_import_ssh_기본은_값까지_복사하고_이미_있는_이름은_건너뛴다(home):
    write_cfg(home, {"ssh": [{"name": "nas", "host": "h", "password": "pw-SECRET99"}, {"name": "old", "host": "o"}]})
    run(home, "cred", "set", "--name", "old", "--json", json.dumps({"kind": "ssh", "host": "o"}))
    r = run(home, "cred", "import-ssh")
    st = {s["name"]: s["status"] for s in r["servers"]}
    assert st == {"nas": "imported", "old": "exists"}
    assert "pw-SECRET99" not in json.dumps(r)                      # 응답에는 비밀이 없다
    saved = json.loads((home / ".projectops" / "config" / "config.json").read_text(encoding="utf-8"))
    assert saved["launch"]["credentials"]["nas"]["password"] == "pw-SECRET99"   # cred 한 곳에 값이 있다
    assert saved["ssh"][0]["password"] == "pw-SECRET99"                          # 옛 섹션은 --prune 전까지 그대로


def test_import_ssh_ref_는_참조만_만든다(home):
    write_cfg(home, {"ssh": [{"name": "nas", "host": "h", "password": "pw-SECRET99"}]})
    run(home, "cred", "import-ssh", "--ref")
    saved = json.loads((home / ".projectops" / "config" / "config.json").read_text(encoding="utf-8"))
    assert saved["launch"]["credentials"]["nas"] == {"kind": "ssh", "ssh_server": "nas"}


def test_import_ssh_prune_은_백업한_뒤_가져온_서버만_옛_섹션에서_지운다(home):
    write_cfg(home, {"ssh": [{"name": "nas", "host": "h", "password": "pw-SECRET99"},
                             {"name": "한글이름", "host": "k", "password": "pw-KEEP"}]})
    r = run(home, "cred", "import-ssh", "--prune")
    assert r["pruned"]["removed"] == ["nas"] and "pw-SECRET99" not in json.dumps(r)
    cfgdir = home / ".projectops" / "config"
    saved = json.loads((cfgdir / "config.json").read_text(encoding="utf-8"))
    assert [s["name"] for s in saved["ssh"]] == ["한글이름"]            # 못 가져온 서버는 옛 섹션에 남는다
    assert saved["launch"]["credentials"]["nas"]["password"] == "pw-SECRET99"
    bak = cfgdir / "config.json.bak-ssh-prune"
    assert bak.exists() and oct(bak.stat().st_mode & 0o777) == "0o600"
    assert "pw-SECRET99" in bak.read_text(encoding="utf-8")            # 백업에서 되돌릴 수 있다


def test_ssh_connect_는_환경변수_비밀번호를_쓰고_출력에서_가린다():
    src = (HERE.parents[1] / "pro-ssh" / "scripts" / "ssh_connect.py").read_text(encoding="utf-8")
    assert "SSH_PASSWORD" in src and '"***"' in src and "launch_cli.py ssh" in src
