"""common/troubleshoot.py · build_troubleshooting.py — 공식 트러블슈팅 공통 (#889).

지키려는 것: 스키마 검증, 색인이 항목과 일치, 찾기 우선순위(코드 > 핵심어)와 상한,
색인이 없거나 깨져도 예외 없이 빈 결과, --check 가 손으로 고친 생성물을 잡는 것.
실제 스킬 폴더가 아니라 임시 fixture 스킬로 본다.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import build_troubleshooting  # noqa: E402
from common import troubleshoot  # noqa: E402


def _entry(entry_id="browser-lock", area="web", codes=("browser_start_failed",),
           keywords=("SingletonLock", "profile_locked"), **extra):
    entry = {"id": entry_id, "area": area, "title": f"{entry_id} 제목",
             "match": {"codes": list(codes), "keywords": list(keywords)},
             "symptom": "증상", "cause": "원인",
             "fix": ["launch_cli.py web close", "두 번째 단계", "세 번째 단계"],
             "refs": [712], "verified_at": "2026-10-17"}
    entry.update(extra)
    return entry


def _write(skill: Path, entry: dict, area: str | None = None, name: str | None = None) -> Path:
    path = skill / "troubleshooting" / (area or entry["area"]) / f"{name or entry['id']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entry, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.fixture()
def skill(tmp_path):
    skill_dir = tmp_path / "pro-sample"
    _write(skill_dir, _entry())
    _write(skill_dir, _entry("maestro-missing", "ios", codes=("ios_tool_missing",), keywords=()))
    _write(skill_dir, _entry("lock-by-words", "web", codes=(), keywords=("SingletonLock", "chromium", "잠금파일")))
    return skill_dir


def _build(skill_dir: Path, *flags: str, capsys=None) -> tuple[int, dict]:
    code = build_troubleshooting.main([str(skill_dir), *flags])
    out = capsys.readouterr().out.strip().splitlines()[-1] if capsys else "{}"
    return code, json.loads(out)


# ── 스키마 ──────────────────────────────────────────────────────────────

def test_valid_entry_has_no_problems():
    assert troubleshoot.validate_entry(_entry()) == []


@pytest.mark.parametrize("change, expected", [
    ({"id": "Bad_ID"}, "kebab"),
    ({"area": "mainframe"}, "area"),
    ({"verified_at": "2026/10/17"}, "verified_at"),
    ({"refs": ["#712"]}, "refs"),
    ({"fix": []}, "fix"),
    ({"match": {"codes": [], "keywords": []}}, "match"),
    ({"match": {"codes": ["Browser Failed"], "keywords": []}}, "match.codes"),
    ({"extra_field": 1}, "unknown fields"),
    ({"title": "x" * 200}, "title"),
])
def test_schema_rejects_bad_values(change, expected):
    problems = troubleshoot.validate_entry({**_entry(), **change})
    assert any(expected in p for p in problems), problems


def test_missing_required_field_is_reported():
    entry = _entry()
    entry.pop("cause")
    assert "missing required field: cause" in troubleshoot.validate_entry(entry)


def test_validate_entries_checks_filename_folder_duplicates_and_secrets(tmp_path):
    skill_dir = tmp_path / "s"
    _write(skill_dir, _entry("one"), name="other-name")
    _write(skill_dir, _entry("two", "web"), area="ios")
    _write(skill_dir, _entry("dup"), area="web")
    _write(skill_dir, _entry("dup", "ios"), area="ios")
    _write(skill_dir, _entry("leak", fix=["password: hunter2-real"]))
    problems = "\n".join(troubleshoot.validate_entries(skill_dir))
    assert "does not match the file name" in problems
    assert "does not match the folder" in problems
    assert "duplicate id" in problems
    assert "looks like a secret" in problems


def test_broken_json_file_is_a_problem_not_a_crash(tmp_path):
    path = tmp_path / "s" / "troubleshooting" / "web" / "x.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    assert any("JSON" in p for p in troubleshoot.validate_entries(tmp_path / "s"))


# ── 색인 ────────────────────────────────────────────────────────────────

def test_build_index_maps_codes_keywords_and_short_fix(skill):
    index = troubleshoot.build_index(skill)
    assert index["codes"]["browser_start_failed"] == ["browser-lock"]
    assert index["keywords"]["singletonlock"] == ["browser-lock", "lock-by-words"]
    info = index["entries"]["browser-lock"]
    assert info["path"] == "web/browser-lock.json"
    assert len(info["fix_short"]) == troubleshoot.SHORT_FIX_ITEMS


def test_build_index_is_deterministic(skill):
    assert troubleshoot.render_index(troubleshoot.build_index(skill)) == \
        troubleshoot.render_index(troubleshoot.build_index(skill))


def test_build_script_writes_then_check_passes_and_hand_edit_fails(skill, capsys):
    code, result = _build(skill, "--check", capsys=capsys)
    assert code == 1 and result["code"] == "stale"
    code, result = _build(skill, capsys=capsys)
    assert code == 0 and "troubleshooting/index.json" in result["written"]
    assert (skill / "references" / "troubleshooting.md").is_file()
    code, _ = _build(skill, "--check", capsys=capsys)
    assert code == 0
    # 손으로 고친 색인은 --check 가 잡는다
    index_file = troubleshoot.index_path(skill)
    index_file.write_text(index_file.read_text(encoding="utf-8").replace("browser-lock", "x"), encoding="utf-8")
    code, result = _build(skill, "--check", capsys=capsys)
    assert code == 1 and "troubleshooting/index.json" in result["stale"]


def test_build_script_refuses_invalid_entries(tmp_path, capsys):
    _write(tmp_path / "s", _entry(verified_at="어제"))
    code, result = _build(tmp_path / "s", capsys=capsys)
    assert code == 1 and result["code"] == "invalid_entries"
    assert not troubleshoot.index_path(tmp_path / "s").exists()


def test_markdown_groups_by_area(skill):
    text = build_troubleshooting.render_markdown(skill)
    assert text.index("## Web") < text.index("## iOS")
    assert "`browser-lock`" in text and "#712" in text


# ── 찾기 ────────────────────────────────────────────────────────────────

def _built(skill_dir: Path) -> Path:
    troubleshoot.index_path(skill_dir).write_text(
        troubleshoot.render_index(troubleshoot.build_index(skill_dir)), encoding="utf-8")
    return skill_dir


def test_code_match_ranks_before_keyword_match(skill):
    rows = troubleshoot.find_known_fixes(_built(skill), "browser_start_failed",
                                         "SingletonLock chromium 잠금파일 남음")
    assert [r["id"] for r in rows] == ["browser-lock", "lock-by-words"]


def test_keyword_only_match_needs_enough_overlap(skill):
    _built(skill)
    assert troubleshoot.find_known_fixes(skill, None, "SingletonLock 하나만") == []
    rows = troubleshoot.find_known_fixes(skill, None, "SingletonLock 과 chromium")
    # lock-by-words 는 핵심어 2개가 겹쳤고, browser-lock 은 1개뿐이라 빠진다
    assert [r["id"] for r in rows] == ["lock-by-words"]


def test_find_respects_limit_and_clips_summary(tmp_path):
    skill_dir = tmp_path / "s"
    for n in range(4):
        _write(skill_dir, _entry(f"e{n}", fix=["가" * 190, "나", "다"]))
    rows = troubleshoot.find_known_fixes(_built(skill_dir), "browser_start_failed", "")
    assert len(rows) == troubleshoot.DEFAULT_FIND_LIMIT
    assert all(len(f) <= troubleshoot.SHORT_FIX_ITEM_CHARS for r in rows for f in r["fix"])
    assert all(len(r["fix"]) <= troubleshoot.SHORT_FIX_ITEMS for r in rows)
    assert set(rows[0]) == {"id", "title", "fix"}


# iOS 실패에 android 해결이 실렸다 (#972) — 영역을 주면 그 영역 + general 만
def test_areas_filter_keeps_only_matching_and_general(tmp_path):
    skill_dir = tmp_path / "s"
    for entry_id, area in (("on-android", "android"), ("on-ios", "ios"), ("on-general", "general")):
        _write(skill_dir, _entry(entry_id, area=area, codes=("boot_failed",)))
    rows = troubleshoot.find_known_fixes(_built(skill_dir), "boot_failed", "", limit=5, areas=("ios",))
    assert {r["id"] for r in rows} == {"on-ios", "on-general"}


def test_unknown_code_returns_nothing(skill):
    assert troubleshoot.find_known_fixes(_built(skill), "nothing_here", "") == []


@pytest.mark.parametrize("broken", ["{not json", "[]", '{"codes": []}', '{"codes": {"x": 1}, "keywords": {}, "entries": {}}'])
def test_broken_or_missing_index_never_raises(skill, broken):
    assert troubleshoot.find_known_fixes(skill, "browser_start_failed", "x") == []   # 색인 없음
    troubleshoot.index_path(skill).write_text(broken, encoding="utf-8")
    assert troubleshoot.find_known_fixes(skill, "browser_start_failed", "x") == []
    assert troubleshoot.list_entries(skill) == []


def test_load_entry_reads_full_entry_even_with_stale_index(skill):
    assert troubleshoot.load_entry(skill, "browser-lock")["cause"] == "원인"   # 색인 없이도
    assert troubleshoot.load_entry(skill, "nope") is None
    assert troubleshoot.load_entry(skill, "../etc/passwd") is None


def test_list_entries_filters_by_area(skill):
    _built(skill)
    assert [r["id"] for r in troubleshoot.list_entries(skill, "ios")] == ["maestro-missing"]
    assert len(troubleshoot.list_entries(skill)) == 3
