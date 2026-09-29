"""컴퓨터별 학습 메모(recall · learn · forget) 테스트.

⚠️ 진짜 홈을 건드리지 않는다 — 전부 임시 HOME 으로 돌린다.
지키려는 것: 강화(카운터)·상한·비밀값 거절·금지 방법이 기억으로 되살아나지 않는 것.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import knowledge  # noqa: E402
from test_launch_cli import _j, _repo, run_cli  # noqa: E402


@pytest.fixture()
def env(tmp_path):
    return {"home": tmp_path / "home", "root": _repo(tmp_path)}


def cli(env, *args):
    (env["home"]).mkdir(exist_ok=True)
    code, out, err = run_cli(*args, "--root", str(env["root"]), home=env["home"])
    return _j(out)


def test_learn_then_recall_roundtrip(env):
    r = cli(env, "learn", "--area", "ios", "--key", "ios.tap",
            "--how", "client/tool/e2e_shot.sh (Maestro) 로 위젯 텍스트를 누른다", "--result", "ok")
    assert r["ok"] and r["entry"]["ok"] == 1
    got = cli(env, "recall", "--area", "ios")
    assert got["ok"] and got["entries"][0]["key"] == "ios.tap"
    assert got["entries"][0]["scope"] == "repo"


def test_recall_empty_is_ok_not_error(env):
    got = cli(env, "recall")
    assert got["ok"] and got["entries"] == [] and got["code"] == "empty"


def test_counters_strengthen_and_weaken(tmp_path):
    p = tmp_path / "k.json"
    for _ in range(3):
        knowledge.learn(p, "web", "web.google-login", "web open --headed", "ok", today="2026-09-29")
    e = knowledge.learn(p, "web", "web.google-login", "web open --headed", "fail", today="2026-09-29")["entry"]
    assert (e["ok"], e["fail"]) == (3, 1)


def test_changed_method_resets_the_old_score(tmp_path):
    p = tmp_path / "k.json"
    for _ in range(3):
        knowledge.learn(p, "ios", "ios.tap", "방법 A", "ok", today="2026-09-29")
    e = knowledge.learn(p, "ios", "ios.tap", "방법 B", "ok", today="2026-09-29")["entry"]
    assert (e["how"], e["ok"], e["fail"]) == ("방법 B", 1, 0)   # A 의 성적을 물려받지 않는다


def test_recall_orders_by_score_and_flags_unreliable(tmp_path):
    p = tmp_path / "k.json"
    for _ in range(3):
        knowledge.learn(p, "ios", "good", "좋은 방법", "ok", today="2026-09-29")
    knowledge.learn(p, "ios", "bad", "나쁜 방법", "fail", today="2026-09-29")
    rows = knowledge.recall({"repo": p}, "ios", today="2026-09-29")
    assert [r["key"] for r in rows] == ["good", "bad"]
    assert rows[0]["verify"] is False and rows[1]["verify"] is True   # 실패가 앞선 것은 한 번 확인


def test_stale_entries_sink_and_are_flagged(tmp_path):
    p = tmp_path / "k.json"
    knowledge.learn(p, "web", "old", "옛 방법", "ok", today="2026-01-01")
    knowledge.learn(p, "web", "new", "새 방법", "ok", today="2026-09-29")
    rows = knowledge.recall({"repo": p}, "web", today="2026-09-29")
    assert [r["key"] for r in rows] == ["new", "old"] and rows[1]["verify"] is True


def test_recall_limit_bounds_the_output(tmp_path):
    p = tmp_path / "k.json"
    for i in range(10):
        knowledge.learn(p, "web", f"k{i}", f"방법 {i}", "ok", today="2026-09-29")
    assert len(knowledge.recall({"repo": p}, "web", limit=3, today="2026-09-29")) == 3


def test_cap_drops_lowest_scores(tmp_path):
    p = tmp_path / "k.json"
    for i in range(knowledge.MAX_ENTRIES + 5):
        knowledge.learn(p, "web", f"k{i}", f"방법 {i}", "fail", today="2026-09-29")
    knowledge.learn(p, "web", "best", "가장 좋은 방법", "ok", today="2026-09-29")
    keys = [e["key"] for e in knowledge.load(p)]
    assert len(keys) == knowledge.MAX_ENTRIES and "best" in keys


def test_how_is_truncated_to_keep_tokens_small(tmp_path):
    p = tmp_path / "k.json"
    e = knowledge.learn(p, "web", "long", "가" * 1000, "ok", today="2026-09-29")["entry"]
    assert len(e["how"]) == knowledge.MAX_HOW


@pytest.mark.parametrize("how", ["password: hunter2secret 로 로그인", "me@example.com 계정으로 로그인",
                                 "토큰 eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkw 사용"])
def test_secrets_are_refused(tmp_path, how):
    p = tmp_path / "k.json"
    r = knowledge.learn(p, "web", "login", how, "ok")
    assert r["error"] == "secret_detected" and not p.exists()


@pytest.mark.parametrize("how", ["cliclick c:730,630 으로 시뮬레이터를 누른다",
                                 "osascript 로 Simulator 창을 click 한다"])
def test_host_mouse_methods_cannot_be_learned(tmp_path, how):
    r = knowledge.learn(tmp_path / "k.json", "ios", "ios.tap", how, "ok")
    assert r["error"] == "forbidden_method"


def test_forbidden_method_in_an_old_file_is_filtered_on_recall(tmp_path):
    """손으로 고친 파일·옛 파일에 금지 방법이 있어도 꺼내지 않는다 — 기억이 안전 규칙을 우회하면 안 된다."""
    p = tmp_path / "k.json"
    p.write_text(json.dumps({"schema": 1, "entries": [
        {"key": "ios.tap", "area": "ios", "how": "cliclick 으로 누른다", "ok": 9, "fail": 0,
         "last_seen": "2026-09-29"},
        {"key": "ios.e2e", "area": "ios", "how": "Maestro 플로우", "ok": 1, "fail": 0,
         "last_seen": "2026-09-29"}]}), encoding="utf-8")
    rows = knowledge.recall({"repo": p}, "ios", today="2026-09-29")
    assert [r["key"] for r in rows] == ["ios.e2e"]


def test_corrupt_file_does_not_stop_work(tmp_path):
    p = tmp_path / "k.json"
    p.write_text("{깨진 json", encoding="utf-8")
    assert knowledge.recall({"repo": p}, None) == []
    assert knowledge.learn(p, "web", "k", "방법", "ok")["entry"]["ok"] == 1   # 덮어써서 복구된다


def test_repo_and_machine_scopes_are_separate(env):
    cli(env, "learn", "--area", "web", "--key", "web.login", "--how", "repo 방법", "--result", "ok")
    cli(env, "learn", "--area", "web", "--key", "web.headed", "--how", "machine 방법",
        "--result", "ok", "--scope", "machine")
    scopes = {e["key"]: e["scope"] for e in cli(env, "recall", "--area", "web")["entries"]}
    assert scopes == {"web.login": "repo", "web.headed": "machine"}
    only = cli(env, "recall", "--scope", "machine")["entries"]
    assert [e["key"] for e in only] == ["web.headed"]


def test_forget_removes_the_entry(env):
    cli(env, "learn", "--area", "web", "--key", "web.x", "--how", "방법", "--result", "ok")
    assert cli(env, "forget", "--key", "web.x")["removed"] == 1
    assert cli(env, "forget", "--key", "web.x")["code"] == "not_found"


def test_cli_rejects_secret_with_json_error(env):
    r = cli(env, "learn", "--area", "web", "--key", "k", "--how", "password: hunter2secret", "--result", "ok")
    assert r["ok"] is False and r["code"] == "secret_detected"
    for k in ("ok", "code", "summary", "next"):
        assert k in r      # MCP-style 4필드 보장
