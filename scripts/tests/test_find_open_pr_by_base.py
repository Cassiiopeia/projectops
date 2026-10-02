# scripts/tests/test_find_open_pr_by_base.py
"""deploy PR 탐색이 의존성 봇 PR을 deploy PR로 오인하지 않는지 검증 (#751).

실사고: dependabot 이 main 으로 올린 PR(#748)을 deploy-status 가 "기존 deploy PR"로 집어,
기존 PR 재사용 경로가 그 PR 본문을 릴리스 노트로 덮어쓸 뻔했다.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from common import gh_client  # noqa: E402


def _patch(monkeypatch, items):
    monkeypatch.setattr(gh_client, "_request", lambda m, u, d, p, raw=False: items)
    monkeypatch.setattr(gh_client, "get_pull_detail", lambda o, r, n, p: {"number": n})


def _pr(number, ref):
    return {"number": number, "head": {"ref": ref}}


def test_skips_dependabot_when_head_not_given(monkeypatch):
    _patch(monkeypatch, [_pr(748, "dependabot/github_actions/x"), _pr(742, "develop")])
    assert gh_client.find_open_pr_by_base("o", "r", "main", "pat")["number"] == 742


def test_skips_renovate_too(monkeypatch):
    _patch(monkeypatch, [_pr(9, "renovate/node-20.x"), _pr(7, "develop")])
    assert gh_client.find_open_pr_by_base("o", "r", "main", "pat")["number"] == 7


def test_none_when_only_bot_prs_open(monkeypatch):
    """봇 PR만 열려 있으면 deploy PR 없음(None)이다. 그래야 새 deploy PR을 만든다."""
    _patch(monkeypatch, [_pr(748, "dependabot/npm_and_yarn/y")])
    assert gh_client.find_open_pr_by_base("o", "r", "main", "pat") is None


def test_head_filter_is_exact(monkeypatch):
    _patch(monkeypatch, [_pr(1, "develop"), _pr(2, "release")])
    assert gh_client.find_open_pr_by_base("o", "r", "main", "pat", head="release")["number"] == 2
    assert gh_client.find_open_pr_by_base("o", "r", "main", "pat", head="nope") is None


def test_empty_list_returns_none(monkeypatch):
    _patch(monkeypatch, [])
    assert gh_client.find_open_pr_by_base("o", "r", "main", "pat") is None
