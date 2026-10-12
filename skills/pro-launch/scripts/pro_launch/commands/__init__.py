"""서브커맨드 — 모듈 하나가 서브커맨드 하나(또는 한 묶음)다.

새 서브커맨드: 이 폴더에 모듈을 두고 `COMMANDS = [Command(name=..., help=..., run=..., configure=...)]` 를
내보낸다. 파서 · 도움말 · 디스패치는 `registry.discover_commands` 가 만들어 주므로 다른 파일은 고치지 않는다.

규칙: 명령끼리 서로 import 하지 않는다. 둘 이상이 쓰는 것은 `runtime/` 으로 내린다 (tests/test_launch_architecture.py 가 검사).
"""
