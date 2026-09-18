"""스킬 테스트 공통 설정.

**로컬은 전부 돌리고, CI는 실제 도구가 필요한 것을 건너뛴다.**

이 저장소의 테스트는 템플릿을 쓰는 사람의 프로젝트가 아니라 **이 레포 자신의 코드**를
검사한다 (`skills/` 는 사용자 프로젝트로 복사되지 않는다). 그래서 GitHub 러너에서까지
브라우저를 받아 띄울 이유가 없다 — 무료 러너 가용량을 그렇게 쓸 만한 가치가 없고,
그 계약은 실제 브라우저가 있는 개발 기계에서 보는 편이 더 정확하다.

  로컬   도구가 있으면 돈다. 없으면 그 테스트만 건너뛴다.
  CI     `local_only` 는 무조건 건너뛴다.

`CI` 환경변수는 GitHub Actions가 자동으로 넣는다.
"""
import os

import pytest

_MARKER = "local_only"


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        f"{_MARKER}: 실제 도구(브라우저·기기·서버)가 있어야 의미가 있다. CI에서는 건너뛴다",
    )


def pytest_collection_modifyitems(config, items):
    # GitHub Actions·대부분의 CI가 CI=true 를 넣는다. 로컬에는 없다.
    if not os.environ.get("CI"):
        return
    skip = pytest.mark.skip(
        reason="CI에서는 실제 도구가 필요한 테스트를 돌리지 않는다 — 로컬에서 본다")
    for item in items:
        if _MARKER in item.keywords:
            item.add_marker(skip)
