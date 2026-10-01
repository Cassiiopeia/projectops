# scripts/tests/test_cli_github.py
"""pro-issue 통합(#464)으로 github_cli에 추가된 서브커맨드의 판정/JSON 조립 검증.

gh_client 함수를 mock하고 cmd_* 핸들러를 in-process로 호출해 verdict·멱등·경고 로직을 본다.
실제 GitHub API를 때리지 않는다.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))
if str(ROOT / "skills/pro-github/scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "skills/pro-github/scripts"))

from common.cli_parser import run_cli  # noqa: E402
from common.gh_client import GitHubAPIError  # noqa: E402
from github_cli import build_parser  # noqa: E402


def _run(monkeypatch, argv, **mocks):
    """github_cli 모듈의 함수를 mock하고 argv로 CLI를 실행한 뒤 (rc, json) 반환."""
    import github_cli
    monkeypatch.setattr(github_cli, "get_github_pat", lambda o, r: "mock_pat")
    for name, fn in mocks.items():
        monkeypatch.setattr(github_cli, name, fn)
    import io
    buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buf)
    rc = run_cli(build_parser(), argv)
    return rc, json.loads(buf.getvalue().strip().splitlines()[-1])


# --- 담당자 add: 누락 경고 ---

def test_add_assignees_warns_missing(monkeypatch):
    rc, out = _run(
        monkeypatch,
        ["add-assignees", "o", "r", "5", "alice,bob"],
        add_assignees=lambda o, r, n, a, pat: {
            "number": n, "url": "u", "assignees": ["alice"],  # bob 누락
        },
    )
    assert rc == 0
    assert out["assignees"] == ["alice"]
    assert "bob" in out["assignee_warning"]


# --- 라벨 remove: 없으면 멱등 ---

def test_remove_label_idempotent_on_404(monkeypatch):
    def _raise(o, r, n, name, pat):
        raise GitHubAPIError(404, "Label does not exist")
    rc, out = _run(monkeypatch, ["remove-label", "o", "r", "5", "없는라벨"],
                   remove_issue_label=_raise)
    assert rc == 0  # 멱등 — 실패 아님
    assert out["code"] == "label_not_present"


def test_remove_label_success(monkeypatch):
    rc, out = _run(monkeypatch, ["remove-label", "o", "r", "5", "작업전"],
                   remove_issue_label=lambda o, r, n, name, pat: {"labels": ["작업중"]})
    assert rc == 0
    assert out["labels"] == ["작업중"]


# --- 라벨 add: 레포에 없는 라벨 경고 ---

def test_add_labels_warns_unknown(monkeypatch):
    rc, out = _run(monkeypatch, ["add-labels", "o", "r", "5", "작업중,헛것"],
                   add_issue_labels=lambda o, r, n, labels, pat: ["작업중"])
    assert rc == 0
    assert out["labels"] == ["작업중"]
    assert "헛것" in out["label_warning"]


# --- 라벨 set: 전부 걸러지면 기존 라벨 보존 (#698) ---

def test_set_labels_all_unknown_fails_without_clearing(monkeypatch):
    rc, out = _run(monkeypatch, ["set-labels", "o", "r", "5", "작업중"],
                   set_issue_labels=lambda o, r, n, labels, pat: {
                       "labels": ["작업전"], "skipped": ["작업중"], "unchanged": True})
    assert rc == 1
    assert out["ok"] is False and out["code"] == "no_valid_labels"
    assert out["labels"] == ["작업전"]  # 기존 라벨 그대로


def test_set_labels_partial_unknown_warns(monkeypatch):
    rc, out = _run(monkeypatch, ["set-labels", "o", "r", "5", "작업중,헛것"],
                   set_issue_labels=lambda o, r, n, labels, pat: {
                       "labels": ["작업중"], "skipped": ["헛것"], "unchanged": False})
    assert rc == 0
    assert "헛것" in out["label_warning"]


def test_create_issue_warns_dropped_labels(monkeypatch, tmp_path):
    body = tmp_path / "b.md"
    body.write_text("본문", encoding="utf-8")
    rc, out = _run(monkeypatch, ["create-issue", "o", "r", "제목", str(body), "헛것"],
                   create_issue=lambda *a, **k: {
                       "number": 1, "url": "u", "title": "t", "assignees": [],
                       "skipped_labels": ["헛것"]})
    assert rc == 0
    assert "헛것" in out["label_warning"]


# --- PR merge: verdict 분기 ---

def test_merge_pr_success(monkeypatch):
    rc, out = _run(monkeypatch, ["merge-pr", "o", "r", "12"],
                   merge_pull_request=lambda o, r, n, pat, merge_method, commit_title, commit_message: {
                       "sha": "abc", "merged": True, "message": "merged"})
    assert rc == 0
    assert out["verdict"] == "merged"


def test_merge_pr_not_mergeable_405(monkeypatch):
    def _raise(o, r, n, pat, merge_method, commit_title, commit_message):
        raise GitHubAPIError(405, "not mergeable")
    rc, out = _run(monkeypatch, ["merge-pr", "o", "r", "12"], merge_pull_request=_raise)
    assert rc == 1
    assert out["verdict"] == "not_mergeable"
    assert out["code"] == "github_api_405"


def test_merge_pr_sha_mismatch_409(monkeypatch):
    def _raise(o, r, n, pat, merge_method, commit_title, commit_message):
        raise GitHubAPIError(409, "sha mismatch")
    rc, out = _run(monkeypatch, ["merge-pr", "o", "r", "12"], merge_pull_request=_raise)
    assert out["verdict"] == "sha_mismatch"


# --- get-pr: mergeable_state → verdict ---

def _pr(state="open", merged=False, mstate="clean"):
    return {"number": 1, "state": state, "merged": merged, "mergeable_state": mstate,
            "body": "", "head_sha": "s", "url": "u"}


def test_get_pr_verdict_mergeable(monkeypatch):
    rc, out = _run(monkeypatch, ["get-pr", "o", "r", "1"],
                   get_pull_detail=lambda o, r, n, pat: _pr(mstate="clean"))
    assert out["verdict"] == "mergeable"


def test_get_pr_verdict_blocked(monkeypatch):
    rc, out = _run(monkeypatch, ["get-pr", "o", "r", "1"],
                   get_pull_detail=lambda o, r, n, pat: _pr(mstate="dirty"))
    assert out["verdict"] == "blocked"


def test_get_pr_verdict_computing_on_unknown(monkeypatch):
    rc, out = _run(monkeypatch, ["get-pr", "o", "r", "1"],
                   get_pull_detail=lambda o, r, n, pat: _pr(mstate=None))
    assert out["verdict"] == "computing"


def test_get_pr_verdict_merged(monkeypatch):
    rc, out = _run(monkeypatch, ["get-pr", "o", "r", "1"],
                   get_pull_detail=lambda o, r, n, pat: _pr(state="closed", merged=True))
    assert out["verdict"] == "merged"


# --- 댓글 수정/삭제 ---

def test_edit_comment(monkeypatch, tmp_path):
    body = tmp_path / "c.md"
    body.write_text("새 본문", encoding="utf-8")
    rc, out = _run(monkeypatch, ["edit-comment", "o", "r", "777", str(body)],
                   update_comment=lambda o, r, cid, b, pat: {"id": cid, "url": "u"})
    assert rc == 0
    assert out["id"] == 777


def test_delete_comment(monkeypatch):
    rc, out = _run(monkeypatch, ["delete-comment", "o", "r", "777"],
                   delete_comment=lambda o, r, cid, pat: {"comment_id": cid, "status": "deleted"})
    assert rc == 0
    assert out["comment_id"] == 777
    assert out["status"] == "deleted"


# --- 이슈 상태 alias ---

def test_close_issue(monkeypatch):
    captured = {}

    def _upd(o, r, n, pat, **kw):
        captured.update(kw)
        return {"number": n, "url": "u", "title": "t"}
    rc, out = _run(monkeypatch, ["close-issue", "o", "r", "5"], update_issue=_upd)
    assert rc == 0
    assert captured["state"] == "closed"
