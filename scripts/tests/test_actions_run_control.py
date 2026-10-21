# scripts/tests/test_actions_run_control.py
"""actions runs/dispatch/rerun/wait, joblog 정규식·--out, api 통과 경로 (#939)."""
import io
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for extra in ("scripts", "skills/pro-github/scripts"):
    if str(ROOT / extra) not in sys.path:
        sys.path.insert(0, str(ROOT / extra))

from common import gh_client  # noqa: E402
from common.cli_parser import run_cli  # noqa: E402
from common.github_rest import actions as rest_actions  # noqa: E402
from github_cli import build_parser  # noqa: E402

LOG = "step 1 ok\nERROR: build failed\nWarning: deprecated\nall done\nFAILED tests/a.py\n"


def _run(monkeypatch, argv, **mocks):
    import github_cli
    monkeypatch.setattr(github_cli, "get_github_pat", lambda o, r: "pat")
    for name, fn in mocks.items():
        monkeypatch.setattr(github_cli, name, fn)
    buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buf)
    run_cli(build_parser(), argv)
    return json.loads(buf.getvalue().strip().splitlines()[-1])


def test_joblog_grep_은_정규식이고_대소문자를_무시한다(monkeypatch, tmp_path):
    monkeypatch.setattr(gh_client, "_request", lambda *a, **k: LOG)
    out = rest_actions.get_job_log("o", "r", 1, "p", grep="error|failed", tail=10, save_to=str(tmp_path / "log.txt"))
    assert out["regex"] is True and out["matched_count"] == 2
    assert (tmp_path / "log.txt").read_text(encoding="utf-8") == LOG and out["saved_to"].endswith("log.txt")


def test_잘못된_정규식은_글자_그대로_찾는다(monkeypatch):
    monkeypatch.setattr(gh_client, "_request", lambda *a, **k: "a(b\nplain\n")
    out = rest_actions.get_job_log("o", "r", 1, "p", grep="a(b")
    assert out["regex"] is False and out["matched_count"] == 1


def test_로그가_만료되면_log_expired(monkeypatch):
    def gone(*a, **k):
        raise gh_client.GitHubAPIError(410, "Gone")
    out = _run(monkeypatch, ["actions", "joblog", "o", "r", "5"], get_job_log=gone)
    assert out["code"] == "log_expired"


def test_dispatch_는_input_을_key_value_로_받는다(monkeypatch):
    seen = {}
    out = _run(monkeypatch, ["actions", "dispatch", "o", "r", "build.yaml", "--ref", "main", "--input", "a=1", "--input", "b=x=y"],
               dispatch_workflow=lambda o, r, wf, ref, inputs, pat: seen.update(i=inputs, ref=ref) or {"workflow": wf, "ref": ref, "inputs": inputs})
    assert seen["i"] == {"a": "1", "b": "x=y"} and seen["ref"] == "main" and out["ok"] is not False


def test_dispatch_input_형식이_틀리면_거절(monkeypatch):
    out = _run(monkeypatch, ["actions", "dispatch", "o", "r", "build.yaml", "--input", "novalue"],
               dispatch_workflow=lambda *a: {})
    assert out["code"] == "bad_argument"


def test_wait_는_끝날_때까지_도구_안에서_폴링한다(monkeypatch):
    states = iter(["queued", "in_progress", "completed"])
    monkeypatch.setattr(gh_client, "get_run", lambda *a: {"status": next(states), "conclusion": "success", "failed_job_ids": []})
    sleeps = []
    monkeypatch.setattr(gh_client, "_sleep", lambda s: sleeps.append(s))
    out = rest_actions.wait_for_run("o", "r", 1, "p", 300)
    assert out["finished"] is True and len(sleeps) == 2


def test_wait_는_시간이_지나면_끝나지_않았다고_알린다(monkeypatch):
    monkeypatch.setattr(gh_client, "get_run", lambda *a: {"status": "in_progress"})
    monkeypatch.setattr(gh_client, "_sleep", lambda s: None)
    assert rest_actions.wait_for_run("o", "r", 1, "p", 0)["finished"] is False


def test_api_는_이_레포_경로만_받고_쓰기는_플래그가_필요하다(monkeypatch):
    calls = []
    fake = lambda m, url, data, pat: calls.append((m, url)) or {"tag_name": "v1"}
    out = _run(monkeypatch, ["api", "GET", "o", "r", "/repos/o/r/releases/latest"], _request=fake)
    assert out["data"] == {"tag_name": "v1"} and calls == [("GET", "https://api.github.com/repos/o/r/releases/latest")]
    assert _run(monkeypatch, ["api", "GET", "o", "r", "/repos/other/x/issues"], _request=fake)["code"] == "path_out_of_scope"
    assert _run(monkeypatch, ["api", "GET", "o", "r", "/repos/o/r/../../user"], _request=fake)["code"] == "path_out_of_scope"
    assert _run(monkeypatch, ["api", "DELETE", "o", "r", "/repos/o/r/issues/1"], _request=fake)["code"] == "write_requires_flag"
    assert len(calls) == 1
    done = _run(monkeypatch, ["api", "POST", "o", "r", "/repos/o/r/issues/1/labels", "--write"], _request=fake)
    assert done["method"] == "POST" and len(calls) == 2
    # 안전장치: --write 가 있어도 레포 공개 전환·삭제·비밀 쓰기는 막는다
    for method, path in (("PATCH", ""), ("DELETE", "/repos/o/r"), ("PUT", "actions/secrets/X")):
        blocked = _run(monkeypatch, ["api", method, "o", "r", path, "--write"], _request=fake)
        assert blocked["code"] == "repo_admin_blocked", (method, path)
    assert len(calls) == 2


def test_secrets_set_value_file_은_여러_줄을_그대로_읽는다(monkeypatch, tmp_path):
    value_file = tmp_path / "v.env"
    value_file.write_text("A=1\nB=2\n", encoding="utf-8")
    seen = {}
    out = _run(monkeypatch, ["secrets", "set", "o", "r", "BACKEND_ENV", "--value-file", str(value_file)],
               set_secret=lambda o, r, n, v, pat: seen.update(v=v) or {"name": n})
    assert seen["v"] == "A=1\nB=2\n" and out["ok"] is not False


def test_api_는_상대_경로에_레포_접두를_붙이고_잘라도_유효한_JSON_이다(monkeypatch, tmp_path):
    """잘린 문자열 data·경로 접두 재요구 (#969 A4·A5)."""
    calls = []
    many = [{"id": index, "body": "x" * 500} for index in range(100)]
    fake = lambda m, url, data, pat: calls.append(url) or many
    out = _run(monkeypatch, ["api", "GET", "o", "r", "issues/comments", "--out", str(tmp_path / "all.json")], _request=fake)
    assert calls == ["https://api.github.com/repos/o/r/issues/comments"]
    assert isinstance(out["data"], list) and out["truncated_items"] == 100 - len(out["data"]) > 0
    assert len(json.loads((tmp_path / "all.json").read_text(encoding="utf-8"))) == 100
    assert _run(monkeypatch, ["api", "GET", "o", "r", "/rate_limit"], _request=lambda *a: {"rate": {}})["ok"] is True


def test_actions_인자_순서가_틀리면_올바른_순서를_안내한다(monkeypatch):
    """`invalid choice: 'Cassiiopeia'` 로 끝나던 호출 (#969 A6)."""
    out = _run(monkeypatch, ["actions", "Cassiiopeia", "projectops", "show-run", "123"])
    assert out["code"] == "bad_args" and out["next"] == "actions show-run Cassiiopeia projectops 123"


def test_joblog_기본_검색은_error_표식만_보고_스크립트_원문은_뺀다(monkeypatch):
    """스크립트 원문의 `error` 글자·브랜치명이 걸려 재시도하던 문제 (#969 A8)."""
    log = ("##[group]Run grep -q error build.log || echo error-branch\n"
           "echo error\n##[endgroup]\nCompiling...\nerror: lib.rs:3 mismatched types\n"
           "##[error]Process completed with exit code 1.\n")
    monkeypatch.setattr(gh_client, "_request", lambda *a, **k: log)
    out = rest_actions.get_job_log("o", "r", 1, "p")
    assert out["mode"] == "error_markers" and not any("grep -q" in line or line == "echo error" for line in out["lines"])
    assert out["lines"][-1].startswith("##[error]") and "error: lib.rs:3 mismatched types" in out["lines"]


def test_joblog_에_run_id_를_넣으면_show_run_으로_안내한다(monkeypatch):
    """run id 를 log_expired 로 오진하던 문제 (#969 A9)."""
    def missing(*a, **k):
        raise gh_client.GitHubAPIError(404, "Not Found")
    out = _run(monkeypatch, ["actions", "joblog", "o", "r", "77"], get_job_log=missing,
               get_run=lambda *a: {"run_id": 77})
    assert out["code"] == "run_id_given" and out["next"].startswith("actions show-run o r 77")
