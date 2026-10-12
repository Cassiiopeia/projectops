"""`web` 의 동작 — 모듈 하나가 동작 하나다.

새 동작: 이 폴더에 모듈을 두고 `ACTION = Action(name=..., run=..., needs=..., configure=...)` 를 내보낸다.
`web` 은 `registry.discover_actions` 로 이 폴더를 훑으므로 `commands/web/__init__.py` 는 고치지 않는다.
`needs` 는 `registry.NEEDS` 를 보라.
"""
