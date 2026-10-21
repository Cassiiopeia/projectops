# scripts/tests/test_deploy_status_verdicts.py
"""deploy-status: 막힌 대기는 stuck 으로, conflict 는 dirty 만, --wait 는 도구 안에서 폴링 (#945)."""
import datetime as dt
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills" / "pro-changelog-deploy" / "scripts"
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("deploy_status", SCRIPTS / "deploy_status.py")
deploy_status = importlib.util.module_from_spec(spec)
sys.modules["deploy_status"] = deploy_status
spec.loader.exec_module(deploy_status)


def _pr(age_seconds, mergeable_state="clean", merged=False, body="## Summary by CodeRabbit\nx"):
    created = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=age_seconds)
    return {"number": 7, "state": "open", "merged": merged, "mergeable_state": mergeable_state,
            "body": body, "head_sha": "h", "url": "u", "created_at": created.isoformat()}


def _args(wait=0):
    return SimpleNamespace(owner="o", repo="r", pr=7, base="main", head=None, wait=wait)


def _patch(monkeypatch, pr, runs, repo_queued_runs=()):
    monkeypatch.setattr(deploy_status, "get_pull_detail", lambda *a: pr)
    monkeypatch.setattr(deploy_status, "get_branch_head", lambda *a: "b")
    monkeypatch.setattr(deploy_status, "resolve_pr_runs", lambda *a: {"runs": runs})
    monkeypatch.setattr(deploy_status, "list_runs", lambda *a, **k: list(repo_queued_runs))


RELEASE_RUN = {"name": "x", "path": ".github/workflows/PROJECT-COMMON-RELEASE-CHANGELOG.yaml",
               "status": "completed", "conclusion": "success", "url": "ru"}


def test_대기열_지연은_waiting_for_workflow_이고_PR_닫기를_권하지_않는다(monkeypatch):
    # 실사고 (#970): queued 를 "워크플로우 없음" 으로 보고 PR 을 닫았다 다시 열라고 권함
    queued_run = {**RELEASE_RUN, "status": "queued", "conclusion": None}
    for runs, repo_queue in (([queued_run], ()), ([], ({"run_id": 1},))):
        _patch(monkeypatch, _pr(4000), runs, repo_queue)
        out = deploy_status._deploy_status_once(_args(), "pat")
        assert out["verdict"] == "waiting_for_workflow"
        assert "--wait" in out["next"] and "do not close or reopen the PR" in out["next"]


def test_옛_head_SHA_의_실패한_RELEASE_run_은_workflow_failed(monkeypatch):
    # 실사고 (#970): head SHA 가 바뀌어 이전 run 을 못 찾고 workflow=null 로 30분 대기
    failed_old_run = {**RELEASE_RUN, "conclusion": "failure", "url": "https://run/1",
                      "head_sha": "old", "is_current_head": False}
    _patch(monkeypatch, _pr(4000), [failed_old_run])
    out = deploy_status._deploy_status_once(_args(), "pat")
    assert out["verdict"] == "workflow_failed" and out["workflow"]["run_url"] == "https://run/1"
    assert "https://run/1" in out["summary"]


def test_머지되면_next_가_보고서와_완료처리를_안내한다(monkeypatch):
    _patch(monkeypatch, _pr(30, merged=True), [RELEASE_RUN])
    next_hint = deploy_status._deploy_status_once(_args(), "pat")["next"]
    assert "pro-report" in next_hint and "finish-issue" in next_hint


def test_resolve_pr_runs_는_head_브랜치의_옛_SHA_run_도_최신순으로_찾는다(monkeypatch):
    from common import gh_client
    from common.github_rest import actions
    pr = {"head": {"sha": "new", "ref": "develop"}, "created_at": "2026-10-21T00:00:00Z"}
    old_run = {"id": 1, "head_sha": "old", "created_at": "2026-10-21T00:05:00Z", "pull_requests": [{"number": 7}]}
    other_pr_run = {"id": 2, "head_sha": "x", "created_at": "2026-10-21T00:06:00Z", "pull_requests": [{"number": 8}]}
    new_run = {"id": 3, "head_sha": "new", "created_at": "2026-10-21T00:09:00Z", "pull_requests": []}

    def fake_request(method, url, payload, pat, **kwargs):
        if "/pulls/" in url:
            return pr
        if "head_sha=" in url:
            return {"workflow_runs": [new_run]}
        return {"workflow_runs": [new_run, other_pr_run, old_run]}

    monkeypatch.setattr(gh_client, "_request", fake_request)
    runs = actions.resolve_pr_runs("o", "r", 7, "pat")["runs"]
    assert [run["run_id"] for run in runs] == [3, 1]
    assert [run["is_current_head"] for run in runs] == [True, False]


def test_오래_대기했는데_현재_head_에서_돈_워크플로우가_없으면_stuck(monkeypatch):
    _patch(monkeypatch, _pr(4000), [])
    out = deploy_status._deploy_status_once(_args(), "pat")
    assert out["verdict"] == "stuck" and out["stuck_reason"] == "no_workflow_on_head"
    assert out["pr"]["age_seconds"] >= 4000


def test_워크플로우는_끝났는데_머지가_안_되면_stuck(monkeypatch):
    _patch(monkeypatch, _pr(4000), [RELEASE_RUN])
    assert deploy_status._deploy_status_once(_args(), "pat")["stuck_reason"] == "workflow_done_not_merged"


def test_갓_만든_PR_의_대기는_정상_대기(monkeypatch):
    _patch(monkeypatch, _pr(300), [RELEASE_RUN])
    assert deploy_status._deploy_status_once(_args(), "pat")["verdict"] == "waiting_for_automerge"


def test_conflict_는_dirty_만_blocked_behind_는_따로(monkeypatch):
    for state, verdict in (("dirty", "conflict"), ("blocked", "blocked"), ("behind", "behind")):
        _patch(monkeypatch, _pr(30, mergeable_state=state), [])
        assert deploy_status._deploy_status_once(_args(), "pat")["verdict"] == verdict


def test_wait_는_도구_안에서_폴링하고_끝나면_멈춘다(monkeypatch, capsys):
    seq = iter(["waiting_for_automerge", "waiting_for_automerge", "merged"])
    monkeypatch.setattr(deploy_status, "get_github_pat", lambda o, r: "pat")
    monkeypatch.setattr(deploy_status, "_deploy_status_once", lambda a, p: {"verdict": next(seq)})
    sleeps = []
    import time
    monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))
    deploy_status.cmd_deploy_status(_args(wait=300))
    assert len(sleeps) == 2 and '"merged"' in capsys.readouterr().out


# ── 릴리스 보조 (#945) ──

def _release_tools():
    spec = importlib.util.spec_from_file_location("release_tools", SCRIPTS / "release_tools.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_릴리스_노트_표식_블록을_도구가_씌운다():
    tools = _release_tools()
    wrapped, did = tools.wrap_release_notes("* **새 기능**\n  * 추가")
    assert did and wrapped.startswith("<!-- This is an auto-generated comment") and "## Summary by CodeRabbit" in wrapped
    assert tools.wrap_release_notes("") == ("", False)  # 맡기기(빈 본문)는 그대로
    already = "## Summary by CodeRabbit\nx"
    assert tools.wrap_release_notes(already) == (already, False)


def test_sync_base_와_branches_check(tmp_path, monkeypatch):
    import subprocess
    # CI 러너에는 git 작성자 설정이 없다 — 병합 커밋을 만들 수 있게 환경으로 준다
    for key, value in (("GIT_AUTHOR_NAME", "a"), ("GIT_AUTHOR_EMAIL", "a@a"),
                       ("GIT_COMMITTER_NAME", "a"), ("GIT_COMMITTER_EMAIL", "a@a")):
        monkeypatch.setenv(key, value)
    tools = _release_tools()
    origin = tmp_path / "o.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    repo = tmp_path / "r"
    repo.mkdir()
    g = lambda *a: subprocess.run(["git", "-c", "user.name=a", "-c", "user.email=a@a", *a], cwd=repo, check=True,
                                  capture_output=True, text=True)
    g("init", "-q", "-b", "main")
    g("remote", "add", "origin", str(origin))
    g("commit", "-q", "--allow-empty", "-m", "base")
    g("push", "-q", "origin", "main")
    g("checkout", "-q", "-b", "develop")
    g("push", "-q", "origin", "develop")
    # 아직 차이가 없으면 경고
    assert "nothing to release" in tools.branches_check(repo, "develop", "main")["warning"]
    g("commit", "-q", "--allow-empty", "-m", "dev work")
    g("push", "-q", "origin", "develop")
    assert tools.branches_check(repo, "develop", "main")["ahead_count"] == 1
    # main 에만 있는 커밋을 develop 으로 병합
    g("checkout", "-q", "main")
    g("commit", "-q", "--allow-empty", "-m", "version bump")
    g("push", "-q", "origin", "main")
    g("checkout", "-q", "develop")
    args = SimpleNamespace(project_root=str(repo), head="develop", base="main")
    import io, json, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        tools.cmd_sync_base(args)
    assert json.loads(buf.getvalue())["code"] == "merged"
