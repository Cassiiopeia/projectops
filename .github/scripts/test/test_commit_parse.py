"""커밋 제목 파싱 — 두 컨벤션 인식 회귀 테스트 (#566).

실사고: tier-2(Conventional Commits)만 인식하는 정규식이라 projectops 표준
"제목 : feat : 내용"이 전부 "기타"로 떨어졌다. AI provider가 죽은 뒤 이 경로가
실제로 쓰이면서 모든 저장소의 릴리스 노트가 원문 한 덩어리로 나왔다.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "changelog_providers"))

from _common import classify, clean_message, parse_commit, sections_to_markdown  # noqa: E402


class TestTier1:
    """projectops 표준 — 제목이 앞에 오고 타입이 중간에 온다."""

    def test_feat(self):
        assert parse_commit("로그인 화면 개선 : feat : 소셜 로그인 버튼 추가") == ("feat", "소셜 로그인 버튼 추가")

    def test_fix(self):
        assert parse_commit("결제 오류 수정 : fix : 카드 중복 청구 해결") == ("fix", "카드 중복 청구 해결")

    def test_refactor_maps_to_improve(self):
        assert parse_commit("성능 개선 : refactor : 목록 로딩 속도 개선")[0] == "improve"

    def test_docs(self):
        assert parse_commit("문서 정리 : docs : 설치 가이드 보강")[0] == "docs"

    def test_breaking_marker(self):
        # "!"가 붙어도 타입 인식은 동일 (승격 폭 판정은 changelog_manager 담당)
        assert parse_commit("CLI 인자 변경 : feat! : 구 플래그 제거") == ("feat", "구 플래그 제거")

    def test_url_and_issue_removed(self):
        got = parse_commit("로그인 개선 : feat : 버튼 추가 #123 https://github.com/a/b/issues/1")
        assert got == ("feat", "버튼 추가")

    def test_spacing_variants(self):
        # 콜론 주변 공백이 달라도 인식
        assert parse_commit("제목 :feat: 내용")[0] == "feat"
        assert parse_commit("제목 : feat :내용")[0] == "feat"


class TestTier2:
    """Conventional Commits — 기존 동작이 깨지지 않아야 한다."""

    def test_feat(self):
        assert parse_commit("feat: 다크 모드 지원") == ("feat", "다크 모드 지원")

    def test_scope(self):
        assert parse_commit("fix(api): 타임아웃 처리") == ("fix", "타임아웃 처리")

    def test_breaking_marker(self):
        assert parse_commit("feat!: 구 API 제거") == ("feat", "구 API 제거")


class TestFallback:
    """컨벤션을 따르지 않는 커밋도 버리지 않는다."""

    def test_free_form_goes_to_etc(self):
        assert parse_commit("그냥 대충 커밋함") == ("etc", "그냥 대충 커밋함")

    def test_free_form_keeps_original(self):
        # 내용을 잃지 않아야 한다 — 빈 문자열로 만들지 말 것
        assert parse_commit("wip")[1] == "wip"

    def test_url_only_line_keeps_original(self):
        # 노이즈 제거 후 빈 문자열이 되면 원문을 보존한다
        assert parse_commit("https://example.com")[1] == "https://example.com"


class TestClassify:
    def test_sections_grouped(self):
        sections = classify([
            "로그인 개선 : feat : 소셜 로그인 추가",
            "feat: 다크 모드",
            "결제 수정 : fix : 중복 청구 해결",
        ])
        assert sections["feat"] == ["소셜 로그인 추가", "다크 모드"]
        assert sections["fix"] == ["중복 청구 해결"]

    def test_markdown_has_no_prefix_leak(self):
        md = sections_to_markdown(classify(["로그인 개선 : feat : 소셜 로그인 추가"]))
        assert "소셜 로그인 추가" in md
        assert " : feat : " not in md, "타입 prefix가 릴리스 노트에 새면 안 된다"
        assert "**새 기능**" in md

    def test_empty(self):
        assert all(v == [] for v in classify([]).values())


class TestCleanMessage:
    """구 호출부 하위호환 — 내용만 남긴다."""

    def test_tier1(self):
        assert clean_message("로그인 개선 : feat : 버튼 추가") == "버튼 추가"

    def test_tier2(self):
        assert clean_message("feat: 버튼 추가") == "버튼 추가"
