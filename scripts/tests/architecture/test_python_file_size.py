"""스킬 스크립트 크기 상한: 파일당 450줄 (#913)

대상 3곳: skills/*/scripts, scripts/ (tests 제외), plugins/*/skills/*/scripts
넘으면 진입 파일은 얇게 두고 서브커맨드를 패키지로 나눈다 (모범: skills/pro-launch/scripts/pro_launch)
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MAXIMUM_LINES_PER_FILE = 450
SKIPPED_DIRECTORY_NAMES = {"__pycache__", "venv", ".venv", "tests"}

# 동결 목록: 상한을 넘는 기존 파일 > 이 줄 수보다 늘면 실패, 나누면 목록에서 지운다
FROZEN_LINE_COUNT_BY_PATH = {
    # 플랫폼 백엔드(Android adb·iOS maestro)가 한 모듈 — 백엔드별 분할 전
    "skills/pro-launch/scripts/app_input.py": 461,
}


def _script_files() -> list:
    bases = [*ROOT.glob("skills/*/scripts"), ROOT / "scripts", *ROOT.glob("plugins/*/skills/*/scripts")]
    files = set()
    for base in bases:
        for path in base.rglob("*.py"):
            relative = path.relative_to(ROOT)
            if not SKIPPED_DIRECTORY_NAMES.intersection(relative.parts):
                files.add(relative.as_posix())
    return sorted(files)


def _line_count(relative: str) -> int:
    return len((ROOT / relative).read_text(encoding="utf-8").splitlines())


def test_script_files_stay_under_line_limit():
    oversized = []
    for relative in _script_files():
        lines = _line_count(relative)
        allowed = max(MAXIMUM_LINES_PER_FILE, FROZEN_LINE_COUNT_BY_PATH.get(relative, 0))
        if lines > allowed:
            oversized.append(f"{relative}: {lines}줄 (상한 {allowed})")
    assert not oversized, "파일 크기 상한 초과 — 진입 파일 + 패키지로 나눈다:\n" + "\n".join(oversized)


def test_frozen_entries_are_still_needed():
    stale = [f"{relative}: {_line_count(relative) if (ROOT / relative).exists() else '없음'}"
             for relative in FROZEN_LINE_COUNT_BY_PATH
             if not (ROOT / relative).exists() or _line_count(relative) <= MAXIMUM_LINES_PER_FILE]
    assert not stale, "상한 아래로 내려간 동결 항목 — 목록에서 지운다:\n" + "\n".join(stale)
