"""note 기억 원칙 (#837) · 화면 대상 targets (#838).

옛 learned.json(schema 1, 픽셀 taps, 성적 없음)이 그대로 읽혀야 한다 — 실제 사용자 파일이
그 모양이다. 쓰기 전 유사 항목 찾기 · 성적 · 요약 · 응답에 싣기 · tidy 를 실제 CLI 로 밟는다.
"""
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

CLI = Path(__file__).resolve().parents[1] / "scripts" / "e2e_cli.py"
sys.path.insert(0, str(CLI.parent))

import e2e_cli  # noqa: E402

TODAY = date.today().isoformat()


def run(*args, home: Path):
    import os
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "HOME": str(home), "USERPROFILE": str(home),
           "PROJECTOPS_HOME": str(home / ".projectops")}
    r = subprocess.run([sys.executable, str(CLI), *args], capture_output=True, text=True,
                       encoding="utf-8", env=env)
    assert "Traceback" not in (r.stderr or ""), r.stderr
    return json.loads((r.stdout or "").strip().splitlines()[-1])


@pytest.fixture
def proj(tmp_path):
    p = tmp_path / "proj"
    p.mkdir()
    subprocess.run(["git", "init", "-q", str(p)], check=True)
    subprocess.run(["git", "-C", str(p), "remote", "add", "origin",
                    "https://github.com/acme/demo.git"], check=True)
    home = tmp_path / "home"
    home.mkdir()
    return p, home


def _learned(home: Path) -> Path:
    return home / ".projectops" / "agent-test" / "acme__demo" / "learned.json"


def _machine(home: Path) -> Path:
    return home / ".projectops" / "agent-test" / "_machine" / "learned.json"


# 실제 사용자 파일과 같은 모양 (schema 1 · 화면당 픽셀 한 벌 · 성적 없음)
LEGACY = {
    "schema": 1,
    "screens": {
        "시작": {"anchor": "시작하기", "taps": {"시작하기": "540,1956"},
                 "measured_on": "1080x2400", "updated": "2026-09-17"},
        "모름": {"anchor": "x", "taps": {"버튼": "10,20"}},
    },
    "pitfalls": [
        {"text": "약관 동의 목록은 3~4회 스와이프해야 끝까지 간다. 한 번만 밀고 잘렸다고 판단하면 오진한다",
         "added": "2026-09-17", "scope": "project"},
        {"text": "한글 입력 불가. adb input text가 ASCII만 받으므로 이름 입력은 영문으로 대체한다",
         "added": "2026-09-17", "scope": "flutter"},
        {"text": "gstack browse 에서 viewport 를 바꾸면 서버가 재시작되며 PATH 의 bun 을 못 찾는다",
         "added": "2026-09-20", "scope": "project"},
        {"text": "screenrecord 는 명령 후 시작까지 1~2초 걸린다. 조작 전에 4초는 기다린 뒤 탭한다",
         "added": "2026-09-20", "scope": "platform"},
        {"text": "e2e_cli shrink 는 PNG 를 webp 로 바꾸고 원본 PNG 를 지운다",
         "added": "2026-09-20", "scope": "project"},
    ] + [{"text": f"서버 응답 검증 항목 번호{i} 를 따로 확인한다 케이스{i}", "added": "2026-09-18",
          "scope": "project"} for i in range(6)],
    "constraints": [{"text": f"아이 화면 규칙 {i}번 경고색 금지 조건{i}", "check": "빨간 글자", "added": "2026-09-17"}
                    for i in range(7)],
    "runs": [{"date": "2026-09-23", "scenario": "s", "result": "통과"}],
    "targets": {"value": ["app"], "why": "Flutter 앱", "added": "2026-09-21"},
}


def _seed(home: Path, data=None):
    f = _learned(home)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(data or LEGACY, ensure_ascii=False), encoding="utf-8")
    return f


# ── 하위호환 · 화면 대상 (#838) ──────────────────────────────────────────

def test_legacy_file_is_read_and_pixels_become_ratios_without_writing(proj):
    p, home = proj
    f = _seed(home)
    before = f.read_text(encoding="utf-8")
    d = run("note", "show", "--all", "--root", str(p), home=home)
    assert d["ok"] is True
    v = d["screens"]["시작"]["variants"]["default@1080x2400"]
    assert v["targets"]["시작하기"] == {"at": "0.5,0.815", "verify": True}
    assert v["legacy_taps"] == {"시작하기": "540,1956"}
    # 해상도를 모르면 바꾸지 않고 남긴다
    assert d["screens"]["모름"]["variants"]["default@?"]["unconverted"] == ["버튼"]
    assert f.read_text(encoding="utf-8") == before, "읽기만 했는데 파일이 바뀌었다"


def test_first_write_migrates_file_and_bumps_schema(proj):
    p, home = proj
    f = _seed(home)
    run("note", "run", "--name", "s", "--text", "ok", "--root", str(p), home=home)
    saved = json.loads(f.read_text(encoding="utf-8"))
    assert saved["schema"] == 3
    v = saved["screens"]["시작"]["variants"]["default@1080x2400"]
    assert "taps" not in v and v["legacy_taps"] == {"시작하기": "540,1956"}
    assert saved["targets"]["value"] == ["app"]       # 모르는 필드·다른 필드는 그대로


def test_pixel_target_hint_converts_with_known_size(proj):
    p, home = proj
    _seed(home)
    d = run("note", "screen", "--name", "시작", "--target", "시작하기=540,1956",
            "--screen-size", "1080x2400", "--root", str(p), home=home)
    assert d["code"] == "pixels_rejected"
    assert "시작하기=at:0.5,0.815" in d["hint"]


def test_screen_result_grades_target(proj):
    p, home = proj
    _seed(home)
    d = run("note", "screen", "--name", "시작", "--target", "시작하기", "--result", "ok",
            "--root", str(p), home=home)
    assert d["ok"] is True and d["graded"][0]["ok"] == 1
    # 성공이 앞서면 변환 때 붙은 verify 가 내려간다
    assert d["graded"][0]["verify"] is False
    d = run("note", "screen", "--name", "시작", "--target", "없음", "--result", "fail",
            "--root", str(p), home=home)
    assert d["code"] == "target_not_found"


def test_rewriting_same_target_keeps_grade_but_new_locator_resets(proj):
    p, home = proj
    args = ["note", "screen", "--name", "홈", "--anchor", "홈", "--root", str(p)]
    run(*args, "--target", "설정=desc:설정", home=home)
    run("note", "screen", "--name", "홈", "--target", "설정", "--result", "ok", "--root", str(p), home=home)
    run(*args, "--target", "설정=desc:설정", home=home)
    t = json.loads(_learned(home).read_text(encoding="utf-8"))["screens"]["홈"]["variants"]["default@?"]["targets"]["설정"]
    assert t["ok"] == 1
    run(*args, "--target", "설정=id:settings", home=home)
    t = json.loads(_learned(home).read_text(encoding="utf-8"))["screens"]["홈"]["variants"]["default@?"]["targets"]["설정"]
    assert t == {"id": "settings"}


# ── 요약 · 성적 (#837) ───────────────────────────────────────────────────

def test_show_default_is_summary_with_caps(proj):
    p, home = proj
    _seed(home)
    d = run("note", "show", "--root", str(p), home=home)
    assert len(d["constraints"]) == 5 and len(d["pitfalls"]) == 5
    assert all(len(x["text"]) <= 120 for x in d["pitfalls"])
    assert "legacy_taps" not in json.dumps(d["screens"], ensure_ascii=False)
    assert "--all" in d["next"] and "note tidy" in d["next"]
    full = run("note", "show", "--all", "--root", str(p), home=home)
    assert len(full["pitfalls"]) == len(LEGACY["pitfalls"])


def test_pitfall_duplicate_merges_instead_of_appending(proj):
    p, home = proj
    _seed(home)
    d = run("note", "pitfall", "--text",
            "약관 동의 목록은 3~4회 스와이프해야 끝까지 간다. 한 번만 밀면 잘렸다고 오진한다",
            "--root", str(p), home=home)
    assert d["merged_into"]["index"] == 0, d
    saved = json.loads(_learned(home).read_text(encoding="utf-8"))
    assert len(saved["pitfalls"]) == len(LEGACY["pitfalls"])
    assert saved["pitfalls"][0]["ok"] == 1 and saved["pitfalls"][0]["last_seen"] == TODAY


def test_pitfall_related_is_shown_but_still_written(proj):
    p, home = proj
    _seed(home)
    d = run("note", "pitfall", "--text", "약관 동의 목록은 화면 아래 버튼까지 가야 보인다 문구 확인",
            "--root", str(p), home=home)
    assert "merged_into" not in d
    assert d["related"] and d["related"][0]["index"] == 0
    assert "note forget" in d["next"]


def test_pitfall_grade_and_forget(proj):
    p, home = proj
    _seed(home)
    for _ in range(2):
        d = run("note", "pitfall", "--index", "0", "--result", "fail", "--root", str(p), home=home)
    assert d["entry"]["fail"] == 1 and d["counted"] is False      # 같은 날 두 번은 한 번
    assert d["verify"] is True
    d = run("note", "forget", "--kind", "pitfall", "--index", "0", "--root", str(p), home=home)
    assert d["ok"] is True
    saved = json.loads(_learned(home).read_text(encoding="utf-8"))
    assert len(saved["pitfalls"]) == len(LEGACY["pitfalls"]) - 1


def test_machine_scope_pitfall_goes_to_machine_file(proj):
    p, home = proj
    d = run("note", "pitfall", "--text", "에뮬레이터 글꼴 배율은 전용 기기에서만 바꾼다 다른 세션 영향",
            "--scope", "platform", "--root", str(p), home=home)
    assert d["scope"] == "machine"
    assert json.loads(_machine(home).read_text(encoding="utf-8"))["pitfalls"][0]["scope"] == "platform"
    assert not _learned(home).exists()


# ── 응답에 싣기 (#837) ───────────────────────────────────────────────────

def test_surface_once_per_slot_per_day(proj):
    p, home = proj
    _seed(home)
    sd = _learned(home).parent
    (sd / "s1.json").write_text(json.dumps({
        "name": "약관", "target": "app",
        "steps": [{"screen": "약관 동의", "do": "스와이프", "expect_screen": "끝까지"}]},
        ensure_ascii=False), encoding="utf-8")
    d = run("scenario", "show", "--name", "s1", "--root", str(p), home=home)
    mem = d["memory"]
    assert len(mem["constraints"]) <= 2 and len(mem["pitfalls"]) <= 3
    assert any("약관" in x["text"] for x in mem["pitfalls"]), mem   # 맥락에 맞는 것이 앞선다
    again = run("scenario", "show", "--name", "s1", "--root", str(p), home=home)
    assert "memory" not in again
    # memory_seen.json 은 시나리오 목록에 섞이지 않는다
    names = [r["file"] for r in run("scenario", "list", "--root", str(p), home=home)["scenarios"]]
    assert names == ["s1.json"], names


def test_hidden_when_failures_dominate():
    e = {"text": "틀린 기억", "ok": 0, "fail": 3}
    assert e2e_cli._memory.hidden(e)


# ── tidy (#837) ─────────────────────────────────────────────────────────

def test_tidy_dry_run_plans_without_writing(proj):
    p, home = proj
    f = _seed(home)
    before = f.read_text(encoding="utf-8")
    d = run("note", "tidy", "--root", str(p), home=home)
    assert d["applied"] is False
    assert {r["index"] for r in d["to_machine"]} == {1}
    launch = {r["index"]: r["area"] for r in d["to_launch"]}
    assert launch == {2: "web", 3: "android"}
    assert [r["index"] for r in d["skipped"]] == [4]       # 도구지만 영역을 모름
    assert f.read_text(encoding="utf-8") == before
    assert not _machine(home).exists()


def test_tidy_apply_moves_only(proj):
    p, home = proj
    _seed(home)
    d = run("note", "tidy", "--apply", "--root", str(p), home=home)
    assert d["applied"] is True, d
    saved = json.loads(_learned(home).read_text(encoding="utf-8"))
    texts = [x["text"] for x in saved["pitfalls"]]
    assert not any("한글 입력" in t or "gstack" in t or "screenrecord" in t for t in texts)
    assert any("e2e_cli shrink" in t for t in texts)          # 못 옮긴 것은 남긴다
    m = json.loads(_machine(home).read_text(encoding="utf-8"))
    assert [x["from"] for x in m["pitfalls"]] == ["acme__demo"]
    # launch knowledge 로 간 것: 프로젝트 범위는 레포, platform 은 이 컴퓨터
    kn = list((home / ".projectops" / "launch").rglob("knowledge.json"))
    hows = " ".join(x["how"] for k in kn for x in json.loads(k.read_text(encoding="utf-8"))["entries"])
    assert "gstack" in hows and "screenrecord" in hows
    # 전체 개수는 옮긴 만큼만 줄었다 (지운 것 없음)
    assert len(saved["pitfalls"]) + 1 + len(d["to_launch"]) == len(LEGACY["pitfalls"])
