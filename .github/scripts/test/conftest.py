"""스크립트 테스트 공통 설정."""
import pytest


@pytest.fixture(autouse=True)
def _pin_repo_language(monkeypatch):
    # 메시지 언어는 실행 위치의 version.yml 에서 정해진다(#787). 테스트가 어디서 돌든 같은 결과가 나오도록
    # 기본은 한국어로 고정한다 — 이관 전 문구를 단정하는 기존 테스트가 그대로 유효하다.
    # 언어별 동작을 보는 테스트는 lang 인자나 env 를 직접 넘긴다.
    monkeypatch.setenv("REPO_LANG", "ko")
