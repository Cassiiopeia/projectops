# scripts/tests/test_release_branches.py
"""changelog_cli의 릴리스 브랜치·provider 읽기 테스트 (#456).

head = deploy_branch(폴백 develop), base = default_branch(폴백 main),
changelog provider = options.changelog.provider(폴백 commit — #566 에서 기본 사다리가 바뀌었다).
version.yml을 정규식으로만 읽어(폐쇄망·yaml 무의존) SSOT에서 브랜치를 해석함을 검증한다.
"""
import importlib.util
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_CLI_PATH = _ROOT / "skills" / "pro-changelog-deploy" / "scripts" / "changelog_cli.py"
_spec = importlib.util.spec_from_file_location("changelog_cli", _CLI_PATH)
changelog_cli = importlib.util.module_from_spec(_spec)
sys.modules["changelog_cli"] = changelog_cli
_spec.loader.exec_module(changelog_cli)

_read_branches = changelog_cli._read_release_branches


def _write_vy(tmp_path, body):
    (tmp_path / "version.yml").write_text(body, encoding="utf-8")
    return tmp_path


def test_reads_deploy_and_default_branch(tmp_path):
    _write_vy(tmp_path, 'version: "1.0.0"\nmetadata:\n  default_branch: "trunk"\n  deploy_branch: "release"\n')
    b = _read_branches(tmp_path)
    assert b["head"] == "release"   # deploy_branch
    assert b["base"] == "trunk"     # default_branch


def test_falls_back_to_develop_main(tmp_path):
    # deploy_branch·default_branch 둘 다 없으면 develop→main 폴백
    _write_vy(tmp_path, 'version: "1.0.0"\nmetadata:\n  last_updated: "x"\n')
    b = _read_branches(tmp_path)
    assert b["head"] == "develop"
    assert b["base"] == "main"


def test_default_branch_only(tmp_path):
    # default_branch만 있으면 base는 그 값, head는 develop 폴백
    _write_vy(tmp_path, 'version: "1.0.0"\nmetadata:\n  default_branch: "main"\n')
    b = _read_branches(tmp_path)
    assert b["head"] == "develop"
    assert b["base"] == "main"


def test_reads_changelog_provider(tmp_path):
    _write_vy(tmp_path,
              'version: "1.0.0"\nmetadata:\n  template:\n    options:\n      changelog:\n        provider: "commit"\n')
    b = _read_branches(tmp_path)
    assert b["provider"] == "commit"


def test_provider_fallback_is_commit(tmp_path):
    """폴백은 commit 이다. #566 이후 기본 사다리가 commit 이라, coderabbit 으로 두면
    이 스킬만 'CodeRabbit 을 기다리는 레포'로 잘못 판정한다."""
    _write_vy(tmp_path, 'version: "1.0.0"\nmetadata:\n  default_branch: "main"\n')
    b = _read_branches(tmp_path)
    assert b["provider"] == "commit"


def test_no_version_yml_all_fallback(tmp_path):
    b = _read_branches(tmp_path)
    assert b == {"head": "develop", "base": "main", "provider": "commit"}
