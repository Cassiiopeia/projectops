"""gh_client 구현 모듈 모음. 호출부는 `common.gh_client` 로만 들어온다.

모듈 사이 호출은 `client.X`(common.gh_client) 경유 — 테스트가 gh_client 속성을 바꿔 끼우면 내부 호출에도 반영.
"""

# 하위 모듈을 직접 import 해도 gh_client 가 먼저 완성되게 한다 (순환 import 순서 고정)
from common import gh_client  # noqa: F401
