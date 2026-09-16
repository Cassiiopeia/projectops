"""후속 워크플로우 탐색 규칙 테스트 (이슈 #551).

핵심 회귀 지점: 무엇을 깨우느냐보다 **무엇을 깨우지 않느냐**가 중요하다.
VERSION-CONTROL을 깨우면 릴리스 직후 안전망이 발동해 버전이 한 번 더 올라간다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dispatch_downstream import parse_triggers, scan


def write(tmp_path, name, content):
    d = tmp_path / ".github" / "workflows"
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(content, encoding="utf-8")
    return d


PUSH_MAIN_DISPATCH = """name: X
on:
  push:
    branches: ["main"]
  workflow_dispatch:
jobs:
  a:
    runs-on: ubuntu-latest
"""

PUSH_MAIN_ONLY = """name: X
on:
  push:
    branches: ["main"]
jobs:
  a:
    runs-on: ubuntu-latest
"""


# ── 트리거 파싱 ───────────────────────────────────────────────────────
def test_push_branch_and_dispatch_detected():
    info = parse_triggers(PUSH_MAIN_DISPATCH, "main")
    assert info["on_push_branch"] is True
    assert info["workflow_dispatch"] is True


def test_dispatch_absent_detected():
    info = parse_triggers(PUSH_MAIN_ONLY, "main")
    assert info["on_push_branch"] is True
    assert info["workflow_dispatch"] is False


def test_other_branch_is_not_target():
    info = parse_triggers(PUSH_MAIN_DISPATCH, "develop")
    assert info["on_push_branch"] is False


def test_pull_request_only_is_not_push_target():
    text = 'name: X\non:\n  pull_request_target:\n    branches: ["main"]\n  workflow_dispatch:\n'
    info = parse_triggers(text, "main")
    assert info["on_push_branch"] is False


def test_commented_trigger_is_ignored():
    # 주석 안의 예시 트리거를 실제 트리거로 오인하면 엉뚱한 워크플로우를 깨운다.
    text = 'name: X\n#on:\n#  push:\n#    branches: ["main"]\non:\n  schedule:\n    - cron: "0 0 * * *"\n'
    info = parse_triggers(text, "main")
    assert info["on_push_branch"] is False


def test_multiple_branches_in_list():
    text = 'name: X\non:\n  push:\n    branches: ["main", "release"]\n  workflow_dispatch:\n'
    assert parse_triggers(text, "release")["on_push_branch"] is True
    assert parse_triggers(text, "main")["on_push_branch"] is True


# ── 탐색·제외 규칙 ────────────────────────────────────────────────────
def test_scan_splits_targets_and_unreachable(tmp_path):
    d = write(tmp_path, "A.yaml", PUSH_MAIN_DISPATCH)
    write(tmp_path, "B.yaml", PUSH_MAIN_ONLY)
    got = scan("main", d)
    assert got["targets"] == ["A.yaml"]
    assert got["unreachable"] == ["B.yaml"]


def test_version_control_is_never_dispatched(tmp_path):
    # 릴리스 직후 깨우면 안전망이 발동해 버전이 이중 증가한다.
    # dispatch에는 github.event.before가 없어 가드가 HEAD^..HEAD만 보므로,
    # 후속 커밋이 먼저 들어오면 version.yml 변경이 범위에서 빠져 가드가 뚫린다.
    d = write(tmp_path, "PROJECT-COMMON-VERSION-CONTROL.yaml", PUSH_MAIN_DISPATCH)
    got = scan("main", d)
    assert got["targets"] == []
    assert got["unreachable"] == []


def test_self_is_excluded(tmp_path):
    d = write(tmp_path, "PROJECT-COMMON-RELEASE-CHANGELOG.yaml", PUSH_MAIN_DISPATCH)
    assert scan("main", d)["targets"] == []


def test_non_workflow_files_ignored(tmp_path):
    d = write(tmp_path, "A.yaml", PUSH_MAIN_DISPATCH)
    (d / "notes.txt").write_text("push: main", encoding="utf-8")
    assert scan("main", d)["targets"] == ["A.yaml"]


def test_yml_extension_supported(tmp_path):
    d = write(tmp_path, "A.yml", PUSH_MAIN_DISPATCH)
    assert scan("main", d)["targets"] == ["A.yml"]


def test_missing_dir_is_empty(tmp_path):
    got = scan("main", tmp_path / "nope")
    assert got == {"targets": [], "unreachable": []}


def test_targets_are_sorted(tmp_path):
    d = write(tmp_path, "B.yaml", PUSH_MAIN_DISPATCH)
    write(tmp_path, "A.yaml", PUSH_MAIN_DISPATCH)
    assert scan("main", d)["targets"] == ["A.yaml", "B.yaml"]
