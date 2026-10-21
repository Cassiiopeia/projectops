# scripts/tests/test_transient_retry_finish.py
"""일시 오류 재시도, 댓글 조정, finish-issue 부분 성공 (#941)."""
import io
import json
import sys
import urllib.error
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for extra in ("scripts", "skills/pro-github/scripts"):
    if str(ROOT / extra) not in sys.path:
        sys.path.insert(0, str(ROOT / extra))

from common import gh_client  # noqa: E402
from common.cli_parser import run_cli  # noqa: E402
from common.github_rest import transport  # noqa: E402
from github_cli import build_parser  # noqa: E402


@pytest.fixture
def no_wait(monkeypatch):
    waits = []
    monkeypatch.setattr(gh_client, "_sleep", lambda s: waits.append(s))
    return waits


def _sender(monkeypatch, outcomes):
    calls = []

    def fake(method, url, data, pat, raw):
        calls.append(method)
        result = outcomes.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(transport, "_send_once", fake)
    return calls


def test_조회는_5xx_를_재시도해_성공한다(monkeypatch, no_wait):
    calls = _sender(monkeypatch, [transport.GitHubAPIError(502, "bad gateway"), {"ok": 1}])
    assert transport._request("GET", "u", None, "p") == {"ok": 1}
    assert len(calls) == 2 and no_wait == [1]


def test_4xx_는_재시도하지_않는다(monkeypatch, no_wait):
    calls = _sender(monkeypatch, [transport.GitHubAPIError(404, "nf")])
    with pytest.raises(transport.GitHubAPIError):
        transport._request("GET", "u", None, "p")
    assert len(calls) == 1 and no_wait == []


def test_POST_는_5xx_여도_재시도하지_않는다(monkeypatch, no_wait):
    calls = _sender(monkeypatch, [transport.GitHubAPIError(500, "boom")])
    with pytest.raises(transport.GitHubAPIError):
        transport._request("POST", "u", {"a": 1}, "p")
    assert len(calls) == 1


def test_네트워크_단절도_멱등_호출이면_재시도한다(monkeypatch, no_wait):
    calls = _sender(monkeypatch, [urllib.error.URLError("down"), urllib.error.URLError("down"), {"ok": 1}])
    assert transport._request("PATCH", "u", {}, "p") == {"ok": 1} and no_wait == [1, 3]


def test_댓글_POST_가_500_이어도_실제로_올라갔으면_조정해_돌려준다(monkeypatch):
    import datetime as dt
    from common.github_rest import issues
    now = dt.datetime.now(dt.timezone.utc).isoformat()

    def fake(method, url, data, pat, raw=False):
        if method == "POST":
            raise transport.GitHubAPIError(500, "boom")
        return [{"id": 9, "html_url": "u9", "body": "hello\n", "created_at": now}]

    monkeypatch.setattr(gh_client, "_request", fake)
    assert issues.add_comment("o", "r", 1, "hello", "p") == {"id": 9, "url": "u9", "reconciled": True}


def test_댓글_POST_가_500_이고_안_올라갔으면_오류를_그대로_올린다(monkeypatch):
    from common.github_rest import issues

    def fake(method, url, data, pat, raw=False):
        if method == "POST":
            raise transport.GitHubAPIError(500, "boom")
        return []

    monkeypatch.setattr(gh_client, "_request", fake)
    with pytest.raises(transport.GitHubAPIError):
        issues.add_comment("o", "r", 1, "hello", "p")


# pro-report 출력 틀 제목이 있는 댓글
_REPORT_COMMENT = {"id": 1, "body": "# 제목\n\n## 개요\n요약\n\n## 변경 사항\n- a"}


def _finish(monkeypatch, set_result, update_error=None, labels=("bug", "작업중"), comments=(_REPORT_COMMENT,)):
    import github_cli
    monkeypatch.setattr(github_cli, "get_github_pat", lambda o, r: "pat")
    monkeypatch.setattr(github_cli, "get_issue_labels", lambda *a: list(labels))
    monkeypatch.setattr(github_cli, "get_issue_comments", lambda *a: list(comments))
    seen = {}
    monkeypatch.setattr(github_cli, "set_issue_labels", lambda o, r, n, wanted, pat: seen.update(w=wanted) or set_result)

    def update(*a, **k):
        if update_error:
            raise update_error
        return {"number": 5, "url": "u"}

    monkeypatch.setattr(github_cli, "update_issue", update)
    buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buf)
    run_cli(build_parser(), ["finish-issue", "o", "r", "5"])
    return json.loads(buf.getvalue().strip().splitlines()[-1]), seen


def test_finish_issue_는_상태_라벨만_바꾸고_닫는다(monkeypatch):
    out, seen = _finish(monkeypatch, {"labels": ["bug", "status: done"]})
    assert seen["w"] == ["bug", "status: done"] and out["code"] == "finished" and out["ok"] is True
    assert out["warnings"] == []


def test_finish_issue_는_보고서_댓글이_없으면_경고한다(monkeypatch):
    """보고서 없이 40개를 일괄로 닫은 일 (#969 A24): 막지 않고 warnings 로 알린다."""
    out, _ = _finish(monkeypatch, {"labels": ["status: done"]}, comments=({"id": 2, "body": "확인했습니다"},))
    assert out["ok"] is True and len(out["warnings"]) == 1 and "보고서" in out["warnings"][0]


def test_finish_issue_라벨_실패여도_닫고_부분_성공을_알린다(monkeypatch):
    out, _ = _finish(monkeypatch, {"unchanged": True, "labels": []})
    assert out["code"] == "finished_partial" and out["failed_steps"] == ["labels"]
    assert [s["step"] for s in out["steps"]] == ["labels", "close"] and out["steps"][1]["ok"] is True


def test_finish_issue_닫기가_실패하면_그_단계만_실패로_보고한다(monkeypatch):
    out, _ = _finish(monkeypatch, {"labels": ["status: done"]}, update_error=gh_client.GitHubAPIError(500, "x"))
    assert out["failed_steps"] == ["close"]


def test_pro_report_로_올린_보고서는_제목_언어와_상관없이_보고서로_본다(monkeypatch, tmp_path):
    """영문 제목 보고서를 올려도 finish-issue 가 '보고서 없음' 경고를 내던 문제 (#969 표식 미기록)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "report_cli_marker", Path(__file__).resolve().parents[2] / "skills" / "pro-report" / "scripts" / "report_cli.py")
    report_cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(report_cli)
    posted = {}
    monkeypatch.setattr(report_cli, "get_github_pat", lambda o, r: "pat")
    monkeypatch.setattr(report_cli, "add_comment", lambda o, r, n, body, pat: posted.update(body=body) or {"id": 9})
    report_file = tmp_path / "report.md"
    report_file.write_text("### 📌 Summary\n\nEnglish report\n", encoding="utf-8")
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    run_cli(report_cli.build_parser(), ["add-comment", "o", "r", "5", str(report_file)])
    out, _ = _finish(monkeypatch, {"labels": ["status: done"]}, comments=({"id": 9, "body": posted["body"]},))
    assert out["warnings"] == []
