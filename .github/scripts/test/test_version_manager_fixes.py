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


# ── #678: version.yml 갱신 실패를 성공으로 출력하지 않는다 ───────────────
def _yml(version_line, extra='version_code: 5\nproject_types: ["basic"]\n'):
    return f"{version_line}\n{extra}"


def test_set_updates_v_prefixed_version(tmp_path):
    write(tmp_path / "version.yml", _yml('version: "v1.2.3"'))
    rc, out, err = run_vm(tmp_path, "set", "2.0.0")
    assert rc == 0, err
    assert (tmp_path / "version.yml").read_text(encoding="utf-8").startswith('version: "2.0.0"\n')


def test_get_reads_v_prefixed_version(tmp_path):
    write(tmp_path / "version.yml", _yml('version: "v1.2.3"'))
    rc, out, err = run_vm(tmp_path, "get")
    assert rc == 0, err
    assert out.strip() == "1.2.3"


@pytest.mark.parametrize("line", ['version: "1.2.3"   ', 'version: "1.2.3-beta.1"', "version: '1.2.3'", "version: 1.2.3"])
def test_increment_updates_unusual_version_lines(tmp_path, line):
    write(tmp_path / "version.yml", _yml(line))
    rc, out, err = run_vm(tmp_path, "increment")
    assert rc == 0, err
    assert out.strip() == "1.2.4"
    text = (tmp_path / "version.yml").read_text(encoding="utf-8")
    assert text.startswith('version: "1.2.4"\n'), text
    assert "version_code: 6" in text


def test_increment_fails_when_version_line_not_updatable(tmp_path):
    # 값 뒤에 주석도 아닌 잡텍스트가 붙어 패턴이 안 맞는 경우: 성공 로그 대신 실패해야 한다.
    original = _yml('version: "1.2.3" junk')
    write(tmp_path / "version.yml", original)
    rc, out, err = run_vm(tmp_path, "increment")
    assert rc == 1
    assert out.strip() == ""                      # 새 버전을 stdout으로 내보내면 릴리스가 잘못 나간다
    assert "갱신하지 못했습니다" in err
    assert "업데이트 완료" not in err
    # version_code도 올라가면 안 된다 (버전 파일과 어긋남)
    assert (tmp_path / "version.yml").read_bytes() == original.encode()


def test_set_fails_when_version_line_not_updatable(tmp_path):
    original = _yml('version: "1.2.3" junk')
    write(tmp_path / "version.yml", original)
    rc, out, err = run_vm(tmp_path, "set", "2.0.0")
    assert rc == 1
    assert out.strip() == ""
    assert "설정 완료" not in err


@pytest.mark.parametrize("cmd", [("get",), ("increment", "--bump", "major"), ("set", "2.0.0"), ("sync",)])
def test_missing_version_key_is_an_error(tmp_path, cmd):
    original = 'project_types: ["basic"]\n'
    write(tmp_path / "version.yml", original)
    rc, out, err = run_vm(tmp_path, *cmd)
    assert rc == 1
    assert out.strip() == ""
    assert "version:" in err
    assert (tmp_path / "version.yml").read_bytes() == original.encode()


def test_bom_before_version_key_is_handled_and_preserved(tmp_path):
    write(tmp_path / "version.yml", b"\xef\xbb\xbf" + _yml('version: "1.2.3"').encode())
    rc, out, err = run_vm(tmp_path, "increment")
    assert rc == 0, err
    assert out.strip() == "1.2.4"
    raw = (tmp_path / "version.yml").read_bytes()
    assert raw.startswith(b"\xef\xbb\xbfversion: \"1.2.4\"\n")


def test_get_code_works_without_version_key(tmp_path):
    # version_code만 읽는 명령은 version 키가 없어도 동작해야 한다 (기존 계약)
    write(tmp_path / "version.yml", 'version_code: 7\nproject_types: ["basic"]\n')
    rc, out, err = run_vm(tmp_path, "get-code")
    assert rc == 0, err
    assert out.strip() == "7"


# ── #684: version.yml 블록 리스트·따옴표 변형 경로 ───────────────────────
def _node_pkg(tmp_path, sub="web", version="1.0.0"):
    write(tmp_path / sub / "package.json", '{"version": "%s"}\n' % version)


def test_block_list_project_types_is_recognized(tmp_path):
    _node_pkg(tmp_path)
    write(tmp_path / "version.yml", 'version: "1.0.0"\nproject_types:\n  - node\nproject_paths:\n  node: "web"\n')
    rc, out, err = run_vm(tmp_path, "increment")
    assert rc == 0, err
    assert '"version": "1.0.1"' in (tmp_path / "web" / "package.json").read_text(encoding="utf-8")


def test_block_list_with_quotes_and_comments(tmp_path):
    _node_pkg(tmp_path, sub=".")
    write(tmp_path / "version.yml", 'version: "1.0.0"\nproject_types:\n  - "node"  # 서버\n  # 주석 줄\n  - \'basic\'\nother: 1\n')
    rc, out, err = run_vm(tmp_path, "increment")
    assert rc == 0, err
    assert '"version": "1.0.1"' in (tmp_path / "package.json").read_text(encoding="utf-8")


@pytest.mark.parametrize("path_line", ["  node: 'web'", "  node: web", '  node: "web"  # 웹', "  node: web # 웹"])
def test_project_paths_quote_variants(tmp_path, path_line):
    _node_pkg(tmp_path)
    write(tmp_path / "version.yml", f'version: "1.0.0"\nproject_types: ["node"]\nproject_paths:\n{path_line}\n')
    rc, out, err = run_vm(tmp_path, "increment")
    assert rc == 0, err
    assert '"version": "1.0.1"' in (tmp_path / "web" / "package.json").read_text(encoding="utf-8")
    assert "건너뜀" not in err


def test_unsupported_project_types_form_is_an_error(tmp_path):
    original = 'version: "1.0.0"\nproject_types: node\n'
    write(tmp_path / "version.yml", original)
    rc, out, err = run_vm(tmp_path, "increment")
    assert rc == 1
    assert "project_types" in err and "지원하지 않는" in err
    assert (tmp_path / "version.yml").read_bytes() == original.encode()


def test_unsupported_project_paths_form_is_an_error(tmp_path):
    write(tmp_path / "version.yml", 'version: "1.0.0"\nproject_types: ["node"]\nproject_paths: {node: web}\n')
    rc, out, err = run_vm(tmp_path, "get")
    assert rc == 1
    assert "project_paths" in err and "지원하지 않는" in err


# ── #683: package.json BOM·깨진 JSON에서 트레이스백 금지 ─────────────────
YML_NODE = 'version: "1.2.3"\nversion_code: 3\nproject_types: ["node"]\n'
YML_MULTI = 'version: "1.2.3"\nversion_code: 3\nproject_types: ["basic", "node"]\n'


def test_bom_package_json_is_accepted_and_bom_kept(tmp_path):
    write(tmp_path / "version.yml", YML_MULTI)
    write(tmp_path / "package.json", b'\xef\xbb\xbf{"name":"x","version":"1.2.3"}\n')
    rc, out, err = run_vm(tmp_path, "get")
    assert rc == 0, err
    assert "Traceback" not in err
    rc, out, err = run_vm(tmp_path, "set", "1.3.0")
    assert rc == 0, err
    raw = (tmp_path / "package.json").read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf{")
    assert b'"version": "1.3.0"' in raw or b'"version":"1.3.0"' in raw


@pytest.mark.parametrize("cmd", [("get",), ("increment",), ("sync",)])
def test_broken_json_reports_clean_error(tmp_path, cmd):
    write(tmp_path / "version.yml", YML_MULTI)
    write(tmp_path / "package.json", "{bad\n")
    rc, out, err = run_vm(tmp_path, *cmd)
    assert rc == 1
    assert "Traceback" not in err
    assert "package.json" in err and "읽지 못했습니다" in err


def test_broken_json_does_not_leave_half_updated_state(tmp_path):
    # package.json을 못 읽으면 version.yml도 바꾸면 안 된다 (두 파일이 어긋난 채 끝나는 것 방지)
    write(tmp_path / "version.yml", YML_MULTI)
    write(tmp_path / "package.json", "{bad\n")
    rc, out, err = run_vm(tmp_path, "set", "2.0.0")
    assert rc == 1
    assert (tmp_path / "version.yml").read_bytes() == YML_MULTI.encode()


def test_non_object_json_reports_clean_error(tmp_path):
    write(tmp_path / "version.yml", YML_NODE)
    write(tmp_path / "package.json", "[1, 2]\n")
    rc, out, err = run_vm(tmp_path, "set", "2.0.0")
    assert rc == 1
    assert "Traceback" not in err
    assert "package.json" in err


def test_read_only_package_json_reports_clean_error(tmp_path):
    import os
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("root는 읽기 전용 파일에도 쓸 수 있다")
    write(tmp_path / "version.yml", YML_NODE)
    write(tmp_path / "package.json", '{"version": "1.2.3"}\n')
    (tmp_path / "package.json").chmod(0o444)
    try:
        rc, out, err = run_vm(tmp_path, "set", "2.0.0")
    finally:
        (tmp_path / "package.json").chmod(0o644)
    assert rc == 1
    assert "Traceback" not in err
    assert "package.json" in err
