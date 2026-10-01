"""version_manager 결함 회귀 테스트 (#664 하위 이슈 묶음).

실제 CLI를 임시 폴더에서 서브프로세스로 돌려 stdout/exit code/파일 바이트를 검증한다.
모듈 import 방식으로는 sys.exit·트레이스백·파일 바이트 보존을 잡을 수 없기 때문이다.
"""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "version_manager.py"


def run_vm(workdir, *args, python=None):
    """version_manager.py를 workdir에서 실행해 (rc, stdout, stderr) 반환."""
    p = subprocess.run(
        [python or sys.executable, str(SCRIPT), *args],
        cwd=str(workdir), capture_output=True, env=_env(),
    )
    return p.returncode, p.stdout.decode("utf-8"), p.stderr.decode("utf-8")


def _env():
    import os
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def write(path, data):
    """바이트/문자열을 그대로 기록 (줄바꿈 변환 방지를 위해 항상 바이트로)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))


YML_BASIC = 'version: "1.2.3"\nversion_code: 5\nproject_types: ["basic"]\n'


# ── #695: Python 3.9 기동 ─────────────────────────────────────────────
def test_future_annotations_declared():
    # 3.9에서 `str | None` 주석이 평가되지 않도록 지연 평가가 선언돼 있어야 한다.
    assert "from __future__ import annotations" in SCRIPT.read_text(encoding="utf-8")


@pytest.mark.skipif(not Path("/usr/bin/python3").exists(), reason="시스템 python3 없음")
def test_runs_on_system_python(tmp_path):
    # macOS 기본 /usr/bin/python3(3.9)에서 기동해야 한다. 3.10+이면 어차피 통과.
    write(tmp_path / "version.yml", YML_BASIC)
    rc, out, err = run_vm(tmp_path, "get", python="/usr/bin/python3")
    assert rc == 0, err
    assert out.strip().splitlines()[-1] == "1.2.3"


# ── #685: set 버전 검증 (개행·앞자리 0) ────────────────────────────────
@pytest.mark.parametrize("bad", ["1.2.3\n", "1.2.3 ", " 1.2.3", "01.02.03", "1.02.3", "1.2", "1.2.3.4", "v1.2.3"])
def test_set_rejects_malformed_version(tmp_path, bad):
    write(tmp_path / "version.yml", YML_BASIC)
    rc, out, err = run_vm(tmp_path, "set", bad)
    assert rc == 1, (out, err)
    # 거부했다면 파일은 한 바이트도 바뀌면 안 된다
    assert (tmp_path / "version.yml").read_bytes() == YML_BASIC.encode()


@pytest.mark.parametrize("ok", ["0.0.0", "0.1.0", "10.20.30"])
def test_set_accepts_valid_version(tmp_path, ok):
    write(tmp_path / "version.yml", YML_BASIC)
    rc, out, err = run_vm(tmp_path, "set", ok)
    assert rc == 0, err
    assert out.strip().splitlines()[-1] == ok
