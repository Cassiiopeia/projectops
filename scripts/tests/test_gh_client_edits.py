# scripts/tests/test_gh_client_edits.py
"""pro-issue 통합(#464)으로 gh_client에 추가된 편집 함수의 요청 조립 검증.

_request를 mock해 (method, url, body)가 GitHub API 스펙대로 만들어지는지 본다.
- 댓글 수정/삭제: issues/comments/{id} (issue_number 없음)
- 라벨 제거: URL에 quote된 이름 (한글)
- 담당자 remove: DELETE + body
- PR merge: merge_method 등 payload
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from common import gh_client  # noqa: E402


def _capture(monkeypatch, return_value):
    """_request 호출 인자를 캡처하고 return_value를 돌려준다."""
    calls = []

    def _fake(method, url, data, pat, raw=False):
        calls.append({"method": method, "url": url, "data": data})
        return return_value
    monkeypatch.setattr(gh_client, "_request", _fake)
    return calls


def test_update_comment_uses_comment_id_path(monkeypatch):
    calls = _capture(monkeypatch, {"id": 9, "html_url": "u"})
    gh_client.update_comment("o", "r", 9, "새 본문", "pat")
    c = calls[0]
    assert c["method"] == "PATCH"
    assert c["url"].endswith("/repos/o/r/issues/comments/9")  # issue_number 없음
    assert c["data"] == {"body": "새 본문"}


def test_delete_comment_no_body(monkeypatch):
    calls = _capture(monkeypatch, {})
    gh_client.delete_comment("o", "r", 9, "pat")
    c = calls[0]
    assert c["method"] == "DELETE"
    assert c["url"].endswith("/issues/comments/9")
    assert c["data"] is None  # 삭제는 body 없음


def test_remove_issue_label_encodes_korean(monkeypatch):
    calls = _capture(monkeypatch, [{"name": "작업중"}])
    result = gh_client.remove_issue_label("o", "r", 5, "작업 전", "pat")
    c = calls[0]
    assert c["method"] == "DELETE"
    # 공백·한글이 URL 인코딩되어야 한다
    assert "/issues/5/labels/" in c["url"]
    assert "%EC%9E%91%EC%97%85" in c["url"]  # '작업' UTF-8 %-encoding
    assert "%20" in c["url"] or "작업 전" not in c["url"]  # 공백 인코딩
    assert result["labels"] == ["작업중"]


def test_set_issue_labels_filters_unknown(monkeypatch):
    monkeypatch.setattr(gh_client, "list_labels", lambda o, r, pat: ["작업중", "긴급"])
    calls = _capture(monkeypatch, [{"name": "작업중"}])
    gh_client.set_issue_labels("o", "r", 5, ["작업중", "없는것"], "pat")
    c = calls[0]
    assert c["method"] == "PUT"
    assert c["data"] == {"labels": ["작업중"]}  # 없는것 필터됨


def test_set_issue_labels_all_unknown_keeps_existing(monkeypatch):
    """#698: 요청 라벨이 전부 레포에 없으면 PUT 하지 않아 기존 라벨이 보존된다."""
    monkeypatch.setattr(gh_client, "list_labels", lambda o, r, pat: ["작업전", "긴급"])
    calls = _capture(monkeypatch, [{"name": "작업전"}])
    result = gh_client.set_issue_labels("o", "r", 5, ["작업중"], "pat")
    assert [c["method"] for c in calls] == ["GET"]  # PUT 없음
    assert result["unchanged"] is True
    assert result["labels"] == ["작업전"]
    assert result["skipped"] == ["작업중"]


def test_set_issue_labels_explicit_empty_still_clears(monkeypatch):
    """빈 입력을 명시한 전체 제거는 기존 계약대로 동작한다."""
    calls = _capture(monkeypatch, [])
    result = gh_client.set_issue_labels("o", "r", 5, [], "pat")
    assert calls[0]["method"] == "PUT" and calls[0]["data"] == {"labels": []}
    assert result["unchanged"] is False


def test_add_issue_labels_empty_input_reports_actual_labels(monkeypatch):
    calls = _capture(monkeypatch, [{"name": "작업전"}, {"name": "긴급"}])
    assert gh_client.add_issue_labels("o", "r", 5, [], "pat") == ["작업전", "긴급"]
    assert [c["method"] for c in calls] == ["GET"]


def test_create_issue_returns_skipped_labels(monkeypatch):
    monkeypatch.setattr(gh_client, "list_labels", lambda o, r, pat: ["작업전"])
    _capture(monkeypatch, {"number": 1, "html_url": "u", "title": "t", "assignees": []})
    result = gh_client.create_issue("o", "r", "t", "b", ["작업전", "없는것"], "pat")
    assert result["skipped_labels"] == ["없는것"]


def test_add_assignees_returns_applied(monkeypatch):
    calls = _capture(monkeypatch, {"number": 5, "html_url": "u",
                                   "assignees": [{"login": "alice"}]})
    result = gh_client.add_assignees("o", "r", 5, ["alice", "bob"], "pat")
    c = calls[0]
    assert c["method"] == "POST"
    assert c["url"].endswith("/issues/5/assignees")
    assert c["data"] == {"assignees": ["alice", "bob"]}
    assert result["assignees"] == ["alice"]  # 실제 반영된 것만


def test_remove_assignees_delete_with_body(monkeypatch):
    calls = _capture(monkeypatch, {"number": 5, "html_url": "u", "assignees": []})
    gh_client.remove_assignees("o", "r", 5, ["alice"], "pat")
    c = calls[0]
    assert c["method"] == "DELETE"
    assert c["data"] == {"assignees": ["alice"]}  # DELETE인데 body 있음


def test_merge_pull_request_payload(monkeypatch):
    calls = _capture(monkeypatch, {"sha": "abc", "merged": True, "message": "ok"})
    result = gh_client.merge_pull_request("o", "r", 12, "pat",
                                          merge_method="squash", commit_title="T")
    c = calls[0]
    assert c["method"] == "PUT"
    assert c["url"].endswith("/pulls/12/merge")
    assert c["data"]["merge_method"] == "squash"
    assert c["data"]["commit_title"] == "T"
    assert "commit_message" not in c["data"]  # None은 payload에서 제외
    assert result["merged"] is True


# --- #700: 422 errors 배열을 메시지에 포함 + timeout ---

def _http_error(code, payload: bytes):
    import io
    import urllib.error
    return urllib.error.HTTPError("https://api.example.test/x", code, "err", {}, io.BytesIO(payload))


class _FakeOpener:
    def __init__(self, exc):
        self.exc = exc
        self.timeouts = []

    def open(self, req, timeout=None):
        self.timeouts.append(timeout)
        raise self.exc


def test_request_422_includes_errors_detail(monkeypatch):
    import json
    import pytest
    body = json.dumps({
        "message": "Validation Failed",
        "errors": [{"resource": "Issue", "field": "title", "code": "missing_field"}],
    }).encode()
    opener = _FakeOpener(_http_error(422, body))
    monkeypatch.setattr(gh_client, "_opener", opener)
    with pytest.raises(gh_client.GitHubAPIError) as ei:
        gh_client._request("POST", "https://api.example.test/x", {}, "pat")
    assert ei.value.status_code == 422
    assert "Validation Failed" in str(ei.value)
    assert "Issue/title/missing_field" in str(ei.value)  # 원인이 보인다


def test_request_without_errors_keeps_plain_message(monkeypatch):
    import pytest
    opener = _FakeOpener(_http_error(404, b'{"message": "Not Found"}'))
    monkeypatch.setattr(gh_client, "_opener", opener)
    with pytest.raises(gh_client.GitHubAPIError) as ei:
        gh_client._request("GET", "https://api.example.test/x", None, "pat")
    assert str(ei.value) == "GitHub API 404: Not Found"


def test_request_has_timeout(monkeypatch):
    import pytest
    opener = _FakeOpener(_http_error(500, b"oops"))
    monkeypatch.setattr(gh_client, "_opener", opener)
    with pytest.raises(gh_client.GitHubAPIError):
        gh_client._request("GET", "https://api.example.test/x", None, "pat")
    assert opener.timeouts and opener.timeouts[0]  # 무한 대기 금지
