"""scripts/common/notes.py + note_cli related + 실패 응답 note_hits (#840)."""
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from common import notes  # noqa: E402


def _write(home: Path, kind: str, name: str, body: str):
    d = home / f"{kind}s"
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(body, encoding="utf-8")


def _roots(home):
    return [("home", home)]


def test_no_notes_gives_empty(tmp_path):
    assert notes.note_hits("ITMS-90062 invalid bundle version", roots=_roots(tmp_path / "none")) == []
    data = notes.attach_note_hits({"ok": True}, "ITMS-90062 boom", roots=_roots(tmp_path / "none"))
    assert "note_hits" not in data


def test_hits_with_code_and_cap(tmp_path):
    for i in range(3):
        _write(tmp_path, "case", f"2026101{i}_001_itms.md",
               f"# ITMS-90062 빌드 번호 거부 {i}\n\n빌드 번호를 올리면 해결된다.\n" + "x" * 500)
    hits = notes.note_hits("Error: ITMS-90062 The bundle version must be higher", roots=_roots(tmp_path))
    assert len(hits) == notes.HIT_LIMIT
    assert set(hits[0]) == {"title", "path", "summary", "scope"}
    assert len(hits[0]["summary"]) <= notes.SUMMARY_MAX


def test_single_common_word_is_not_evidence(tmp_path):
    _write(tmp_path, "case", "20261010_001_a.md", "# 캐시 문제\n\ngradle 캐시를 지운다\n")
    assert notes.note_hits("gradle exploded unrelated", roots=_roots(tmp_path)) == []


def test_error_text_noise_ignored():
    words, _ = notes.keywords("2026-10-10T12:00:00Z error: failed exit code 1 abcdef0123")
    assert "error" not in words and "failed" not in words


def test_related_scores(tmp_path):
    _write(tmp_path, "fact", "ios_upload_build_number.md", "# iOS 업로드 빌드 번호\n\n내용\n")
    rel = notes.related("iOS 업로드 빌드 번호 규칙", _roots(tmp_path))
    assert rel and "score" in rel[0] and len(rel) <= 3
    assert notes.related("전혀 다른 주제 zzz", _roots(tmp_path)) == []


def _load_note_cli():
    spec = importlib.util.spec_from_file_location("note_cli", ROOT / "skills/pro-note/scripts/note_cli.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_get_output_path_related(tmp_path, monkeypatch, capsys):
    cli = _load_note_cli()
    monkeypatch.setattr(cli, "HOME_ROOT", tmp_path)
    monkeypatch.setattr(cli, "_repo_root", lambda start=None: None)
    _write(tmp_path, "case", "20261001_001_deploy_cert_fail.md", "# deploy cert fail\n\n인증서 갱신\n")
    argv = ["note_cli", "get-output-path", "case", "--title", "deploy cert fail again", "--scope", "home"]
    monkeypatch.setattr(sys, "argv", argv)
    cli.main()
    out = json.loads(capsys.readouterr().out)
    assert out["related"][0]["score"] > 0
    monkeypatch.setattr(sys, "argv", ["note_cli", "get-output-path", "case", "--title", "완전 새 주제 qwerty", "--scope", "home"])
    cli.main()
    assert "related" not in json.loads(capsys.readouterr().out)


def test_github_cli_joblog_attaches_note_hits(tmp_path, monkeypatch, capsys):
    spec = importlib.util.spec_from_file_location("github_cli", ROOT / "skills/pro-github/scripts/github_cli.py")
    gh = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gh)
    _write(tmp_path, "case", "20261001_001_itms.md", "# ITMS-90062 거부\n\n빌드 번호를 올린다\n")
    monkeypatch.setattr(gh, "get_github_pat", lambda o, r: "x")
    monkeypatch.setattr(gh, "get_job_log", lambda *a, **k: {"job_id": 1, "matched_count": 1,
                        "lines": ["Error ITMS-90062 bundle version must be higher"]})
    monkeypatch.setattr(notes, "home_root", lambda: tmp_path)
    monkeypatch.setattr(notes, "_git_root", lambda: None)
    monkeypatch.setattr(sys, "argv", ["github_cli", "actions", "joblog", "o", "r", "1"])
    gh.main()
    out = json.loads(capsys.readouterr().out)
    assert out["summary"] and out["note_hits"][0]["title"].startswith("ITMS-90062")
    # 기록이 없으면 필드 자체가 없다
    monkeypatch.setattr(notes, "home_root", lambda: tmp_path / "none")
    gh.main()
    assert "note_hits" not in json.loads(capsys.readouterr().out)
