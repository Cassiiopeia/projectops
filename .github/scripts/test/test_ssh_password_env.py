"""서버 비밀번호는 SSH 스크립트 본문에 치환하지 않고 env/envs 로만 전달한다 (#728).

`export PW=${{ secrets.SERVER_PASSWORD }}` 처럼 쓰면 공백, ;, $, " 가 든 비밀번호가 잘리거나
서버에서 명령으로 실행된다.
"""
import glob
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
FILES = sorted(glob.glob(str(ROOT / ".github/workflows/project-types/**/*.y*ml"), recursive=True))


def _ssh_steps():
    for p in FILES:
        d = yaml.safe_load(Path(p).read_text(encoding="utf-8")) or {}
        for jn, j in (d.get("jobs") or {}).items():
            for s in j.get("steps", []):
                if "appleboy/ssh-action" in str(s.get("uses", "")):
                    yield Path(p).name, s


def test_ssh_스크립트_본문에_비밀번호_식이_직접_들어가지_않는다():
    bad = [(f, s.get("name")) for f, s in _ssh_steps() if "secrets.SERVER_PASSWORD" in (s.get("with") or {}).get("script", "")]
    assert not bad, bad


def test_비밀번호를_쓰는_ssh_step_은_env_와_envs_를_갖춘다():
    checked = 0
    for f, s in _ssh_steps():
        script = (s.get("with") or {}).get("script", "")
        if 'PW="${SERVER_PASSWORD}"' not in script and "PW=${SERVER_PASSWORD}" not in script:
            continue
        checked += 1
        assert "SERVER_PASSWORD" in (s.get("env") or {}), (f, s.get("name"))
        assert "SERVER_PASSWORD" in str((s.get("with") or {}).get("envs", "")), (f, s.get("name"))
    assert checked >= 10, "서버 배포 워크플로의 SSH step 을 충분히 검사하지 못했다"


@pytest.mark.parametrize("pw", ["pass word", "a;touch X", "ab$cd!ef", 'q"uote', "back`tick", "sl\\ash"])
def test_env_로_전달된_비밀번호는_어떤_문자든_그대로_보존된다(pw, tmp_path):
    """envs 방식의 실제 셸 동작: 값은 변수로만 취급돼 명령으로 실행되지 않는다."""
    import subprocess
    r = subprocess.run(["bash", "-c", 'export PW="${SERVER_PASSWORD}"; printf "%s" "$PW"'], cwd=tmp_path,
                       env={"SERVER_PASSWORD": pw, "PATH": "/usr/bin:/bin"}, capture_output=True, text=True)
    assert r.stdout == pw
    assert not list(tmp_path.iterdir())  # ; 뒤 명령이 실행됐다면 파일이 생겼을 것
