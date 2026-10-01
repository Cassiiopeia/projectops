"""project_paths 가 저장소 밖을 가리켜도 버전 파일을 쓰지 않는다 (#673)."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "version_manager.py"


def _project(tmp_path, node_path):
    """version.yml 만 있는 최소 프로젝트와, 그 바깥에 놓인 package.json 을 만든다."""
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "version.yml").write_text(
        'version: "1.0.0"\nversion_code: 1\nproject_types: ["node"]\n'
        f'project_paths:\n  node: "{node_path}"\n',
        encoding="utf-8",
    )
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "package.json").write_text('{"version":"1.0.0"}', encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=proj, check=True)
    return proj, outside


def _run(proj, *args):
    return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=proj, capture_output=True, text=True,
                          env=dict(os.environ, PYTHONIOENCODING="utf-8"))


@pytest.mark.parametrize("bad", ["../outside", "/etc", "a/../../outside"])
def test_저장소_밖_경로는_거부하고_파일을_건드리지_않는다(tmp_path, bad):
    proj, outside = _project(tmp_path, bad)
    r = _run(proj, "set", "9.9.9")
    assert r.returncode != 0
    assert "project_paths" in (r.stderr + r.stdout)
    assert (outside / "package.json").read_text(encoding="utf-8") == '{"version":"1.0.0"}'


def test_심볼릭_링크로_저장소_밖을_가리켜도_거부한다(tmp_path):
    proj, outside = _project(tmp_path, "link")
    os.symlink(outside, proj / "link")
    r = _run(proj, "set", "9.9.9")
    assert r.returncode != 0
    assert (outside / "package.json").read_text(encoding="utf-8") == '{"version":"1.0.0"}'


def test_저장소_안_서브폴더는_정상_동작한다(tmp_path):
    proj, _ = _project(tmp_path, "client")
    (proj / "client").mkdir()
    (proj / "client" / "package.json").write_text('{"version":"1.0.0"}', encoding="utf-8")
    r = _run(proj, "set", "2.0.0")
    assert r.returncode == 0, r.stderr
    assert '"2.0.0"' in (proj / "client" / "package.json").read_text(encoding="utf-8")
