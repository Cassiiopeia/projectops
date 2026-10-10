"""pro-changelog-deploy 스킬의 provider 판정 테스트 (#821).

스킬 CLI(detect-release-context)와 RELEASE-CHANGELOG 워크플로우가 provider 미설정을
서로 다르게 해석해(스킬 commit / 워크플로우 coderabbit) 판단이 갈렸다.
규칙: 명시값 → (.coderabbit.yaml 있으면) coderabbit → commit. 종료된 github-ai는 commit.
워크플로우 쪽 같은 규칙은 test_changelog_providers.py가 본다.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
_CLI = ROOT / "skills" / "pro-changelog-deploy" / "scripts" / "changelog_cli.py"
_spec = importlib.util.spec_from_file_location("changelog_cli_821", _CLI)
changelog_cli = importlib.util.module_from_spec(_spec)
sys.modules["changelog_cli_821"] = changelog_cli
_spec.loader.exec_module(changelog_cli)


def _vy(provider=None):
    body = 'version: "1.0.0"\n'
    if provider:
        body += f'metadata:\n  template:\n    options:\n      changelog:\n        provider: "{provider}"\n'
    return body


@pytest.mark.parametrize("provider,coderabbit_yaml,expected", [
    (None, False, "commit"),          # 둘 다 없음 → commit
    (None, True, "coderabbit"),       # 미설정 + .coderabbit.yaml → coderabbit (기존 동작 보존)
    ("gemini", True, "gemini"),       # 명시값이 우선
    ("commit", True, "commit"),
    ("github-ai", False, "commit"),   # 종료된 서비스 → commit 흡수
])
def test_provider_resolution(tmp_path, provider, coderabbit_yaml, expected):
    (tmp_path / "version.yml").write_text(_vy(provider), encoding="utf-8")
    if coderabbit_yaml:
        (tmp_path / ".coderabbit.yaml").write_text("reviews: {}\n", encoding="utf-8")
    assert changelog_cli._read_release_branches(tmp_path)["provider"] == expected


def test_no_version_yml_with_coderabbit_yaml(tmp_path):
    """version.yml이 없어도 .coderabbit.yaml 규칙은 적용된다."""
    (tmp_path / ".coderabbit.yaml").write_text("reviews: {}\n", encoding="utf-8")
    assert changelog_cli._read_release_branches(tmp_path)["provider"] == "coderabbit"
