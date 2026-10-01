"""common.http 의 URL 인코딩 회귀 테스트 (#703).

한글·공백이 든 URL 을 그대로 urllib 에 넘기면 ascii 인코딩 오류로 요청 자체가 실패했다.
"""
import http.server
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common import http as chttp  # noqa: E402


def test_encode_url_quotes_korean_and_space_but_keeps_existing_escapes():
    got = chttp.encode_url("http://h:1/검색 a/%EA%B2%80?q=한글 x&k=%20")
    assert got == "http://h:1/%EA%B2%80%EC%83%89%20a/%EA%B2%80?q=%ED%95%9C%EA%B8%80%20x&k=%20"


def test_encode_url_leaves_plain_ascii_untouched():
    u = "https://example.com/a/b?x=1&y=2#frag"
    assert chttp.encode_url(u) == u


def test_request_sends_korean_path_and_query():
    seen = []

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append(self.path)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        r = chttp.request("GET", f"http://127.0.0.1:{srv.server_port}/검색 a?q=한글")
    finally:
        srv.shutdown()
    assert r["ok"] and r["status"] == 200, r
    assert seen == ["/%EA%B2%80%EC%83%89%20a?q=%ED%95%9C%EA%B8%80"]
