"""#675 회귀 테스트: version_manager가 CRLF 파일을 LF로 바꿔 전체 diff를 만들던 결함.

#682(줄바꿈·들여쓰기 보존)와 같은 원인이라 수정은 함께 들어갔고,
여기서는 #675 보고서의 재현 절차(CRLF package.json / build.gradle, 버전 한 줄만 바뀌어야 함)를 그대로 고정한다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_version_manager_fixes import run_vm, write  # noqa: E402


def test_package_json_crlf_only_version_line_changes(tmp_path):
    # #675 재현: CRLF package.json은 version 한 줄만 바뀌어야 한다
    original = '{\r\n  "name": "x",\r\n  "version": "1.0.0"\r\n}\r\n'
    write(tmp_path / "version.yml", 'version: "1.0.0"\nversion_code: 1\nproject_types: ["node"]\n')
    write(tmp_path / "package.json", original)
    rc, out, err = run_vm(tmp_path, "set", "1.0.5")
    assert rc == 0, err
    assert (tmp_path / "package.json").read_bytes() == original.replace("1.0.0", "1.0.5").encode()


def test_build_gradle_crlf_only_version_line_changes(tmp_path):
    original = 'version = "3.0.0"\r\nplugins{}\r\n'
    write(tmp_path / "version.yml", 'version: "3.0.0"\nversion_code: 1\nproject_types: ["spring"]\n')
    write(tmp_path / "build.gradle", original)
    rc, out, err = run_vm(tmp_path, "set", "3.0.1")
    assert rc == 0, err
    assert (tmp_path / "build.gradle").read_bytes() == original.replace("3.0.0", "3.0.1").encode()
