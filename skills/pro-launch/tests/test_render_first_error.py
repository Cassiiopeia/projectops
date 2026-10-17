"""render_failed 의 first_error — 출력 깊숙이 묻힌 첫 컴파일 오류를 앞으로 끌어낸다 (#901).

실제 Flutter 없이 컴파일러 출력 샘플만으로 검증한다.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from pro_launch.commands.render import find_first_error  # noqa: E402

# flutter test 가 임시 렌더 테스트를 컴파일하다 실패할 때의 모양 (import 누락)
_FLUTTER_COMPILE_FAILURE = """\
00:01 +0: loading /repo/client/test/_launch_render/states_test.dart
test/_launch_render/states_test.dart:12:9: Error: Undefined name 'MethodChannel'.
  const channel = MethodChannel('plugins.flutter.io/path_provider');
                  ^^^^^^^^^^^^^
test/_launch_render/states_test.dart:20:5: Error: The getter 'SystemChrome' isn't defined for the class '_State'.
    SystemChrome.setEnabledSystemUIMode(SystemUiMode.manual);
    ^^^^^^^^^^^^
00:03 +0 -1: loading /repo/client/test/_launch_render/states_test.dart [E]
  Failed to load "/repo/client/test/_launch_render/states_test.dart":
  Compilation failed for testPath=/repo/client/test/_launch_render/states_test.dart
00:03 +0 -1: Some tests failed.
"""


def test_dart_compile_error_is_first_line_with_source_context():
    first = find_first_error(_FLUTTER_COMPILE_FAILURE)
    assert first.splitlines() == [
        "test/_launch_render/states_test.dart:12:9: Error: Undefined name 'MethodChannel'.",
        "  const channel = MethodChannel('plugins.flutter.io/path_provider');",
        "                  ^^^^^^^^^^^^^",
    ]


def test_dart_error_wins_over_an_earlier_generic_error_line():
    output = "warning: generic error: noise from a plugin\n" + _FLUTTER_COMPILE_FAILURE
    assert find_first_error(output).startswith("test/_launch_render/states_test.dart:12:9: Error:")


def test_generic_error_line_when_no_dart_error():
    output = ("> Task :app:compileTestJava\n"
              "src/test/java/a/LaunchRenderTest.java:7: error: cannot find symbol\n"
              "    MockMvc mvc;\n"
              "    ^\n"
              "1 error\n")
    assert find_first_error(output).splitlines() == [
        "src/test/java/a/LaunchRenderTest.java:7: error: cannot find symbol",
        "    MockMvc mvc;",
        "    ^",
    ]


def test_typescript_error_code_line_is_found():
    output = "src/x.tsx(3,1): error TS2304: Cannot find name 'render'.\n"
    assert find_first_error(output) == "src/x.tsx(3,1): error TS2304: Cannot find name 'render'."


def test_no_error_line_gives_none():
    # 오류 단어가 콜론 없이 나오거나 다른 단어의 일부면 오류 줄로 보지 않는다
    assert find_first_error("echo boom\n0 errors\non_error: ignored\nSome tests failed.\n") is None


def test_render_failed_puts_buried_first_error_near_top(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    subprocess.run(["git", "init", "-q", str(proj)], check=True)
    # 오류 뒤에 60줄을 붙여 output_tail(끝 40줄)에서 밀려나게 한다
    log = tmp_path / "build.log"
    log.write_text(_FLUTTER_COMPILE_FAILURE + "".join(f"noise line {i}\n" for i in range(60)),
                   encoding="utf-8")
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "HOME": str(tmp_path),
           "SHOT_DIR": str(tmp_path / "shots")}
    completed = subprocess.run(
        [sys.executable, str(SCRIPTS / "launch_cli.py"), "render", "run", "--root", str(proj),
         "--cmd", f"cat '{log}'; exit 1"],
        capture_output=True, text=True, env=env, timeout=120)
    payload = json.loads(completed.stdout.strip().splitlines()[-1])
    keys = list(payload)

    assert payload["code"] == "render_failed" and payload["ok"] is False, payload
    assert "MethodChannel" not in payload["output_tail"], "샘플이 output_tail 에 묻히지 않았다"
    assert payload["first_error"].startswith(
        "test/_launch_render/states_test.dart:12:9: Error: Undefined name 'MethodChannel'.")
    assert "MethodChannel" in payload["summary"]
    assert keys.index("first_error") < keys.index("output_tail")
    # 공통 4필드(ok·code·summary·next) 바로 뒤 (#898)
    assert keys.index("first_error") == keys.index("next") + 1
    assert "first_error" in payload["next"]
