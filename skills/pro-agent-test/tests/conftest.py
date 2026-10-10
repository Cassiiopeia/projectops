"""pro-agent-test 테스트 공통 — 실제 ~/.projectops 를 건드리지 않는다 (#836).

HOME 을 넘기지 않는 테스트도 상태 루트(PROJECTOPS_HOME)는 테스트마다 임시 폴더로 돌린다.
경로를 `tmp_path/home/.projectops` 로 두는 이유: HOME 을 `tmp_path/home` 으로 바꾸는 테스트의
기대 경로와 그대로 맞는다 (pro-launch tests/conftest.py 와 같은 방식).
"""
import pytest


@pytest.fixture(autouse=True)
def _isolated_projectops_home(tmp_path, monkeypatch):
    home = tmp_path / "home" / ".projectops"
    monkeypatch.setenv("PROJECTOPS_HOME", str(home))
    return home
