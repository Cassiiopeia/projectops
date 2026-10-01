# scripts/tests/test_create_pr_retry.py
"""push 직후 일시적 422(head invalid)만 재시도하고 다른 오류는 즉시 올린다 (#724)."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from common import gh_client  # noqa: E402

HEAD_INVALID = "Validation Failed (PullRequest/head/invalid)"


@pytest.fixture
def no_wait(monkeypatch):
    waits = []
    monkeypatch.setattr(gh_client, "_sleep", lambda s: waits.append(s))
    return waits


def _call():
    return gh_client.create_pull_request("o", "r", "t", "b", "o:br", "main", "pat")


def test_일시적_head_invalid_는_재시도해_성공한다(monkeypatch, no_wait):
    seq = [gh_client.GitHubAPIError(422, HEAD_INVALID), gh_client.GitHubAPIError(422, HEAD_INVALID),
           {"number": 7, "html_url": "u"}]

    def fake(method, url, data, pat, raw=False):
        r = seq.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    monkeypatch.setattr(gh_client, "_request", fake)
    assert _call() == {"number": 7, "url": "u"}
    assert len(no_wait) == 2


def test_계속_실패하면_재시도_횟수만큼만_기다리고_오류를_올린다(monkeypatch, no_wait):
    calls = []

    def fake(method, url, data, pat, raw=False):
        calls.append(1)
        raise gh_client.GitHubAPIError(422, HEAD_INVALID)

    monkeypatch.setattr(gh_client, "_request", fake)
    with pytest.raises(gh_client.GitHubAPIError):
        _call()
    assert len(calls) == gh_client._PR_HEAD_RETRIES + 1


def test_다른_422_는_재시도하지_않는다(monkeypatch, no_wait):
    calls = []

    def fake(method, url, data, pat, raw=False):
        calls.append(1)
        raise gh_client.GitHubAPIError(422, "Validation Failed (PullRequest/base/invalid)")

    monkeypatch.setattr(gh_client, "_request", fake)
    with pytest.raises(gh_client.GitHubAPIError):
        _call()
    assert len(calls) == 1 and no_wait == []
