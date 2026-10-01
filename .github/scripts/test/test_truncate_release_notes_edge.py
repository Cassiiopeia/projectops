"""truncate_release_notes.py 예외 경로·이모지 절단 회귀 테스트 (#689).

계약: 어떤 경우에도 exit 0, 이모지 조합(국기·ZWJ)을 중간에서 자르지 않는다.
"""
import subprocess
import sys
from pathlib import Path

SCRIPT = str(Path(__file__).resolve().parent.parent / "truncate_release_notes.py")


def run(cwd, *args):
    return subprocess.run([sys.executable, SCRIPT, *args], cwd=cwd,
                          capture_output=True, text=True, encoding="utf-8")


def test_non_utf8_input_does_not_crash(tmp_path):
    (tmp_path / "in.txt").write_bytes(b"\xff\xfe bad bytes\n")
    r = run(tmp_path, "in.txt", "5", "char", "out.txt")
    assert r.returncode == 0
    assert "Traceback" not in r.stderr
    assert (tmp_path / "out.txt").exists()


def test_missing_output_dir_is_warning_exit0(tmp_path):
    (tmp_path / "in.txt").write_text("abcdefghij", encoding="utf-8")
    r = run(tmp_path, "in.txt", "5", "char", "/nonexistent/dir/out.txt")
    assert r.returncode == 0
    assert "Traceback" not in r.stderr


def test_missing_output_dir_within_limit_is_exit0(tmp_path):
    (tmp_path / "in.txt").write_text("abc", encoding="utf-8")
    r = run(tmp_path, "in.txt", "50", "char", "/nonexistent/dir/out.txt")
    assert r.returncode == 0
    assert "Traceback" not in r.stderr


def test_flag_not_split(tmp_path):
    (tmp_path / "in.txt").write_text("🇰🇷" * 4, encoding="utf-8")
    run(tmp_path, "in.txt", "4", "char", "out.txt")
    out = (tmp_path / "out.txt").read_text(encoding="utf-8")
    # 국기는 2글자 한 쌍 — 한도 4(말줄임표 포함)면 국기 1개 + 말줄임표만 남아야 한다
    assert out == "🇰🇷…"


def test_zwj_family_not_split(tmp_path):
    family = "👨‍👩‍👧"  # 5 코드포인트
    (tmp_path / "in.txt").write_text("ab" + family + family, encoding="utf-8")
    run(tmp_path, "in.txt", "5", "char", "out.txt")
    out = (tmp_path / "out.txt").read_text(encoding="utf-8")
    assert out == "ab…"


def test_variation_selector_not_split(tmp_path):
    (tmp_path / "in.txt").write_text("ab❤️cd", encoding="utf-8")
    run(tmp_path, "in.txt", "4", "char", "out.txt")
    out = (tmp_path / "out.txt").read_text(encoding="utf-8")
    assert out == "ab…"
