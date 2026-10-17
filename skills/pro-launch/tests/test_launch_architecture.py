"""pro-launch 의 구조 규칙 (#859) — 기여자가 구조를 망가뜨리지 못하게 한다.

코드를 나눠 놓아도 규칙이 말뿐이면 곧 다시 한 파일에 쌓인다. 여기서 지키려는 것:

  · 명령 하나를 추가하려면 파일 하나만 더하면 된다 (선언을 모아 파서·도움말이 만들어진다)
  · 의존은 아래로만 흐른다 — runtime 은 commands 를 모르고, 명령끼리는 서로 모른다
  · OS 마다 다른 동작은 한 곳(procs.py)에만 있고, 어느 OS 에서든 시험해 볼 수 있다
  · 모듈 하나가 깨져도 다른 명령은 돈다
  · 파일 하나가 다시 거대해지지 않는다

기기·브라우저·서버가 없어도 돈다.
"""
from __future__ import annotations

import ast
import inspect
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import pro_launch  # noqa: E402,F401  (import 경로를 맞춘다)
from pro_launch import registry  # noqa: E402
from pro_launch.cli import HELP_ORDER, build_parser, load_commands  # noqa: E402
from pro_launch.runtime import procs  # noqa: E402

PKG = SCRIPTS / "pro_launch"
MAX_LINES = 450   # 이보다 길어지면 나눌 때다 — 원래 한 파일이 3,500줄이었다


def _py_files(sub: str = "") -> list[Path]:
    return sorted(p for p in (PKG / sub).rglob("*.py") if "__pycache__" not in p.parts)


def _imported_modules(path: Path) -> set[str]:
    mods: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            mods |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            mods.add(node.module)
            # `from pro_launch.commands import web` 는 모듈 web 을 들이는 것이다
            mods |= {f"{node.module}.{a.name}" for a in node.names}
    return mods


# ── 선언과 발견 ──────────────────────────────────────────────────────────


def test_every_help_order_command_is_registered():
    names = [c.name for c in load_commands()]
    assert set(HELP_ORDER) <= set(names), set(HELP_ORDER) - set(names)
    assert len(names) == len(set(names)), "서브커맨드 이름이 겹친다"


def test_commands_declare_help_and_a_callable_run():
    for cmd in load_commands():
        assert cmd.help.strip(), f"{cmd.name}: help 가 비었다"
        assert callable(cmd.run), cmd.name


def test_parser_is_built_from_the_declarations():
    parser = build_parser()
    sub = next(a for a in parser._actions if a.__class__.__name__ == "_SubParsersAction")
    assert list(sub.choices) == [c.name for c in load_commands()]


def test_no_module_failed_to_load():
    load_commands()
    assert registry.LOAD_ERRORS == {}, registry.LOAD_ERRORS


@pytest.mark.parametrize("pkg_path,expected", [
    ("pro_launch.commands.web.actions",
     {"setup", "open", "goto", "find", "click", "type", "text", "shot", "assert", "console", "close",
      "viewport", "route", "inspect", "select", "check", "press", "hover", "dialog", "download",
      "wait", "scroll", "upload", "script", "tab", "login"}),
    ("pro_launch.commands.app.actions", {"shot", "launch", "type", "tap", "swipe", "tree", "terminate",
                                         "relaunch", "location", "permission", "push", "openurl", "run",
                                         "session", "flow"}),
])
def test_actions_are_discovered_from_their_folder(pkg_path, expected):
    import importlib
    actions = registry.discover_actions(importlib.import_module(pkg_path))
    assert set(actions) == expected


# 동작이 받는 인자 수는 needs 가 정한다 — 디스패처가 그대로 부르므로 어긋나면 런타임에 터진다
_ARITY = {"nothing": 1, "launch": 3, "state_offline": 3, "state_online": 3, "page": 3}


@pytest.mark.parametrize("pkg_path", ["pro_launch.commands.web.actions", "pro_launch.commands.app.actions"])
def test_every_action_matches_the_signature_its_needs_promises(pkg_path):
    import importlib
    for name, act in registry.discover_actions(importlib.import_module(pkg_path)).items():
        params = inspect.signature(act.run).parameters
        want = 1 if pkg_path.endswith("app.actions") else _ARITY[act.needs]
        assert len(params) == want, f"{pkg_path}.{name}: needs={act.needs} 인데 인자 {len(params)}개"


def test_action_with_unknown_needs_is_rejected():
    with pytest.raises(ValueError):
        registry.Action(name="x", run=lambda: None, needs="whatever")


def test_a_broken_module_does_not_take_down_the_others(tmp_path, monkeypatch):
    pkg = tmp_path / "fakecmds"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "good.py").write_text(textwrap.dedent("""
        from pro_launch.registry import Command
        COMMANDS = [Command(name="good", help="ok", run=lambda a: 0)]
    """), encoding="utf-8")
    (pkg / "bad.py").write_text("raise RuntimeError('boom at import')\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    import importlib
    registry.LOAD_ERRORS.clear()
    found = registry.discover_commands(importlib.import_module("fakecmds"))
    try:
        assert [c.name for c in found] == ["good"]
        assert "bad" in registry.LOAD_ERRORS and "boom at import" in registry.LOAD_ERRORS["bad"]
    finally:
        registry.LOAD_ERRORS.clear()


def test_duplicate_command_names_are_an_error(tmp_path, monkeypatch):
    pkg = tmp_path / "dupcmds"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    for n in ("a", "b"):
        (pkg / f"{n}.py").write_text(textwrap.dedent("""
            from pro_launch.registry import Command
            COMMANDS = [Command(name="same", help="x", run=lambda a: 0)]
        """), encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    import importlib
    with pytest.raises(ValueError, match="겹친다"):
        registry.discover_commands(importlib.import_module("dupcmds"))


# ── 의존 방향 ────────────────────────────────────────────────────────────


def test_runtime_never_imports_commands():
    bad = []
    for f in _py_files("runtime"):
        for mod in _imported_modules(f):
            if mod.startswith("pro_launch.commands"):
                bad.append(f"{f.relative_to(PKG)} → {mod}")
    assert not bad, "아래층(runtime)이 위층(commands)을 안다:\n" + "\n".join(bad)


def test_commands_do_not_import_each_other():
    """둘 이상이 쓰는 것은 runtime 으로 내린다. 명령 사이에 의존이 생기면 하나를 바꿀 때 다른 것이 깨진다."""
    bad = []
    for f in _py_files("commands"):
        rel = f.relative_to(PKG / "commands")
        own = rel.parts[0].removesuffix(".py")
        if own == "__init__":
            continue
        for mod in _imported_modules(f):
            parts = mod.split(".")
            if parts[:2] == ["pro_launch", "commands"] and len(parts) >= 3 and parts[2] != own:
                bad.append(f"{f.relative_to(PKG)} → {mod}")
    assert not bad, "명령이 다른 명령을 import 한다:\n" + "\n".join(bad)


def test_nothing_in_the_package_imports_the_entry_point():
    bad = [f.relative_to(PKG).as_posix() for f in _py_files() if "launch_cli" in _imported_modules(f)]
    assert not bad, bad


# ── OS 분기는 한 곳 ──────────────────────────────────────────────────────


def _platform_branches(path: Path) -> list[int]:
    """`sys.platform` 을 비교하거나 startswith 로 가르는 줄. 출력에 담는 것은 분기가 아니다."""
    lines = []

    def is_platform(n) -> bool:
        return (isinstance(n, ast.Attribute) and n.attr == "platform"
                and isinstance(n.value, ast.Name) and n.value.id == "sys")

    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Compare) and (is_platform(node.left) or any(is_platform(c) for c in node.comparators)):
            lines.append(node.lineno)
        elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
              and node.func.attr == "startswith" and is_platform(node.func.value)):
            lines.append(node.lineno)
    return lines


def test_os_branching_lives_only_in_procs():
    found = {f.relative_to(PKG).as_posix(): _platform_branches(f) for f in _py_files()}
    found = {k: v for k, v in found.items() if v}
    assert set(found) <= {"runtime/procs.py"}, f"OS 분기가 procs.py 밖에 있다: {found}"


# ── 파일 크기 ────────────────────────────────────────────────────────────


def test_modules_stay_small():
    big = {f.relative_to(PKG).as_posix(): n for f in _py_files()
           if (n := len(f.read_text(encoding="utf-8").splitlines())) > MAX_LINES}
    assert not big, f"{MAX_LINES}줄을 넘었다 — 나눌 때다: {big}"


def test_entry_point_stays_thin():
    n = len((SCRIPTS / "launch_cli.py").read_text(encoding="utf-8").splitlines())
    assert n < 80, f"launch_cli.py 가 {n}줄이다 — 구현은 pro_launch/ 에 둔다"


# ── procs: OS 를 흉내 내 어느 곳에서든 시험한다 ──────────────────────────


@pytest.mark.parametrize("platform,expect", [
    ("win32", {"creationflags": 0x00000008 | 0x00000200}),
    ("linux", {"start_new_session": True}),
    ("darwin", {"start_new_session": True}),
])
def test_detach_options_per_platform(monkeypatch, platform, expect):
    monkeypatch.setattr(sys, "platform", platform)
    assert procs.detach_options() == expect


@pytest.mark.parametrize("platform,needle", [("win32", "taskkill /PID 42 /T /F"), ("linux", "kill -9 42")])
def test_manual_kill_command_per_platform(monkeypatch, platform, needle):
    monkeypatch.setattr(sys, "platform", platform)
    assert procs.manual_kill_command(42) == needle


def test_pid_alive_uses_the_windows_probe_not_os_kill_on_windows(monkeypatch):
    """윈도우에서 os.kill(pid, 0) 은 확인이 아니라 종료다 — 그 길로 가면 브라우저가 죽는다."""
    from common import proc as common_proc   # 생존 확인 단일 원본 (procs 는 재노출)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(common_proc, "_pid_alive_windows", lambda pid: True)

    def forbidden(*a, **k):
        raise AssertionError("윈도우에서 os.kill 을 불렀다")
    monkeypatch.setattr(common_proc.os, "kill", forbidden)
    assert procs.pid_alive is common_proc.pid_alive
    assert procs.pid_alive(1234) is True


def test_kill_browser_on_windows_asks_nicely_then_forces(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    calls: list[list[str]] = []
    state = {"forced": False}

    def fake_run(cmd, **kw):
        calls.append(list(cmd))
        if "/F" in cmd:
            state["forced"] = True
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(procs.subprocess, "run", fake_run)
    # 정중히 끝내자는 요청에는 안 죽고, /F 가 간 뒤에야 죽는다
    monkeypatch.setattr(procs, "_pid_alive_windows", lambda pid: not state["forced"])
    monkeypatch.setattr(procs.time, "sleep", lambda s: None)
    assert procs.kill_browser(99, grace=0.01) is False
    assert calls == [["taskkill", "/PID", "99", "/T"], ["taskkill", "/PID", "99", "/T", "/F"]]


def test_kill_browser_on_windows_stops_at_the_polite_request_when_it_works(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    calls: list[list[str]] = []
    monkeypatch.setattr(procs.subprocess, "run",
                        lambda cmd, **kw: calls.append(list(cmd)) or subprocess.CompletedProcess(cmd, 0, "", ""))
    monkeypatch.setattr(procs, "_pid_alive_windows", lambda pid: False)
    assert procs.kill_browser(7, grace=0.01) is False
    assert calls == [["taskkill", "/PID", "7", "/T"]]
