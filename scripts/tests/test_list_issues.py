"""list_issues: label filter, pagination, PR exclusion."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common import gh_client  # noqa: E402


def _issue(n, labels=(), pr=False):
    d = {"number": n, "title": f"t{n}", "html_url": f"u{n}", "state": "open", "labels": [{"name": x} for x in labels]}
    if pr:
        d["pull_request"] = {}
    return d


def test_excludes_pull_requests_and_reports_labels(monkeypatch):
    monkeypatch.setattr(gh_client, "_request", lambda *a, **k: [_issue(1, ["a"]), _issue(2, pr=True)])
    got = gh_client.list_issues("o", "r", "pat")
    assert [i["number"] for i in got] == [1]
    assert got[0]["labels"] == ["a"]


def test_labels_are_sent_url_encoded(monkeypatch):
    seen = []
    monkeypatch.setattr(gh_client, "_request", lambda m, url, *a, **k: seen.append(url) or [])
    gh_client.list_issues("o", "r", "pat", labels="작업완료,x")
    assert "labels=%EC%9E%91%EC%97%85%EC%99%84%EB%A3%8C,x" in seen[0]


def test_limit_zero_follows_pagination(monkeypatch):
    pages = {1: [_issue(i) for i in range(100)], 2: [_issue(100), _issue(101)]}
    monkeypatch.setattr(gh_client, "_request", lambda m, url, *a, **k: pages[int(url.rsplit("page=", 1)[1])])
    assert len(gh_client.list_issues("o", "r", "pat", limit=0)) == 102


def test_limit_caps_result(monkeypatch):
    monkeypatch.setattr(gh_client, "_request", lambda *a, **k: [_issue(i) for i in range(50)])
    assert len(gh_client.list_issues("o", "r", "pat", limit=10)) == 10
