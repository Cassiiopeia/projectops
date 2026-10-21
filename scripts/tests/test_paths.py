# scripts/tests/test_paths.py
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import pytest  # noqa: E402
from common.paths import get_next_seq  # noqa: E402


def test_get_next_seq_nonexistent_dir_lenient_returns_001(tmp_path):
    missing = tmp_path / "does-not-exist"
    assert get_next_seq(missing, "20260602") == "001"


def test_get_next_seq_nonexistent_dir_strict_raises(tmp_path):
    missing = tmp_path / "does-not-exist"
    with pytest.raises(FileNotFoundError):
        get_next_seq(missing, "20260602", strict=True)


def test_get_next_seq_counts_files_for_today(tmp_path):
    skill_dir = tmp_path / "issue"
    skill_dir.mkdir()
    (skill_dir / "20260602_001_x.md").write_text("", encoding="utf-8")
    (skill_dir / "20260602_002_y.md").write_text("", encoding="utf-8")
    (skill_dir / "20260601_001_z.md").write_text("", encoding="utf-8")
    assert get_next_seq(skill_dir, "20260602") == "003"


def test_get_next_seq_reuses_same_title_but_not_renamed_issue_doc(tmp_path):
    # 실사고: 이슈 번호 없을 때 get-output-path 호출마다 001·002 폴더가 새로 생김 (#971)
    skill_dir = tmp_path / "launch"
    skill_dir.mkdir()
    (skill_dir / "20260602_001_로그인").mkdir()
    (skill_dir / "20260602_245_결제.md").write_text("", encoding="utf-8")   # 등록 후 실제 번호로 바꾼 문서
    assert get_next_seq(skill_dir, "20260602", title="로그인") == "001"
    assert get_next_seq(skill_dir, "20260602", title="결제") == "003"
