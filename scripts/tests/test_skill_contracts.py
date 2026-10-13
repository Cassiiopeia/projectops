"""스킬 공통 계약: frontmatter, 참조 파일, CLI --help, 잘못된 인자 시 JSON 오류 (#864).
네트워크 없이 도는 경로만 본다."""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SKILLS = [*sorted((ROOT / "skills").glob("pro-*")), *sorted((ROOT / "plugins").glob("*/skills/pro-*"))]
CLIS = sorted(p for s in SKILLS for p in (s / "scripts").glob("*_cli.py"))
# PATH·SYSTEMROOT 는 남겨야 Windows 에서 파이썬이 뜬다 — 예전의 PATH="" 는 이식성이 없어 뺐다.
# --help·잘못된 서브커맨드는 argparse 단계에서 끝나므로 외부 명령·config 에 닿지 않는다.
_DROP = ("HOME", "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "PYTHONPATH")


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    """HOME 계열을 빈 임시 폴더로 격리한 환경 (기여자의 실제 config 가 새지 않게)."""
    home = str(tmp_path_factory.mktemp("home"))
    return {**{k: v for k, v in os.environ.items() if k not in _DROP},
            "HOME": home, "USERPROFILE": home, "PYTHONIOENCODING": "utf-8"}


# -I: 사용자 site-packages·PYTHONPATH·스크립트 폴더 무시, -S: site-packages 무시.
# 기여자 환경에 paramiko 가 깔려 있어도 "없는 상태"를 재현한다.
NO_SITE = [sys.executable, "-I", "-S"]


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.name)
def test_frontmatter(skill):
    text = (skill / "SKILL.md").read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    assert m, "frontmatter 없음"
    assert re.search(rf"^name:\s*['\"]?{re.escape(skill.name)}['\"]?\s*$", m.group(1), re.MULTILINE)
    assert re.search(r"^description:\s*\S", m.group(1), re.MULTILINE)


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.name)
def test_own_references_exist(skill):
    text = (skill / "SKILL.md").read_text(encoding="utf-8")
    for ref in re.findall(r"`(references/[a-z0-9_-]+\.md)`", text):
        assert (skill / ref).exists(), ref


@pytest.mark.parametrize("cli", CLIS, ids=lambda p: p.parent.parent.name)
def test_cli_help_exits_zero(cli, env):
    r = subprocess.run([sys.executable, str(cli), "--help"], capture_output=True, text=True,
                       env=env, timeout=30)
    assert r.returncode == 0, r.stderr


@pytest.mark.parametrize("cli", CLIS, ids=lambda p: p.parent.parent.name)
def test_cli_bad_subcommand_returns_json(cli, env):
    r = subprocess.run([sys.executable, str(cli), "no-such-subcommand"], capture_output=True, text=True,
                       env=env, timeout=30)
    assert r.stdout.strip(), f"stdout 비어 있음: {r.stderr}"
    payload = json.loads(r.stdout.strip().splitlines()[-1])
    assert r.returncode != 0
    assert payload["ok"] is False and payload["code"] == "bad_args"
    assert "no-such-subcommand" in payload.get("error", "")


SSH_CONNECT = ROOT / "skills" / "pro-ssh" / "scripts" / "ssh_connect.py"


def test_ssh_connect_help_without_paramiko(env):
    # -S: site-packages 제외 → paramiko 가 없어도 --help 는 정상 종료해야 한다(지연 import)
    r = subprocess.run([*NO_SITE, str(SSH_CONNECT), "--help"], capture_output=True, text=True, env=env, timeout=30)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "usage" in r.stdout.lower()


def test_ssh_connect_missing_paramiko_prints_install_hint(env):
    # 인자 검증 통과 후 첫 소켓 호출 전에 paramiko import 에서 멈춘다 (네트워크 불필요).
    # 만에 하나 paramiko 가 불려도 밖으로 나가지 않게 루프백의 닫힌 포트(1)·짧은 타임아웃을 준다.
    r = subprocess.run([*NO_SITE, str(SSH_CONNECT), "--host", "127.0.0.1", "--port", "1", "--timeout", "1",
                        "--user", "u", "--auth", "password", "--password", "pw", "--command", "true"],
                       capture_output=True, text=True, env=env, timeout=30)
    assert r.returncode != 0
    assert "pip install paramiko" in r.stdout
