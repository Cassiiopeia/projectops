# scripts/tests/test_cli_output_options.py
"""공통 CLI 계약: 앞머리 4키, --brief/--field, bad_args 의 usage·did_you_mean, commit 한 방 (#940)."""
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "skills" / "pro-commit" / "scripts"))

from common import emit as emit_module  # noqa: E402
from common.cli_parser import JSONArgumentParser, run_cli  # noqa: E402
from common.emit import emit  # noqa: E402


@pytest.fixture(autouse=True)
def reset_options():
    emit_module.configure_output()
    yield
    emit_module.configure_output()


def _capture(monkeypatch):
    buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buf)
    return buf


def _parser():
    parser = JSONArgumentParser(prog="demo")
    sub = parser.add_subparsers(dest="command", required=True)
    one = sub.add_parser("list-runs")
    one.add_argument("--n", type=int, default=1)
    one.set_defaults(func=lambda a: emit({"items": [{"id": 7, "name": "x"}], "title": "T", "extra": "e"}))
    return parser


def test_응답은_ok_code_summary_next_순서로_시작한다(monkeypatch):
    buf = _capture(monkeypatch)
    emit({"zzz": 1, "next": "n", "ok": True})
    assert list(json.loads(buf.getvalue()))[:4] == ["ok", "code", "summary", "next"]


def test_brief_는_안내_키와_목록의_최소_행만_남긴다(monkeypatch):
    """목록까지 지우면 다시 불러야 했다 (#969 A20): 행은 번호·제목·상태 식별 키만."""
    buf = _capture(monkeypatch)
    run_cli(_parser(), ["list-runs", "--brief"])
    out = json.loads(buf.getvalue())
    assert set(out) == {"ok", "code", "summary", "next", "items"} and out["items"] == [{"id": 7, "name": "x"}]


def test_field_는_그_값만_글자_그대로_준다(monkeypatch):
    buf = _capture(monkeypatch)
    assert run_cli(_parser(), ["list-runs", "--field", "title"]) == 0
    assert buf.getvalue() == "T\n"
    buf = _capture(monkeypatch)
    run_cli(_parser(), ["list-runs", "--field", "items.0.id"])
    assert buf.getvalue() == "7\n"


def test_없는_field_는_가능한_키를_알려준다(monkeypatch):
    buf = _capture(monkeypatch)
    assert run_cli(_parser(), ["list-runs", "--field", "nope"]) == 1
    out = json.loads(buf.getvalue())
    assert out["code"] == "field_not_found" and "items" in out["available_keys"]


def test_fields_표기도_받고_없으면_중첩_경로를_제안하며_summary_는_문자열이다(monkeypatch):
    """--field/--fields 표기 차이·최상위 키만 제안·summary null (#969 A21·A22)."""
    buf = _capture(monkeypatch)
    parser = _parser()
    parser._subparsers._group_actions[0].choices["list-runs"].set_defaults(
        func=lambda a: emit({"issue": {"labels": ["bug"]}}))
    assert run_cli(parser, ["list-runs", "--fields", "labels"]) == 1
    out = json.loads(buf.getvalue())
    assert out["code"] == "field_not_found" and "issue.labels" in out["did_you_mean"]
    buf = _capture(monkeypatch)
    run_cli(parser, ["list-runs"])
    assert json.loads(buf.getvalue())["summary"] == "done"


def test_오류_응답에는_field_를_적용하지_않는다(monkeypatch):
    buf = _capture(monkeypatch)
    parser = _parser()
    parser._subparsers._group_actions[0].choices["list-runs"].set_defaults(
        func=lambda a: emit({"ok": False, "code": "boom", "error": "원인"}))
    run_cli(parser, ["list-runs", "--field", "title"])
    assert json.loads(buf.getvalue())["error"] == "원인"


def test_bad_args_는_사용법과_비슷한_서브커맨드를_싣는다(monkeypatch):
    buf = _capture(monkeypatch)
    run_cli(_parser(), ["list-run"])
    out = json.loads(buf.getvalue())
    assert out["code"] == "bad_args" and out["did_you_mean"] == ["list-runs"] and "usage" in out


def test_commit_한_번에_정리하고_지정한_경로만_커밋한다(tmp_path, monkeypatch):
    import commit_cli
    repo = tmp_path / "r"
    repo.mkdir()
    g = lambda *a: subprocess.run(["git", "-c", "user.name=a", "-c", "user.email=a@a", "-C", str(repo), *a],
                                  check=True, capture_output=True, text=True)
    g("init", "-q")
    (repo / "mine.txt").write_text("1", encoding="utf-8")
    (repo / "theirs.txt").write_text("2", encoding="utf-8")
    message = tmp_path / "m.txt"
    message.write_text("제목 : fix : 내용 https://x/1\n\n@someone", encoding="utf-8")
    buf = _capture(monkeypatch)
    monkeypatch.setattr(subprocess, "run", (lambda real: lambda cmd, **k: real(
        [cmd[0], "-c", "user.name=a", "-c", "user.email=a@a", *cmd[1:]] if cmd[0] == "git" else cmd, **k))(subprocess.run))
    args = type("A", (), {"message_file": str(message), "message": None, "paths": ["mine.txt"], "root": str(repo)})()
    commit_cli.cmd_commit(args)
    out = json.loads(buf.getvalue())
    assert out["ok"] is True and out["mention_removed"] is True and "@someone" not in out["message"]
    assert g("show", "--name-only", "--format=").stdout.split() == ["mine.txt"]  # 남의 파일은 커밋되지 않았다


def test_commit_스테이징이_없으면_거절한다(tmp_path, monkeypatch):
    import commit_cli
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    buf = _capture(monkeypatch)
    commit_cli.cmd_commit(type("A", (), {"message_file": None, "message": "m", "paths": [], "root": str(tmp_path)})())
    assert json.loads(buf.getvalue())["code"] == "nothing_staged"
