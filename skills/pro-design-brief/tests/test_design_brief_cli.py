"""design_brief_cli 단위 테스트 (#634).

설정 해석 우선순위 · 보드 조립(HTML 구조 · 그림 한 번만 싣기 · PNG 개수) · 문구 기계 검사 ·
ASCII 폭을 본다. 브라우저가 필요한 PNG 검사만 `local_only` 다.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

CLI = Path(__file__).resolve().parents[1] / "scripts" / "design_brief_cli.py"
sys.path.insert(0, str(CLI.parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import design_brief_cli as db  # noqa: E402

# 1x1 PNG
_PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
                     "0000000d49444154789c6360f8cfc0f01f0005000201a2dd8a3a0000000049454e44ae426082")


def run_cli(*args, home: Path, cwd: Path | None = None):
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "HOME": str(home), "USERPROFILE": str(home)}
    r = subprocess.run([sys.executable, str(CLI), *args], capture_output=True, text=True,
                       encoding="utf-8", env=env, cwd=str(cwd) if cwd else None)
    return json.loads(r.stdout.strip().splitlines()[-1])


def _repo(tmp: Path, name="proj", remote="https://github.com/acme-org/myapp.git") -> Path:
    p = tmp / name
    p.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(p)], check=True)
    if remote:
        subprocess.run(["git", "-C", str(p), "remote", "add", "origin", remote], check=True)
    return p


def _write_config(home: Path, data: dict):
    f = home / ".projectops" / "config" / "config.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return f


# ── 설정 ─────────────────────────────────────────────────────────────────

def test_project_entry_beats_section_default(tmp_path):
    proj = _repo(tmp_path)
    cfg = {"design_brief": {"destination": "markdown", "designer": "기본",
                            "projects": [{"match": "acme-org/myapp", "destination": "issue"}]}}
    r = db.resolve_config(proj, cfg)
    assert r["resolved"]["destination"] == "issue" and r["source"]["destination"] == "project"
    assert r["resolved"]["designer"] == "기본" and r["source"]["designer"] == "default"
    assert r["resolved"]["auto_approve"] is False, "기본은 게시 전에 확인받는다"


def test_non_github_repo_matches_by_path(tmp_path):
    """GitHub 을 안 쓰는 레포도 요청서를 받는다 — 그래서 github 설정 밑에 두지 않았다."""
    proj = _repo(tmp_path, "local", remote=None)
    cfg = {"design_brief": {"projects": [{"match": str(proj.resolve()), "destination": "html"}]}}
    r = db.resolve_config(proj, cfg)
    assert r["resolved"]["destination"] == "html" and r["repo"]["github"] is False


def test_first_run_suggests_and_lists_what_is_missing(tmp_path):
    proj = _repo(tmp_path)
    r = db.resolve_config(proj, {"github": {"repos": [{"owner": "acme-org", "repo": "myapp"}]}})
    assert r["missing"] == ["destination", "designer"]
    assert r["suggest"]["destination"] == "issue"
    local = _repo(tmp_path, "local", remote=None)
    assert db.resolve_config(local, {})["suggest"]["destination"] == "html"


def test_designer_from_template_skips_placeholders(tmp_path):
    """템플릿의 `디자인: 이름` 은 자리표시다 — 담당자로 읽으면 엉뚱한 사람을 부른다 (실측)."""
    proj = _repo(tmp_path)
    t = proj / ".github" / "ISSUE_TEMPLATE"
    t.mkdir(parents=True)
    (t / "a.md").write_text("- **디자인**: 이름\n", encoding="utf-8")
    (t / "b.md").write_text("- 디자인: @real-designer\n", encoding="utf-8")
    assert db._designer_from_templates(proj) == ["real-designer"]


def test_config_set_keeps_other_sections(tmp_path):
    """전체를 읽고 해당 키만 바꾼다 — PAT 같은 다른 섹션을 날리면 안 된다."""
    proj = _repo(tmp_path)
    f = _write_config(tmp_path, {"github": {"global_pat": "keep-me"}, "output": {"root": "x"}})
    d = run_cli("config", "set", "--root", str(proj), "--destination", "html", "--designer", "김디자인",
                home=tmp_path)
    assert d["ok"] and d["resolved"]["destination"] == "html"
    saved = json.loads(f.read_text(encoding="utf-8"))
    assert saved["github"]["global_pat"] == "keep-me" and saved["output"] == {"root": "x"}
    assert saved["design_brief"]["projects"][0]["match"] == "acme-org/myapp"
    # 같은 레포에 다시 저장하면 항목이 늘지 않는다
    run_cli("config", "set", "--root", str(proj), "--auto-approve", "true", home=tmp_path)
    saved = json.loads(f.read_text(encoding="utf-8"))
    assert len(saved["design_brief"]["projects"]) == 1
    assert saved["design_brief"]["projects"][0]["auto_approve"] is True


def test_config_set_rejects_unknown_destination(tmp_path):
    d = run_cli("config", "set", "--root", str(_repo(tmp_path)), "--destination", "slack", home=tmp_path)
    assert d["code"] == "bad_destination"


# ── 산출물 자리 ───────────────────────────────────────────────────────────

def test_output_path_is_untracked_evidence(tmp_path):
    proj = _repo(tmp_path)
    d = run_cli("get-output-path", "--title", "요청서", home=tmp_path, cwd=proj)
    run_dir = Path(d["run_dir"])
    assert run_dir.parent == (proj / "docs" / "projectops" / "design-brief").resolve() or \
        run_dir.parent.resolve() == (proj / "docs" / "projectops" / "design-brief").resolve()
    assert Path(d["board_dir"]).is_dir() and d["gitignore"] == "created"


# ── 보드 ─────────────────────────────────────────────────────────────────

def _data(tmp: Path) -> Path:
    shots = tmp / "screenshots"
    shots.mkdir(parents=True, exist_ok=True)
    (shots / "a.png").write_bytes(_PNG)
    data = {
        "title": "화면 — 디자인 요청서",
        "summary": {"what": "무엇", "why": "왜", "must_keep": [{"rule": "규칙", "source": "출처"}]},
        "current": [{"label": "지금", "image": "screenshots/a.png"}],
        "states": [{"axis": "데이터", "name": "0건", "status": "none", "image": "screenshots/a.png",
                    "copy_needed": True, "design": False},
                   {"axis": "표시", "name": "렌더 실패", "status": "temp", "ascii": "┌─┐", "render_failed": True}],
        "alternatives": [{"id": "A", "name": "지금", "image": "screenshots/a.png", "recommended": True,
                          "pros": ["p"], "cons": ["c"], "dev_impact": "없음"},
                         {"id": "B", "name": "새 화면", "ascii": "┌──┐\n│가│\n└──┘"}],
        "copy": [{"where": "약관", "current": "약관", "legal": True},
                 {"where": "실패", "current": "", "needed": True}],
    }
    f = tmp / "board_data.json"
    f.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return f


def test_board_html_has_only_sections_with_data(tmp_path):
    doc, topics = db.render_html(json.loads(_data(tmp_path).read_text(encoding="utf-8")), tmp_path)
    assert topics == ["summary", "current", "states", "alternatives", "copy"], "데이터 없는 주제를 만들었다"
    assert "{{" not in doc and "<!--SECTIONS-->" not in doc and "<!--NAV-->" not in doc
    assert "정답이 아니라 생각할 재료" in doc
    assert "법적 문구 — 바꾸면 안 됨" in doc and doc.count("문구 필요") >= 2
    assert "<th>시안</th>" in doc, "design 값이 있으면 시안 칸이 생겨야 한다"
    assert "개발 쪽 추천" in doc


def test_board_embeds_each_image_once(tmp_path):
    """같은 캡처를 네 칸에 써도 한 번만 싣는다 — 칸마다 박았더니 HTML 이 16MB 가 됐다 (실측)."""
    doc, _ = db.render_html(json.loads(_data(tmp_path).read_text(encoding="utf-8")), tmp_path)
    assert doc.count("data:image/png;base64,") == 1
    assert doc.count('data-img="img1"') == 3


def test_board_ascii_keeps_wide_chars_in_two_columns(tmp_path):
    doc, _ = db.render_html(json.loads(_data(tmp_path).read_text(encoding="utf-8")), tmp_path)
    assert '<span class="w">가</span>' in doc


def test_board_cli_writes_html_and_markdown(tmp_path):
    f = _data(tmp_path)
    d = run_cli("board", "--data", str(f), "--out", str(tmp_path / "board"), "--md", home=tmp_path)
    assert d["ok"] and Path(d["html"]).is_file() and Path(d["md"]).is_file()
    md = Path(d["md"]).read_text(encoding="utf-8")
    assert "## 꼭 지킬 것" in md and "**문구 필요**" in md


def test_board_rejects_broken_data(tmp_path):
    bad = tmp_path / "x.json"
    bad.write_text("{", encoding="utf-8")
    assert run_cli("board", "--data", str(bad), "--out", str(tmp_path / "o"), home=tmp_path)["code"] == "bad_data"


def test_markdown_table_cells_escape_pipes():
    md = db.render_markdown({"copy": [{"where": "a|b", "current": "x", "candidates": ["p|q"], "reason": "r"}]},
                            [], Path("."))
    assert "| a\\|b | x | p\\|q | r |" in md


@pytest.mark.local_only
def test_board_png_one_per_topic_and_within_width(tmp_path):
    if db._require_playwright() is None:
        pytest.skip("Playwright 없음 — pro-launch web setup 후 실행된다")
    f = _data(tmp_path)
    d = run_cli("board", "--data", str(f), "--out", str(tmp_path / "board"), "--png",
                home=Path(os.path.expanduser("~")))   # 브라우저는 실제 HOME 의 것을 쓴다
    assert d["ok"], d
    assert len(d["png"]) == len(d["topics"]) == 5
    assert all(db._png_width(Path(p)) <= db.MAX_PNG_WIDTH for p in d["png"])


# ── 문구 검사 ─────────────────────────────────────────────────────────────

def test_copy_lint_flags_mechanical_tells(tmp_path):
    rows = [{"where": "a", "current": "저장되었습니다", "candidates": ["저장했어요", "혁신적인 저장 — 끝"]},
            {"where": "b", "current": "우리 아이 기록", "candidates": ["이룸이 기록"]},
            {"where": "약관", "current": "개인정보를 수집·이용·제공합니다", "legal": True}]
    f = tmp_path / "copy.json"
    f.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    d = run_cli("copy-lint", "--file", str(f), "--banned", "아이,기기", home=tmp_path)
    assert d["code"] == "candidate_issues"
    texts = {i["text"]: i["problems"] for i in d["issues"]}
    assert any("em dash" in p for p in texts["혁신적인 저장 — 끝"])
    assert any("과장" in p for p in texts["혁신적인 저장 — 끝"])
    assert any("피동" in p for p in texts["저장되었습니다"])
    assert any("아이" in p for p in texts["우리 아이 기록"])
    assert "저장했어요" not in texts and "이룸이 기록" not in texts
    assert not any("수집" in t for t in texts), "법적 문구는 검사하지 않는다"


def test_copy_lint_passes_clean_candidates(tmp_path):
    f = tmp_path / "c.json"
    f.write_text(json.dumps([{"where": "a", "current": "x", "candidates": ["저장했어요"]}], ensure_ascii=False),
                 encoding="utf-8")
    assert run_cli("copy-lint", "--file", str(f), home=tmp_path)["ok"] is True


# ── ASCII ────────────────────────────────────────────────────────────────

def test_ascii_lines_are_the_same_width_with_korean(tmp_path):
    spec = {"width": 28, "title": "< 앱 정보", "rows": ["", {"text": "버전 1.44.0", "align": "center"},
                                                     "---", " 오픈소스 라이선스        >",
                                                     {"text": "아주아주아주아주아주아주아주아주 긴 글", "align": "left"}]}
    d = run_cli("ascii", "--spec", json.dumps(spec, ensure_ascii=False), home=tmp_path)
    assert d["aligned"] is True, d["ascii"]
    widths = {db.text_width(line) for line in d["ascii"].splitlines()}
    assert widths == {30}


def test_text_width_counts_hangul_as_two():
    assert db.text_width("가a") == 3 and db.text_width("ELUM") == 4


# ── 근거 검사 (#636) ──────────────────────────────────────────────────────
#
# 렌더만 보고 쓴 주장 7건이 실기기와 달랐고, 도달할 수 없는 상태를 요청한 일이 있었다.
# 판단은 agent 가 하지만, 빠뜨린 표시는 기계가 센다.

def _clean_data(tmp: Path) -> dict:
    shots = tmp / "screenshots"
    shots.mkdir(parents=True, exist_ok=True)
    (shots / "a.png").write_bytes(_PNG)
    return {
        "title": "t",
        "facts": [{"claim": "주간 지급량은 50개다", "basis": "server", "ref": "GET /api/credit"}],
        "current": [{"label": "지금", "image": "screenshots/a.png", "source": "device"}],
        "states": [{"axis": "데이터", "name": "0건", "status": "none", "reachable": "yes",
                    "image": "screenshots/a.png", "source": "render"}],
        "alternatives": [{"id": "A", "name": "지금", "image": "screenshots/a.png", "source": "device"}],
    }


def test_preflight_is_empty_when_everything_is_labeled(tmp_path):
    assert db.preflight(_clean_data(tmp_path)) == []


def test_preflight_flags_missing_labels_and_render_only_facts(tmp_path):
    d = _clean_data(tmp_path)
    d["current"][0].pop("source")
    d["states"][0].pop("reachable")
    d["states"].append({"axis": "데이터", "name": "옛 보상 이모지", "reachable": "old_data"})
    d["alternatives"][0].pop("source")
    d["facts"] += [{"claim": "시트 뒤 버튼이 비친다", "basis": "render", "ref": "x.png"},
                   {"claim": "근거 없는 말"},
                   {"claim": "위치 없는 근거", "basis": "device"}]
    w = "\n".join(db.preflight(d))
    assert "현재 구현[0]" in w and "출처" in w
    assert "reachable" in w and "예전 데이터에만" in w
    assert "대안 A" in w
    assert "렌더(가짜 데이터)는 근거가 아니다" in w and "근거가 없다" in w and "ref" in w


def test_board_shows_source_reachability_and_facts(tmp_path):
    doc, _ = db.render_html(_clean_data(tmp_path), tmp_path)
    assert "렌더 · 가짜 데이터" in doc and "실기기" in doc
    assert "지금 나온다" in doc
    assert "지금 앱에 대한 사실과 근거" in doc and "운영 API·설정" in doc


def test_board_strict_stops_on_preflight(tmp_path):
    d = _clean_data(tmp_path)
    d["facts"][0]["basis"] = "render"
    f = tmp_path / "data.json"
    f.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    loose = run_cli("board", "--data", str(f), "--out", str(tmp_path / "b1"), home=tmp_path)
    assert loose["ok"] is True and loose["preflight"], "경고는 돌려주되 조립은 한다"
    strict = run_cli("board", "--data", str(f), "--out", str(tmp_path / "b2"), "--strict", home=tmp_path)
    assert strict["ok"] is False and strict["code"] == "preflight_failed"


def test_markdown_carries_facts_and_reachability(tmp_path):
    md = db.render_markdown(_clean_data(tmp_path), [], tmp_path)
    assert "## 지금 앱에 대한 사실과 근거" in md and "| 주간 지급량은 50개다 | 운영 API·설정 |" in md
    assert "| 지금 나온다 |" in md


@pytest.mark.parametrize("text,hit", [
    ("아이콘을 누르세요", False), ("아이디 입력", False), ("아이콘", False),
    ("우리 아이 기록", True), ("아이가 좋아해요", True), ("아이들이 써요", True),
    ("아이에게는", True), ("아이.", True),
])
def test_banned_word_is_a_word_not_a_substring(text, hit):
    """금지어 '아이'가 '아이콘'에 걸리던 오탐 (실측, #636)."""
    assert db._banned_hit("아이", text) is hit
