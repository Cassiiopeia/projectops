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
    # 기본은 완료(completed) — 파이프라인 완료 처리가 이유 없이 닫히지 않게 한다 (#819)
    assert captured["state_reason"] == "completed"
    assert out["state_reason"] == "completed"


def test_close_issue_as_not_planned(monkeypatch):
    """취소된 작업은 not_planned 로 닫아 완료와 구분한다 (#819)."""
    captured = {}

    def _upd(o, r, n, pat, **kw):
        captured.update(kw)
        return {"number": n, "url": "u", "title": "t"}
    rc, out = _run(monkeypatch, ["close-issue", "o", "r", "5", "--reason", "not_planned"],
                   update_issue=_upd)
    assert rc == 0
    assert captured["state_reason"] == "not_planned"


def test_close_issue_rejects_unknown_reason(monkeypatch):
    rc, out = _run(monkeypatch, ["close-issue", "o", "r", "5", "--reason", "duplicate"],
                   update_issue=lambda *a, **k: {})
    assert out["ok"] is False


def test_update_issue_sends_state_reason(monkeypatch):
    """state_reason 은 PATCH payload 에 그대로 실려야 GitHub 에 반영된다."""
    from common import gh_client
    sent = {}

    def _req(method, url, data, pat, raw=False):
        sent.update(data or {})
        return {"number": 5, "html_url": "u", "title": "t"}
    monkeypatch.setattr(gh_client, "_request", _req)
    gh_client.update_issue("o", "r", 5, "pat", state="closed", state_reason="not_planned")
    assert sent == {"state": "closed", "state_reason": "not_planned"}


# --- #822: 이슈 문서 경로도 CLI 가 정한다 ---

def _git_repo(path, branch):
    import subprocess
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", branch], cwd=path, check=True)
    return path


def test_issue_output_path_uses_seq_not_branch_issue(tmp_path, monkeypatch):
    """이슈 브랜치 위에서 새 이슈를 만들어도 그 브랜치 번호를 빌리지 않는다."""
    from datetime import date
    proj = _git_repo(tmp_path / "proj", "20261010_#819_다른_이슈")
    monkeypatch.chdir(proj)
    rc, out = _run(monkeypatch, ["get-output-path", "issue", "--title", "❗[Bug][Skills] New issue"])
    assert rc == 0, out
    p = Path(out["path"])
    today = date.today().strftime("%Y%m%d")
    assert p.parent.name == "issue"
    assert p.name == f"{today}_001_New_issue.md", p.name  # 이모지·태그는 파일명에서 빠진다
    assert "819" not in p.name


def test_issue_output_path_default_skill_id(tmp_path, monkeypatch):
    proj = _git_repo(tmp_path / "proj", "develop")
    monkeypatch.chdir(proj)
    rc, out = _run(monkeypatch, ["get-output-path", "--title", "제목"])
    assert rc == 0, out
    assert out["path"].endswith("_001_제목.md")


# --- #699: 전부 실패/바꿀 값 없음을 ok:true 로 보고하지 않는다 ---

def _404(o, r, n, pat):
    raise GitHubAPIError(404, "Not Found")


def test_get_issues_all_failed_is_not_ok(monkeypatch):
    rc, out = _run(monkeypatch, ["get-issues", "o", "r", "99999"], get_issue=_404)
    assert rc == 1
    assert out["ok"] is False and out["code"] == "all_failed"


def test_get_issues_partial_failure_reports_count(monkeypatch):
    def _get(o, r, n, pat):
        if n == 2:
            raise GitHubAPIError(404, "Not Found")
        return {"number": n}
    rc, out = _run(monkeypatch, ["get-issues", "o", "r", "1", "2"], get_issue=_get)
    assert rc == 0
    assert out["failed_count"] == 1
    assert "1개 조회 실패" in out["summary"]


def test_update_issue_nothing_to_update(monkeypatch):
    called = []
    rc, out = _run(monkeypatch, ["update-issue", "o", "r", "4"],
                   update_issue=lambda *a, **k: called.append(1) or {})
    assert rc == 1 and out["code"] == "nothing_to_update"
    assert not called  # PATCH 자체를 보내지 않는다


def test_update_pr_nothing_to_update(monkeypatch):
    called = []
    rc, out = _run(monkeypatch, ["update-pr", "o", "r", "1"],
                   update_pull_request=lambda *a, **k: called.append(1) or {})
    assert rc == 1 and out["code"] == "nothing_to_update"
    assert not called


def test_changelog_update_pr_nothing_to_update(monkeypatch):
    import importlib.util
    path = ROOT / "skills/pro-changelog-deploy/scripts/changelog_cli.py"
    spec = importlib.util.spec_from_file_location("changelog_cli_699", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "get_github_pat", lambda o, r: "mock_pat")
    called = []
    monkeypatch.setattr(mod, "update_pull_request", lambda *a, **k: called.append(1) or {})
    import io
    buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buf)
    rc = run_cli(mod.build_parser(), ["update-pr", "o", "r", "1"])
    out = json.loads(buf.getvalue().strip().splitlines()[-1])
    assert rc == 1 and out["code"] == "nothing_to_update"
    assert not called


# --- #701: upload-image 태그 공백 / delete-image 비숫자 입력은 bad_args ---

def test_upload_image_tag_with_space_is_bad_args(monkeypatch):
    rc, out = _run(monkeypatch, ["upload-image", "o", "r", "a.png", "--tag", "qa sweep tag"])
    assert rc == 1
    assert out["code"] == "bad_args"


def test_delete_image_non_numeric_is_bad_args(monkeypatch):
    rc, out = _run(monkeypatch, ["delete-image", "o", "r", "abc"])
    assert rc == 1
    assert out["code"] == "bad_args"


def test_delete_image_numeric_still_works(monkeypatch):
    seen = []
    rc, out = _run(monkeypatch, ["delete-image", "o", "r", "123"],
                   delete_release_asset=lambda o, r, i, pat: seen.append(i))
    assert rc == 0 and out["asset_id"] == 123 and seen == [123]
