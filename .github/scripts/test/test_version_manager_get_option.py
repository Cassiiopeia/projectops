"""version_manager.py get-option — 워크플로가 version.yml 옵션을 읽는 단일 경로 (#832)."""
import subprocess
import sys
import textwrap
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "version_manager.py"


def run(tmp_path, yml, *args):
    (tmp_path / "version.yml").write_text(textwrap.dedent(yml), encoding="utf-8")
    p = subprocess.run([sys.executable, str(SCRIPT), "get-option", *args],
                       cwd=tmp_path, capture_output=True, text=True)
    return p.returncode, p.stdout.strip()


BASE = """\
version: "1.0.0"
metadata:
  template:
    options:
      semver_auto: false
      label_style: "ko"
      issue_helper:
        semver_auto: true
"""


def test_reads_bool_and_quoted(tmp_path):
    assert run(tmp_path, BASE, "semver_auto") == (0, "false")
    assert run(tmp_path, BASE, "label_style") == (0, "ko")


def test_missing_key_returns_default(tmp_path):
    assert run(tmp_path, BASE, "close_on_release", "true") == (0, "true")
    assert run(tmp_path, BASE, "close_on_release") == (0, "")


def test_nested_same_name_is_not_picked(tmp_path):
    # issue_helper 안의 semver_auto(true)가 아니라 직계 값(false)을 읽어야 한다
    assert run(tmp_path, BASE, "semver_auto", "true")[1] == "false"


def test_key_outside_options_is_ignored(tmp_path):
    yml = """\
    version: "1.0.0"
    semver_auto: false
    metadata:
      template:
        options:
          label_style: en
    """
    assert run(tmp_path, yml, "semver_auto", "true")[1] == "true"


def test_trailing_comment_and_crlf(tmp_path):
    yml = BASE.replace("semver_auto: false", "semver_auto: false  # 끔").replace("\n", "\r\n")
    (tmp_path / "version.yml").write_bytes(yml.encode())
    p = subprocess.run([sys.executable, str(SCRIPT), "get-option", "semver_auto"],
                       cwd=tmp_path, capture_output=True, text=True)
    assert p.stdout.strip() == "false"


def test_requires_key(tmp_path):
    assert run(tmp_path, BASE)[0] == 1


# ── #851: 점 경로, 순서와 무관한 직계 판정, get-types ─────────────────────
def test_nested_key_before_direct_key_is_not_picked(tmp_path):
    yml = """\
    version: "1.0.0"
    metadata:
      template:
        options:
          issue_helper:
            semver_auto: true
          semver_auto: false
    """
    assert run(tmp_path, yml, "semver_auto", "true")[1] == "false"


def test_dotted_path_reads_nested_block(tmp_path):
    yml = """\
    version: "1.0.0"
    metadata:
      template:
        options:
          changelog:
            provider: "gemini"
            base_url: "http://h:11434/#v1"
          provider: wrong
    """
    assert run(tmp_path, yml, "changelog.provider") == (0, "gemini")
    assert run(tmp_path, yml, "changelog.base_url") == (0, "http://h:11434/#v1"), "따옴표 안의 # 은 주석이 아니다"
    assert run(tmp_path, yml, "changelog.model", "x") == (0, "x")


def test_block_scalar_content_is_not_a_key(tmp_path):
    yml = """\
    version: "1.0.0"
    metadata:
      template:
        options:
          notes: |
            semver_auto: false
          label_style: en
    """
    assert run(tmp_path, yml, "semver_auto", "true")[1] == "true"
    assert run(tmp_path, yml, "label_style")[1] == "en"


def _types(tmp_path, yml):
    (tmp_path / "version.yml").write_text(textwrap.dedent(yml), encoding="utf-8")
    p = subprocess.run([sys.executable, str(SCRIPT), "get-types"], cwd=tmp_path, capture_output=True, text=True)
    return p.returncode, p.stdout.strip()


def test_get_types_inline_and_block_list(tmp_path):
    assert _types(tmp_path, 'version: "1.0.0"\nproject_types: ["spring", "react"]\n') == (0, "spring,react")
    # 워크플로의 grep 은 블록 리스트를 못 읽어 빈 값이 됐다
    assert _types(tmp_path, 'version: "1.0.0"\nproject_types:\n  - flutter\n  - "node"  # web\n') == (0, "flutter,node")
    assert _types(tmp_path, 'version: "1.0.0"\n') == (0, "")
