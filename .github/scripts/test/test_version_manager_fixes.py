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


# ── #675·#682: 줄바꿈·들여쓰기·주석 보존, 멱등 ───────────────────────────
import os


def _crlf(s):
    return s.replace("\n", "\r\n")


def _assert_pure_crlf(raw):
    """모든 줄바꿈이 CRLF여야 한다 (맨 LF가 하나도 없어야 함)."""
    assert raw.count(b"\n") == raw.count(b"\r\n"), raw


def _freeze_mtime(path):
    """mtime을 과거로 박아 두고, 이후 파일이 다시 쓰였는지 mtime 변화로 감지한다."""
    os.utime(path, ns=(1_000_000_000, 1_000_000_000))
    return os.stat(path).st_mtime_ns


def test_version_yml_crlf_preserved_on_increment(tmp_path):
    yml = _crlf('version: "1.2.3"  # 릴리스\nversion_code: 3 # app build number\nproject_types: ["basic"]\nmetadata:\n  template:\n    last_updated: "x"\n')
    write(tmp_path / "version.yml", yml)
    rc, out, err = run_vm(tmp_path, "increment")
    assert rc == 0, err
    raw = (tmp_path / "version.yml").read_bytes()
    _assert_pure_crlf(raw)
    text = raw.decode("utf-8")
    assert 'version: "1.2.4"  # 릴리스\r\n' in text
    assert "version_code: 4 # app build number\r\n" in text


def test_version_yml_crlf_missing_version_code_is_added_with_crlf(tmp_path):
    write(tmp_path / "version.yml", _crlf('version: "1.2.3"\nproject_types: ["basic"]\n'))
    rc, out, err = run_vm(tmp_path, "get-code")
    assert rc == 0, err
    _assert_pure_crlf((tmp_path / "version.yml").read_bytes())


def test_missing_version_code_appended_on_its_own_line(tmp_path):
    # 마지막 줄에 개행이 없어도 version_code가 앞 줄에 붙어 버리면 안 된다
    write(tmp_path / "version.yml", 'project_types: ["basic"]\nversion: "1.2.3"')
    rc, out, err = run_vm(tmp_path, "get-code")
    assert rc == 0, err
    text = (tmp_path / "version.yml").read_text(encoding="utf-8")
    assert 'version: "1.2.3"\nversion_code: 1' in text


@pytest.mark.parametrize("ptype,fname,content,expect", [
    ("flutter", "pubspec.yaml", "name: demo\nversion: 1.2.3+7 # rel\n", "version: 2.0.0+3 # rel\r\n"),
    ("spring", "build.gradle", "plugins {}\nversion = '1.2.3'\n", "version = '2.0.0'\r\n"),
    ("python", "pyproject.toml", '[project]\nname = "x"\nversion = "1.2.3"\n', 'version = "2.0.0"\r\n'),
])
def test_text_files_keep_crlf(tmp_path, ptype, fname, content, expect):
    write(tmp_path / "version.yml", _crlf(f'version: "1.2.3"\nversion_code: 3\nproject_types: ["{ptype}"]\n'))
    write(tmp_path / fname, _crlf(content))
    rc, out, err = run_vm(tmp_path, "set", "2.0.0")
    assert rc == 0, err
    raw = (tmp_path / fname).read_bytes()
    _assert_pure_crlf(raw)
    assert expect in raw.decode("utf-8"), raw


def test_plist_keeps_crlf(tmp_path):
    write(tmp_path / "version.yml", _crlf('version: "1.2.3"\nproject_types: ["react-native"]\n'))
    write(tmp_path / "ios/App/Info.plist", _crlf("<dict>\n<key>CFBundleShortVersionString</key>\n<string>1.2.3</string>\n</dict>\n"))
    rc, out, err = run_vm(tmp_path, "set", "2.0.0")
    assert rc == 0, err
    raw = (tmp_path / "ios/App/Info.plist").read_bytes()
    _assert_pure_crlf(raw)
    assert b"<string>2.0.0</string>" in raw


@pytest.mark.parametrize("original", [
    '{\n\t"name": "x",\n\t"files": ["a", "b"],\n\t"version": "1.2.3"\n}\n',                 # 탭 + 한 줄 배열
    '{\n    "name": "x",\n    "files": ["a", "b"],\n    "version": "1.2.3"\n}\n',           # 4칸
    '{"name":"x","files":["a","b"],"version":"1.2.3"}',                                   # 압축, 끝 개행 없음
    '{\n  "version" :   "1.2.3" ,\n  "dep": {"version": "9.9.9"}\n}\n',                   # 공백 변형 + 중첩 같은 키
])
def test_package_json_format_preserved(tmp_path, original):
    write(tmp_path / "version.yml", 'version: "1.2.3"\nversion_code: 1\nproject_types: ["node"]\n')
    write(tmp_path / "package.json", original)
    rc, out, err = run_vm(tmp_path, "set", "1.2.4")
    assert rc == 0, err
    got = (tmp_path / "package.json").read_text(encoding="utf-8")
    # 값 하나만 바뀌고 나머지 바이트는 동일해야 한다 (중첩 "9.9.9"는 건드리지 않는다)
    assert got == original.replace('"1.2.3"', '"1.2.4"')


def test_package_json_missing_version_key_is_added_keeping_indent(tmp_path):
    write(tmp_path / "version.yml", 'version: "1.2.3"\nversion_code: 1\nproject_types: ["node"]\n')
    write(tmp_path / "package.json", '{\n\t"name": "x"\n}\n')
    rc, out, err = run_vm(tmp_path, "set", "1.2.4")
    assert rc == 0, err
    assert (tmp_path / "package.json").read_text(encoding="utf-8") == '{\n\t"name": "x",\n\t"version": "1.2.4"\n}\n'


def test_app_json_expo_version_only_changes(tmp_path):
    original = '{\n\t"expo": {\n\t\t"name": "x",\n\t\t"version": "1.2.3",\n\t\t"tags": ["a", "b"]\n\t}\n}\n'
    write(tmp_path / "version.yml", 'version: "1.2.3"\nproject_types: ["react-native-expo"]\n')
    write(tmp_path / "app.json", original)
    rc, out, err = run_vm(tmp_path, "set", "1.2.4")
    assert rc == 0, err
    assert (tmp_path / "app.json").read_text(encoding="utf-8") == original.replace('"1.2.3"', '"1.2.4"')


def test_app_json_without_expo_version_is_added(tmp_path):
    write(tmp_path / "version.yml", 'version: "1.2.3"\nproject_types: ["react-native-expo"]\n')
    write(tmp_path / "app.json", '{\n  "expo": {\n    "name": "x"\n  }\n}\n')
    rc, out, err = run_vm(tmp_path, "set", "1.2.4")
    assert rc == 0, err
    assert (tmp_path / "app.json").read_text(encoding="utf-8") == '{\n  "expo": {\n    "name": "x",\n    "version": "1.2.4"\n  }\n}\n'


def test_get_does_not_rewrite_files_in_multitype(tmp_path):
    original = '{\n\t"name": "x",\n\t"files": ["a", "b"],\n\t"version": "1.2.3"\n}\n'
    write(tmp_path / "version.yml", YML_MULTI)
    write(tmp_path / "package.json", original)
    before = _freeze_mtime(tmp_path / "package.json")
    for cmd in ("get", "sync"):
        rc, out, err = run_vm(tmp_path, cmd)
        assert rc == 0, err
    assert (tmp_path / "package.json").read_bytes() == original.encode()
    assert os.stat(tmp_path / "package.json").st_mtime_ns == before   # 쓰기 자체가 없어야 한다


def test_set_same_version_does_not_touch_files(tmp_path):
    write(tmp_path / "version.yml", YML_NODE)
    write(tmp_path / "package.json", '{"version": "1.2.3"}\n')
    b_json = _freeze_mtime(tmp_path / "package.json")
    b_yml = _freeze_mtime(tmp_path / "version.yml")
    rc, out, err = run_vm(tmp_path, "set", "1.2.3")
    assert rc == 0, err
    assert os.stat(tmp_path / "package.json").st_mtime_ns == b_json
    assert os.stat(tmp_path / "version.yml").st_mtime_ns == b_yml


def test_lf_files_stay_lf(tmp_path):
    write(tmp_path / "version.yml", 'version: "1.2.3"\nversion_code: 3\nproject_types: ["basic"]\n')
    rc, out, err = run_vm(tmp_path, "increment")
    assert rc == 0, err
    assert b"\r" not in (tmp_path / "version.yml").read_bytes()


# ── #680: build.gradle 동기화는 프로젝트 version 대입만 고친다 ─────────────
YML_SPRING = 'version: "1.2.3"\nversion_code: 5\nproject_types: ["spring"]\n'

GRADLE_MIXED = """plugins { id 'org.springframework.boot' version '3.2.0' }
ext.kotlin_version = '1.9.0'
ext { libVersion = "2.0.0" }
group = 'com.x'
// version = '0.0.1'
version = '1.2.3'
"""


def test_gradle_only_project_version_line_is_changed(tmp_path):
    write(tmp_path / "version.yml", YML_SPRING)
    write(tmp_path / "build.gradle", GRADLE_MIXED)
    rc, out, err = run_vm(tmp_path, "increment")
    assert rc == 0, err
    got = (tmp_path / "build.gradle").read_text(encoding="utf-8")
    assert got == GRADLE_MIXED.replace("\nversion = '1.2.3'", "\nversion = '1.2.4'")


def test_gradle_double_quote_and_indented_assignment(tmp_path):
    original = 'ext.kotlin_version = "1.9.0"\nallprojects {\n    version = "1.2.3"\n}\n'
    write(tmp_path / "version.yml", YML_SPRING)
    write(tmp_path / "build.gradle", original)
    rc, out, err = run_vm(tmp_path, "set", "1.3.0")
    assert rc == 0, err
    assert (tmp_path / "build.gradle").read_text(encoding="utf-8") == original.replace('    version = "1.2.3"', '    version = "1.3.0"')


def test_gradle_kts_is_synced(tmp_path):
    write(tmp_path / "version.yml", YML_SPRING)
    write(tmp_path / "build.gradle.kts", 'val kotlinVersion = "1.9.0"\nversion = "1.2.3"\n')
    rc, out, err = run_vm(tmp_path, "increment")
    assert rc == 0, err
    assert (tmp_path / "build.gradle.kts").read_text(encoding="utf-8") == 'val kotlinVersion = "1.9.0"\nversion = "1.2.4"\n'


def test_gradle_kts_version_is_read_by_get(tmp_path):
    # 프로젝트 파일이 더 높으면 그 값을 따라 version.yml이 끌어올려진다 (build.gradle과 동일 동작)
    write(tmp_path / "version.yml", YML_SPRING)
    write(tmp_path / "build.gradle.kts", 'version = "1.5.0"\n')
    rc, out, err = run_vm(tmp_path, "get")
    assert rc == 0, err
    assert out.strip() == "1.5.0"


def test_gradle_without_version_assignment_warns(tmp_path):
    write(tmp_path / "version.yml", YML_SPRING)
    write(tmp_path / "build.gradle", "plugins {}\n")
    rc, out, err = run_vm(tmp_path, "set", "2.0.0")
    assert rc == 0
    assert "build.gradle" in err and "version 대입을 찾지 못했습니다" in err
    assert (tmp_path / "build.gradle").read_text(encoding="utf-8") == "plugins {}\n"


def test_spring_without_any_gradle_file_warns(tmp_path):
    write(tmp_path / "version.yml", YML_SPRING)
    rc, out, err = run_vm(tmp_path, "set", "2.0.0")
    assert rc == 0
    assert "build.gradle" in err and "건너뜀" in err


# ── #681: pyproject.toml은 [project]/[tool.poetry] 테이블의 version만 다룬다 ──
YML_PY = 'version: "1.2.3"\nversion_code: 5\nproject_types: ["python"]\n'


def test_pyproject_only_project_table_is_changed(tmp_path):
    original = '[project]\nname = "x"\nversion="1.2.3"\n\n[tool.other.deps]\nversion = "2.0"\n\n[tool.foo]\nversion = "9.9"\n'
    write(tmp_path / "version.yml", YML_PY)
    write(tmp_path / "pyproject.toml", original)
    rc, out, err = run_vm(tmp_path, "increment")
    assert rc == 0, err
    assert (tmp_path / "pyproject.toml").read_text(encoding="utf-8") == original.replace('version="1.2.3"', 'version="1.2.4"')


@pytest.mark.parametrize("line,expect", [
    ("version = '1.2.3'", "version = '1.3.0'"),
    ('  version = "1.2.3"', '  version = "1.3.0"'),
    ('version="1.2.3"', 'version="1.3.0"'),
    ('version = "1.2.3"  # 릴리스', 'version = "1.3.0"  # 릴리스'),
])
def test_pyproject_quote_and_spacing_variants(tmp_path, line, expect):
    write(tmp_path / "version.yml", YML_PY)
    write(tmp_path / "pyproject.toml", f'[project]\nname = "x"\n{line}\n')
    rc, out, err = run_vm(tmp_path, "set", "1.3.0")
    assert rc == 0, err
    assert (tmp_path / "pyproject.toml").read_text(encoding="utf-8") == f'[project]\nname = "x"\n{expect}\n'


def test_pyproject_poetry_table_is_supported(tmp_path):
    original = '[tool.poetry]\nname = "x"\nversion = "1.2.3"\n\n[tool.poetry.dependencies]\npython = "^3.9"\n[tool.other]\nversion = "5.0"\n'
    write(tmp_path / "version.yml", YML_PY)
    write(tmp_path / "pyproject.toml", original)
    rc, out, err = run_vm(tmp_path, "set", "1.3.0")
    assert rc == 0, err
    assert (tmp_path / "pyproject.toml").read_text(encoding="utf-8") == original.replace('version = "1.2.3"', 'version = "1.3.0"')


def test_pyproject_ignores_version_before_project_table(tmp_path):
    original = '[build-system]\nversion = "7.0"\n\n[project]\nname = "x"\nversion = "1.2.3"\n'
    write(tmp_path / "version.yml", YML_PY)
    write(tmp_path / "pyproject.toml", original)
    rc, out, err = run_vm(tmp_path, "set", "1.3.0")
    assert rc == 0, err
    assert (tmp_path / "pyproject.toml").read_text(encoding="utf-8") == original.replace('version = "1.2.3"', 'version = "1.3.0"')


def test_pyproject_without_project_version_warns_and_keeps_file(tmp_path):
    original = '[project]\nname = "x"\ndynamic = ["version"]\n\n[tool.foo]\nversion = "9.9"\n'
    write(tmp_path / "version.yml", YML_PY)
    write(tmp_path / "pyproject.toml", original)
    rc, out, err = run_vm(tmp_path, "set", "1.3.0")
    assert rc == 0
    assert "pyproject.toml" in err and "version을 찾지 못했습니다" in err
    assert (tmp_path / "pyproject.toml").read_text(encoding="utf-8") == original


def test_pyproject_single_quoted_version_is_read_by_get(tmp_path):
    # 작은따옴표라는 이유로 pyproject의 더 높은 버전이 무시되면 안 된다
    write(tmp_path / "version.yml", YML_PY)
    write(tmp_path / "pyproject.toml", "[project]\nname = 'x'\nversion = '1.5.0'\n")
    rc, out, err = run_vm(tmp_path, "get")
    assert rc == 0, err
    assert out.strip() == "1.5.0"


# ── #679: react-native Info.plist 탐색은 Pods·build 등을 제외한다 ──────────
YML_RN = 'version: "1.2.3"\nversion_code: 5\nproject_types: ["react-native"]\n'
PLIST_NEXT = "<dict>\n<key>CFBundleShortVersionString</key>\n<string>%s</string>\n</dict>\n"
PLIST_SAME = "<dict>\n\t<key>CFBundleShortVersionString</key>\t<string>%s</string>\n</dict>\n"


def test_rn_get_ignores_pods_plist(tmp_path):
    write(tmp_path / "version.yml", YML_RN)
    write(tmp_path / "ios/Sample/Info.plist", PLIST_NEXT % "1.2.3")
    write(tmp_path / "ios/Pods/Some/Info.plist", PLIST_NEXT % "10.1.0")
    rc, out, err = run_vm(tmp_path, "get")
    assert rc == 0, err
    assert out.strip() == "1.2.3"
    # 읽기 명령이 version.yml을 Pod 버전으로 덮어쓰면 안 된다
    assert (tmp_path / "version.yml").read_text(encoding="utf-8") == YML_RN


@pytest.mark.parametrize("excluded", ["Pods/X", "build/X", "node_modules/X", "DerivedData/X", "Sample/Pods/X"])
def test_rn_write_skips_excluded_dirs(tmp_path, excluded):
    write(tmp_path / "version.yml", YML_RN)
    write(tmp_path / "ios/Sample/Info.plist", PLIST_NEXT % "1.2.3")
    write(tmp_path / f"ios/{excluded}/Info.plist", PLIST_NEXT % "7.7.7")
    rc, out, err = run_vm(tmp_path, "increment")
    assert rc == 0, err
    assert (tmp_path / "ios/Sample/Info.plist").read_text(encoding="utf-8") == PLIST_NEXT % "1.2.4"
    assert (tmp_path / f"ios/{excluded}/Info.plist").read_text(encoding="utf-8") == PLIST_NEXT % "7.7.7"


def test_rn_same_line_plist_format_is_updated(tmp_path):
    write(tmp_path / "version.yml", YML_RN)
    write(tmp_path / "ios/Sample/Info.plist", PLIST_SAME % "1.2.3")
    write(tmp_path / "ios/Pods/X/Info.plist", PLIST_SAME % "9.0.0")
    rc, out, err = run_vm(tmp_path, "increment")
    assert rc == 0, err
    assert (tmp_path / "ios/Sample/Info.plist").read_text(encoding="utf-8") == PLIST_SAME % "1.2.4"
    assert (tmp_path / "ios/Pods/X/Info.plist").read_text(encoding="utf-8") == PLIST_SAME % "9.0.0"


def test_rn_primary_plist_is_app_not_tests_target(tmp_path):
    # 폴더 이름 정렬로 고르면 AppTests가 먼저 잡힌다
    write(tmp_path / "version.yml", YML_RN)
    write(tmp_path / "ios/AppTests/Info.plist", PLIST_NEXT % "99.0.0")
    write(tmp_path / "ios/Sample/Info.plist", PLIST_NEXT % "1.2.3")
    rc, out, err = run_vm(tmp_path, "get")
    assert rc == 0, err
    assert out.strip() == "1.2.3"


def test_rn_marketing_version_variable_is_kept_and_warned(tmp_path):
    original = PLIST_NEXT % "$(MARKETING_VERSION)"
    write(tmp_path / "version.yml", YML_RN)
    write(tmp_path / "ios/Sample/Info.plist", original)
    rc, out, err = run_vm(tmp_path, "set", "2.0.0")
    assert rc == 0, err
    assert (tmp_path / "ios/Sample/Info.plist").read_text(encoding="utf-8") == original
    assert "MARKETING_VERSION" in err


def test_rn_no_plist_with_version_key_warns(tmp_path):
    write(tmp_path / "version.yml", YML_RN)
    write(tmp_path / "ios/Sample/Info.plist", "<dict>\n</dict>\n")
    rc, out, err = run_vm(tmp_path, "set", "2.0.0")
    assert rc == 0
    assert "CFBundleShortVersionString" in err and "찾지 못했습니다" in err
