"""pro-launch 테스트 공통 — 실제 ~/.projectops 를 건드리지 않는다 (#836).

브라우저 테스트는 HOME 을 바꿀 수 없다(macOS Chrome 이 멈춘다, 실측). 그대로 두면 실제 홈에
`acme__thing`·`webproj` 같은 버킷이 생기고 실제 기억의 memory_seen.json 까지 건드린다.
HOME 은 그대로 두고 상태 루트(PROJECTOPS_HOME)만 테스트마다 임시 폴더로 돌린다.

경로를 `tmp_path/home/.projectops` 로 두는 이유: HOME 을 `tmp_path/home` 으로 바꾸는 기존
테스트의 기대 경로와 그대로 맞는다.
"""
import pytest


@pytest.fixture(autouse=True)
def _isolated_projectops_home(tmp_path, monkeypatch):
    home = tmp_path / "home" / ".projectops"
    monkeypatch.setenv("PROJECTOPS_HOME", str(home))
    return home
