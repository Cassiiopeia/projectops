"""버전 증가 연산 테스트 (이슈 #546).

increment_patch()는 기존 호출 계약이라 그대로 살아 있어야 하고,
increment_version()은 bump 미지정 시 그와 동일하게 동작해야 한다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from version_manager import increment_patch, increment_version, parse_bump_flag


# ── 승격 폭별 연산 ────────────────────────────────────────────────────
def test_major_resets_minor_and_patch_to_zero():
    assert increment_version("1.2.3", "major") == "2.0.0"
    assert increment_version("4.2.45", "major") == "5.0.0"

def test_minor_resets_patch_to_zero():
    assert increment_version("1.2.3", "minor") == "1.3.0"
    assert increment_version("4.2.45", "minor") == "4.3.0"

def test_patch_increments_last_segment():
    assert increment_version("1.2.3", "patch") == "1.2.4"
    assert increment_version("4.2.45", "patch") == "4.2.46"

def test_default_bump_is_patch():
    # 인자 생략 시 기존 동작(patch) 보존 — .sh shim 경유 구 호출이 그대로 살아야 한다.
    assert increment_version("1.2.3") == increment_patch("1.2.3")

def test_increment_patch_still_works():
    assert increment_patch("0.9.9") == "0.9.10"

def test_double_digit_segments():
    assert increment_version("10.20.30", "minor") == "10.21.0"
    assert increment_version("10.20.30", "major") == "11.0.0"


# ── --bump 플래그 파싱 ────────────────────────────────────────────────
def test_flag_absent_defaults_to_patch():
    assert parse_bump_flag(["version_manager.py", "increment"]) == "patch"

def test_flag_parses_each_level():
    for level in ("major", "minor", "patch"):
        argv = ["version_manager.py", "increment", "--bump", level]
        assert parse_bump_flag(argv) == level

def test_invalid_level_returns_none():
    assert parse_bump_flag(["version_manager.py", "increment", "--bump", "huge"]) is None

def test_missing_value_returns_none():
    assert parse_bump_flag(["version_manager.py", "increment", "--bump"]) is None
