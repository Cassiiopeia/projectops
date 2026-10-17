"""GitHub REST 호출 공통 (#914): 마커 댓글 갱신, redirect 시 토큰 제거."""
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import github_api  # noqa: E402


def test_마커_댓글은_다음_쪽까지_찾아_갱신하고_없으면_만든다():
    calls = []
    first_page = [{"id": n, "body": "다른 댓글"} for n in range(100)]

    def fake_request(method, url, token, payload=None):
        calls.append((method, url))
        if method == "GET":
            return first_page if url.endswith("&page=1") else [{"id": 777, "body": "<!-- M -->\n이전"}]
        return {"id": 999}

    assert github_api.upsert_marker_comment("o/r", 1, "t", "새 본문", "<!-- M -->",
                                            request_function=fake_request) == ("updated", 777)
    assert ("PATCH", f"{github_api.API_ROOT}/repos/o/r/issues/comments/777") in calls

    calls.clear()
    first_page = []
    assert github_api.upsert_marker_comment("o/r", 1, "t", "본문", "<!-- M -->",
                                            request_function=fake_request) == ("created", 999)
    assert calls[-1] == ("POST", f"{github_api.API_ROOT}/repos/o/r/issues/1/comments")


def test_redirect_대상에는_토큰을_넘기지_않는다():
    original = urllib.request.Request("https://api.github.com/x", headers={"Authorization": "Bearer t"})
    handler = github_api.StripAuthorizationOnRedirect()
    redirected = handler.redirect_request(original, None, 302, "Found", {}, "https://blob.example/x")
    assert "Authorization" not in redirected.headers
    assert redirected.get_header("Authorization") is None
