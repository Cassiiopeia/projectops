"""changelog_manager export / update-from-summary 회귀 테스트 (#687, #688).

스크립트를 실제 프로세스로 돌려 종료 코드·산출 파일까지 본다 (임시 디렉터리에서 실행).
"""
import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = str(Path(__file__).resolve().parent.parent / "changelog_manager.py")

MD = """# Changelog

## [1.2.3] - 2026-01-01

**기능**
- 하나
- 둘

---

## [1.2.2] - 2025-12-31

**버그**
- 셋
"""


def run(cwd, *args, env=None):
    e = {k: v for k, v in os.environ.items()
         if k not in ("VERSION", "TODAY", "TIMESTAMP", "PROJECT_TYPE", "PR_NUMBER")}
    e.update(env or {})
    e["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run([sys.executable, SCRIPT, *args], cwd=cwd, env=e,
                          capture_output=True, text=True, encoding="utf-8")


# ── #687 export 의 CHANGELOG.md 폴백 ──────────────────────────────────
def test_export_md_fallback_returns_section(tmp_path):
    (tmp_path / "CHANGELOG.md").write_text(MD, encoding="utf-8")
    r = run(tmp_path, "export", "--version", "1.2.3")
    assert r.returncode == 0
    assert "- 하나" in r.stdout and "- 둘" in r.stdout
    assert "앱 안정성" not in r.stdout
    assert "셋" not in r.stdout  # 다음 버전 섹션은 섞이지 않는다
    assert "---" not in r.stdout  # 섹션 구분선이 스토어 노트에 남지 않는다


def test_export_md_fallback_last_section(tmp_path):
    (tmp_path / "CHANGELOG.md").write_text(MD, encoding="utf-8")
    r = run(tmp_path, "export", "--version", "1.2.2")
    assert "- 셋" in r.stdout


# ── #688 update-from-summary 방어 ─────────────────────────────────────
ENV = {"VERSION": "1.2.3", "PROJECT_TYPE": "basic", "TODAY": "2026-01-01",
       "PR_NUMBER": "5", "TIMESTAMP": "t"}


def _prep(tmp_path):
    (tmp_path / "pr_body.md").write_text("* **새 기능**\n  * 항목\n", encoding="utf-8")


def _versions(tmp_path):
    d = json.loads((tmp_path / "CHANGELOG.json").read_text(encoding="utf-8"))
    return [r["version"] for r in d["releases"]]


def test_update_is_idempotent(tmp_path):
    _prep(tmp_path)
    assert run(tmp_path, "update-from-summary", env=ENV).returncode == 0
    assert run(tmp_path, "update-from-summary", env=ENV).returncode == 0
    assert _versions(tmp_path) == ["1.2.3"]
    run(tmp_path, "generate-md")
    md = (tmp_path / "CHANGELOG.md").read_text(encoding="utf-8")
    assert md.count("## [1.2.3]") == 1


def test_corrupt_json_is_not_overwritten(tmp_path):
    _prep(tmp_path)
    broken = '{"metadata":{},"releases":[{"version":"0.9"},\n<<<<<<< HEAD\n'
    (tmp_path / "CHANGELOG.json").write_text(broken, encoding="utf-8")
    r = run(tmp_path, "update-from-summary", env={**ENV, "VERSION": "2.0.0"})
    assert r.returncode != 0
    assert (tmp_path / "CHANGELOG.json").read_text(encoding="utf-8") == broken


def test_missing_version_fails(tmp_path):
    _prep(tmp_path)
    r = run(tmp_path, "update-from-summary")
    assert r.returncode != 0
    assert not (tmp_path / "CHANGELOG.json").exists()


def test_generate_md_does_not_truncate_on_bad_structure(tmp_path):
    (tmp_path / "CHANGELOG.md").write_text("ORIGINAL\n", encoding="utf-8")
    (tmp_path / "CHANGELOG.json").write_text('{"metadata":{},"releases":[1,2]}', encoding="utf-8")
    r = run(tmp_path, "generate-md")
    assert r.returncode != 0
    assert (tmp_path / "CHANGELOG.md").read_text(encoding="utf-8") == "ORIGINAL\n"
