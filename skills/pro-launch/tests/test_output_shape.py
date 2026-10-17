"""전역 출력 모양 옵션 --brief · --fields 와 키 순서 (#898).

잘라 읽다가 next·memory·known_fix 를 잃던 문제 — 줄여도 그 키들은 남고, 플래그가 없으면 키 집합이 그대로인지 본다.
"""
from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from pro_launch import cli  # noqa: E402
from pro_launch.runtime import output as rt_output  # noqa: E402
from pro_launch.runtime.context import OUTPUT_CTX  # noqa: E402


@pytest.fixture(autouse=True)
def reset_output_shape():
    OUTPUT_CTX.clear()
    yield
    OUTPUT_CTX.clear()


def _sample_failure() -> dict:
    return {"ok": False, "code": "boom", "error": "실패", "path": "/x", "url": "u",
            "learn_hint": "h", "summary": "요약", "known_fix": [{"id": "k"}], "next": "다음",
            "memory": [{"key": "m"}]}


def _run_main(*argv: str) -> tuple[int, dict]:
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        return_code = cli.main(list(argv))
    return return_code, json.loads(buffer.getvalue().strip().splitlines()[-1])


# 순서: 머리 4필드 > 안내 > 나머지 (값은 그대로)
def test_order_puts_head_then_guidance_then_rest():
    payload = _sample_failure()
    shaped = rt_output.shape_payload(dict(payload))
    assert list(shaped)[:7] == ["ok", "code", "summary", "next", "known_fix", "memory", "learn_hint"]
    assert list(shaped)[7:] == ["error", "path", "url"]
    assert shaped == payload


# 플래그 없음: 키 집합 그대로 (하위호환)
def test_no_flag_keeps_every_key():
    payload = _sample_failure()
    assert set(rt_output.shape_payload(dict(payload))) == set(payload)


def test_missing_head_keys_get_defaults_in_front():
    shaped = rt_output.shape_payload({"path": "/x"})
    assert list(shaped) == ["ok", "code", "summary", "next", "path"]
    assert shaped["ok"] is True and shaped["code"] == "ok"


def test_fields_keeps_named_keys_and_always_kept_keys():
    OUTPUT_CTX.update(field_names=["path"])
    shaped = rt_output.shape_payload(_sample_failure())
    assert list(shaped) == ["ok", "code", "summary", "next", "known_fix", "memory", "learn_hint", "path"]


def test_brief_keeps_core_and_error_only():
    OUTPUT_CTX.update(is_brief=True)
    shaped = rt_output.shape_payload(_sample_failure())
    assert set(shaped) == {"ok", "code", "summary", "next", "error", "known_fix", "memory", "learn_hint"}


def test_brief_and_fields_union():
    OUTPUT_CTX.update(is_brief=True, field_names=["url"])
    assert "url" in rt_output.shape_payload(_sample_failure())


# 옵션 꺼내기: 서브커맨드 앞·뒤 · = 형식 · `--` 뒤는 건드리지 않음
@pytest.mark.parametrize("argv, expected_rest, expected_brief, expected_fields", [
    (["--brief", "doctor"], ["doctor"], True, None),
    (["web", "shot", "--brief"], ["web", "shot"], True, None),
    (["--fields", "a,b", "doctor"], ["doctor"], False, ["a", "b"]),
    (["doctor", "--fields=a", "--fields", "b"], ["doctor"], False, ["a", "b"]),
    (["local", "sudo", "--", "ls", "--brief"], ["local", "sudo", "--", "ls", "--brief"], False, None),
])
def test_pop_output_options(argv, expected_rest, expected_brief, expected_fields):
    rest, is_brief, field_names, option_error = cli._pop_output_options(argv)
    assert (rest, is_brief, field_names, option_error) == (expected_rest, expected_brief, expected_fields, None)


def test_fields_without_value_is_bad_args():
    return_code, payload = _run_main("doctor", "--fields")
    assert return_code == 1 and payload["code"] == "bad_args"


# 실제 명령 경로: 뒤에 붙여도 · 앞에 붙여도 줄어든다
@pytest.mark.parametrize("argv", [("doctor", "--brief"), ("--brief", "doctor")])
def test_brief_on_real_command(argv):
    _, payload = _run_main(*argv)
    assert set(payload) <= set(rt_output.BRIEF_KEYS)
    assert list(payload)[:4] == ["ok", "code", "summary", "next"]


def test_fields_on_real_command_and_no_flag_compatibility():
    _, full = _run_main("doctor")
    assert list(full)[:4] == ["ok", "code", "summary", "next"]
    extra_key = next(k for k in full if k not in rt_output.BRIEF_KEYS)
    _, narrowed = _run_main("doctor", "--fields", extra_key)
    assert extra_key in narrowed and set(narrowed) <= {*rt_output.BRIEF_KEYS, extra_key}


def test_bad_args_path_is_shaped():
    _, payload = _run_main("no-such-command", "--brief")
    assert payload["code"] == "bad_args"
    assert set(payload) <= {*rt_output.BRIEF_KEYS}


def test_handler_error_path_is_shaped(monkeypatch):
    def broken_handler(_args):
        raise RuntimeError("boom")

    parser = cli.build_parser()
    original_parse = parser.parse_args

    def parse_with_broken_handler(raw):
        parsed = original_parse(raw)
        parsed.func = broken_handler
        return parsed

    parser.parse_args = parse_with_broken_handler
    monkeypatch.setattr(cli, "build_parser", lambda: parser)
    _, payload = _run_main("doctor", "--brief")
    assert payload["code"] == "handler_error" and "error" in payload
    assert set(payload) <= set(rt_output.BRIEF_KEYS)


# 이름 충돌 방지: 어떤 서브커맨드도 --brief · --fields 를 자기 옵션으로 쓰지 않는다 (전역 옵션이 먼저 꺼낸다)
def test_no_subcommand_defines_output_options():
    def walk(parser):
        for action in parser._actions:
            yield action
            for child in (getattr(action, "choices", None) or {}).values() if hasattr(action, "_name_parser_map") else ():
                yield from walk(child)

    parser = cli.build_parser()
    top_level = {id(a) for a in parser._actions}
    clashing = [a.option_strings for a in walk(parser)
                if id(a) not in top_level and set(a.option_strings) & {cli.BRIEF_OPTION, cli.FIELDS_OPTION}]
    assert clashing == []


# 원인 한 줄(first_error)은 머리 바로 뒤, 안내 앞 · --brief 에도 남는다
def test_first_error_follows_head_and_survives_brief():
    payload = {**_sample_failure(), "output_tail": "...", "first_error": "x.dart:1: Error: y"}
    assert list(rt_output.shape_payload(dict(payload)))[4] == "first_error"
    OUTPUT_CTX.update(is_brief=True)
    assert "first_error" in rt_output.shape_payload(dict(payload))
