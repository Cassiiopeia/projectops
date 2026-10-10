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


# ── 쓰면 읽히고, 쓰일수록 정확해진다 (#833) ──────────────────────────────

ASC = "ASC 로그인 폼은 iframe 안이다. 셀렉터 앞에 iframe >> internal:control=enter-frame >> 를 붙인다"


@pytest.fixture()
def khome(tmp_path, monkeypatch):
    """knowledge 모듈을 임시 홈에 묶는다 (진짜 ~/.projectops 를 건드리지 않는다)."""
    monkeypatch.setattr(knowledge, "base_dir", lambda: tmp_path / ".projectops")
    return tmp_path / ".projectops" / "launch"


def _repo_file(khome, name):
    return khome / name / knowledge.FILE


def test_similar_matches_same_key_or_overlapping_how():
    a = {"area": "web", "key": "web.apple_login", "how": ASC}
    b = {"area": "web", "key": "apple.login.iframe", "how": ASC.replace("이다.", "이다 —")}
    assert knowledge.similar(a, b)
    assert not knowledge.similar(a, {**b, "area": "ios"})
    assert not knowledge.similar(a, {"area": "web", "key": "x", "how": "github 로그인은 headed 로 연다"})


def test_learn_in_second_repo_promotes_to_machine(khome):
    """다른 레포에 같은 지식이 있으면 새로 쌓지 않고 이 컴퓨터 범위로 합친다 (실측: 4곳 중복)."""
    r1 = knowledge.learn_smart(_repo_file(khome, "a__one"), "web", "web.asc", ASC, "ok")
    assert r1["scope"] == "repo"
    r2 = knowledge.learn_smart(_repo_file(khome, "b__two"), "web", "apple.iframe", ASC, "ok")
    assert r2["scope"] == "machine" and r2["promoted_from"] == 1
    assert r2["entry"]["ok"] == 2                     # 두 번의 성공이 합쳐진다
    assert knowledge.load(_repo_file(khome, "a__one")) == []
    # 세 번째 레포는 이미 이 컴퓨터 범위에 있으니 거기를 강화한다
    r3 = knowledge.learn_smart(_repo_file(khome, "c__three"), "web", "whatever", ASC, "ok")
    assert r3["scope"] == "machine" and r3["entry"]["ok"] == 3


def test_tidy_merges_spread_and_junk_buckets(khome):
    for name, key in (("a__one", "web.asc"), ("b__two", "apple.iframe")):
        knowledge.learn(_repo_file(khome, name), "web", key, ASC, "ok")
    knowledge.learn(_repo_file(khome, "scripts"), "web", "web.google", "Google 로그인은 팝업이다", "ok")
    knowledge.learn(_repo_file(khome, "a__one"), "ios", "ios.back", "iOS 뒤로는 화살표를 point 9%,10% 로", "ok")
    r = knowledge.tidy()
    m = knowledge.load(khome / "_machine" / knowledge.FILE)
    assert {e["key"] for e in m} >= {"web.google"} and r["merged"] >= 1
    asc = next(e for e in m if e["area"] == "web" and "iframe" in e["how"])
    assert asc["ok"] == 2
    # 한 레포에만 있는 고유 지식은 그 레포에 남는다
    assert [e["key"] for e in knowledge.load(_repo_file(khome, "a__one"))] == ["ios.back"]
    assert knowledge.load(_repo_file(khome, "scripts")) == []


def test_surface_once_per_day_and_hides_failing(khome):
    machine = khome / "_machine" / knowledge.FILE
    knowledge.learn(machine, "ios", "ios.tap", "Maestro 로 누른다", "ok", today="2026-10-10")
    for _ in range(3):
        knowledge.learn(machine, "ios", "ios.bad", "cliclock 아닌 다른 방법", "fail", today="2026-10-10")
    seen = khome / "seen.json"
    got = knowledge.surface({"machine": machine}, "ios", seen, today="2026-10-10")
    assert [g["key"] for g in got] == ["ios.tap"]      # 실패가 앞서는 기억은 싣지 않는다
    assert knowledge.surface({"machine": machine}, "ios", seen, today="2026-10-10") == []
    assert knowledge.surface({"machine": machine}, "ios", seen, today="2026-10-11") != []


def test_auto_record_counts_once_per_day(khome):
    for _ in range(3):
        knowledge.auto_record("android", "android.input", "app tap 으로 된다", today="2026-10-10")
    knowledge.auto_record("android", "android.input", "app tap 으로 된다", today="2026-10-11")
    e = knowledge.load(khome / "_machine" / knowledge.FILE)[0]
    assert e["ok"] == 2                               # 하루 한 번만 올라간다


def test_track_attempt_hints_after_fail_then_success(tmp_path):
    import launch_cli
    f = tmp_path / "attempts.json"
    assert launch_cli._track_attempt(f, "web", {"ok": False, "code": "not_found"}) is None
    hint = launch_cli._track_attempt(f, "web", {"ok": True, "code": "ok"})
    assert hint and "not_found" in hint and "learn" in hint
    # 한 번 알려 준 뒤에는 다시 알리지 않는다
    assert launch_cli._track_attempt(f, "web", {"ok": True, "code": "ok"}) is None


def test_learn_from_skill_dir_without_remote_goes_to_machine(tmp_path):
    """스킬 폴더로 cd 한 뒤 --root . 이면 'scripts' 가짜 레포 대신 이 컴퓨터 범위에 쓴다 (실측 버그)."""
    import launch_cli
    home = tmp_path / "home"
    home.mkdir()
    code, out, err = run_cli("learn", "--area", "web", "--key", "web.x", "--how", "headed 로 연다",
                             "--result", "ok", "--root", str(launch_cli._HERE.parent), home=home)
    d = _j(out)
    # 개발 레포 안이면 git 원격이 있어 repo 로 간다. 원격 없는 플러그인 캐시를 흉내 낼 수 없으면 건너뛴다
    if d["scope"] == "repo":
        pytest.skip("이 체크아웃은 git 원격이 있어 레포를 알 수 있다")
    assert d["scope"] == "machine"
    assert not (home / ".projectops" / "launch" / "scripts").exists()
