"""semver 승격 폭 판정 테스트 (이슈 #546).

핵심 회귀 지점: projectops 커밋 컨벤션("제목 : type : 내용")에서 minor·major가
모두 잡혀야 한다. 참조 구현(project-auto-wizard)은 Conventional Commits 전용이라
tier-1 breaking 마커를 커버하지 않았다 — 그 빈 자리를 여기서 고정한다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from changelog_manager import classify_bump_level


# ── projectops 컨벤션 (tier-1) ────────────────────────────────────────
def test_tier1_feat_is_minor():
    assert classify_bump_level(["로그인 기능 : feat : 소셜 로그인 추가"]) == "minor"

def test_tier1_feat_with_trailing_url_is_minor():
    lines = ["릴리스 버전 관리 : feat : semver 승격 도입 https://github.com/o/r/issues/546"]
    assert classify_bump_level(lines) == "minor"

def test_tier1_bang_marker_is_major():
    # 이 레포 컨벤션의 breaking 마커 — 참조 구현에는 없던 경로다.
    assert classify_bump_level(["설정 포맷 변경 : feat! : 구 키 지원 중단"]) == "major"

def test_tier1_bang_on_any_type_is_major():
    assert classify_bump_level(["기본값 변경 : fix! : 타임아웃 단위 변경"]) == "major"
    assert classify_bump_level(["CLI 정리 : chore! : deprecated 플래그 제거"]) == "major"

def test_tier1_non_feat_is_patch():
    lines = [
        "문서 정리 : docs : 설치 안내 보강",
        "버그 수정 : fix : 널 참조 수정",
        "의존성 : chore : 패키지 갱신",
    ]
    assert classify_bump_level(lines) == "patch"

def test_tier1_title_containing_colon_is_not_truncated():
    # 타입 앞 콜론에는 공백이 선행해야 하므로 제목 안의 맨몸 콜론에서 잘리지 않는다.
    assert classify_bump_level(["v1:2 마이그레이션 : feat : 신규 포맷 지원"]) == "minor"


# ── Conventional Commits (tier-2) ─────────────────────────────────────
def test_tier2_feat_is_minor():
    assert classify_bump_level(["feat: add login flow"]) == "minor"

def test_tier2_bang_marker_is_major():
    assert classify_bump_level(["feat!: drop legacy config format"]) == "major"
    assert classify_bump_level(["fix!: change default timeout unit"]) == "major"
    assert classify_bump_level(["chore!: remove deprecated CLI flag"]) == "major"

def test_tier2_bang_with_scope_is_major():
    assert classify_bump_level(["feat(api)!: change response shape"]) == "major"

def test_tier2_scope_without_bang_is_minor():
    assert classify_bump_level(["feat(auth): add oauth"]) == "minor"

def test_tier2_non_feat_is_patch():
    assert classify_bump_level(["fix: crash on start", "chore: bump deps"]) == "patch"

def test_tier2_chore_aliases_are_patch():
    assert classify_bump_level(["perf: speed up parser", "ci: cache deps"]) == "patch"


# ── 우선순위 / 제외 규칙 ──────────────────────────────────────────────
def test_major_wins_over_minor_in_same_release():
    lines = ["설정 변경 : feat! : 구 키 제거", "로그인 : feat : 소셜 로그인"]
    assert classify_bump_level(lines) == "major"

def test_minor_wins_over_patch_in_same_release():
    lines = ["버그 수정 : fix : 널 참조", "로그인 : feat : 소셜 로그인"]
    assert classify_bump_level(lines) == "minor"

def test_skip_ci_lines_are_ignored():
    # 릴리스 확정 커밋이 구간에 섞여도 승격 폭을 바꾸지 않아야 한다.
    lines = ["docs(readme): update version to v4.2.45 [skip ci]"]
    assert classify_bump_level(lines) == "patch"

def test_skip_ci_feat_line_is_ignored():
    assert classify_bump_level(["feat: something [skip ci]"]) == "patch"

def test_merge_commits_are_ignored():
    assert classify_bump_level(["Merge pull request #123 from o/feat-branch"]) == "patch"

def test_unclassified_free_form_is_patch():
    # AI 보조 판정을 쓰지 않으므로 자유형식은 언제나 patch다 (결정적).
    assert classify_bump_level(["updated stuff", "wip", "작업중"]) == "patch"

def test_empty_input_is_patch():
    assert classify_bump_level([]) == "patch"

def test_blank_lines_are_ignored():
    assert classify_bump_level(["", "   ", "로그인 : feat : 소셜"]) == "minor"
