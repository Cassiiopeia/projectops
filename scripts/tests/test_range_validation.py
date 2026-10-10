# scripts/tests/test_range_validation.py
"""#713: 범위 밖 값과 없는 경로가 여러 CLI 에서 조용히 수용되던 것을 막는다."""
import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from common.cli_parser import run_cli  # noqa: E402


def _load(rel: str, name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run(monkeypatch, mod, argv):
    buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buf)
    rc = run_cli(mod.build_parser(), argv)
    return rc, json.loads(buf.getvalue().strip().splitlines()[-1])


@pytest.fixture
def commit():
    return _load("skills/pro-commit/scripts/commit_cli.py", "commit_cli_713")


@pytest.fixture
def gh():
    return _load("skills/pro-github/scripts/github_cli.py", "github_cli_713")


@pytest.mark.parametrize("cli", ["commit", "gh"])
def test_commit_type_is_validated(monkeypatch, request, cli):
    mod = request.getfixturevalue(cli)
    rc, out = _run(monkeypatch, mod, ["get-commit-template", "제목", "u", "--type", "잘못된"])
    assert rc == 1 and out["code"] == "bad_args"


@pytest.mark.parametrize("ctype", ["fix", "feat", "docs", "chore", "feat!"])
def test_commit_type_valid_values_still_work(monkeypatch, commit, ctype):
    rc, out = _run(monkeypatch, commit, ["get-commit-template", "제목", "u", "--type", ctype])
    assert rc == 0 and f": {ctype} :" in out["template"]


def test_create_branch_name_rejects_bad_date(monkeypatch, gh):
    rc, out = _run(monkeypatch, gh, ["create-branch-name", "x", "664", "--date", "bad"])
    assert rc == 1 and out["code"] == "bad_args"
    rc, out = _run(monkeypatch, gh, ["create-branch-name", "x", "664", "--date", "20261301"])
    assert rc == 1 and out["code"] == "bad_args"  # 실재하지 않는 날짜


def test_create_branch_name_valid_date_still_works(monkeypatch, gh):
    rc, out = _run(monkeypatch, gh, ["create-branch-name", "x", "664", "--date", "20261001"])
    assert rc == 0 and out["branch"] == "20261001_#664_x"


def test_output_path_rejects_unregistered_skill_id():
    from common.paths import resolve_output_path
    r = resolve_output_path("../../../escape", "t")
    assert r["ok"] is False and r["code"] == "unknown_skill_id"


def test_output_path_registered_skill_still_works(monkeypatch):
    from common.paths import resolve_output_path
    monkeypatch.chdir(ROOT)  # 다른 테스트가 cwd 를 바꿔 둬도 저장소 안에서 계산한다
    r = resolve_output_path("report", "t")
    assert "path" in r and "/report/" in r["path"].replace("\\", "/")


def test_detect_release_context_missing_root(monkeypatch, tmp_path):
    mod = _load("skills/pro-changelog-deploy/scripts/changelog_cli.py", "changelog_cli_713")
    rc, out = _run(monkeypatch, mod, ["detect-release-context", "--project-root", str(tmp_path / "없는")])
    assert rc == 1 and out["code"] == "not_found"
