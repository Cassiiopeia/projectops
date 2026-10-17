"""인자 오류 진단: 모르는 옵션·서브커맨드 > 비슷한 이름 > 그 명령의 옵션 목록 > 예시 한 줄 (#886).

bad_args 가 가장 잦은 실패인데 "usage 를 보라"뿐이라 agent 가 짐작으로 다시 불렀다.
흔한 실수: 다른 스킬의 옵션(--project-root·--issue), --cred 없이 이름만 넘김, 빈 값('' — $VAR 미설정).
"""
from __future__ import annotations

import argparse
import difflib
import re

# 다른 CLI·스킬에서 넘어오는 옵션 이름 > 이 CLI 의 이름 (받는 명령에만 제안한다)
OPTION_ALIASES = {
    "--project-root": "--root", "--project": "--root", "--repo-root": "--root", "--repo": "--root",
    "--cwd": "--root", "--dir": "--root", "--workdir": "--root",
    "--credential": "--cred", "--account": "--cred",
    "--udid": "--device", "--serial": "--device",
    "--link": "--url", "--address": "--url",
    "--size": "--viewport",
    # 글자로 누르기(click 은 --selector 'text=…') · 입력값 이름 혼동 — 실측에서 --timeout 이 잘못 제안됐다
    "--text": "--selector", "--value": "--text",
}
SIMILARITY_CUTOFF = 0.6
# 위치 인자로 잘못 넘기기 쉬운 '이름' 옵션 (앞선 것이 우선)
NAME_OPTIONS = ("--cred", "--name", "--key")


def _subparsers(parser: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    action = next((a for a in parser._actions if isinstance(a, argparse._SubParsersAction)), None)
    return dict(action.choices) if action else {}


def _option_strings(parser: argparse.ArgumentParser) -> list[str]:
    return [o for a in parser._actions for o in a.option_strings if o not in ("-h", "--help")]


def _long_options(parser: argparse.ArgumentParser) -> list[str]:
    """옵션마다 대표 긴 이름 하나."""
    names = []
    for action in parser._actions:
        longs = [o for o in action.option_strings if o.startswith("--") and o != "--help"]
        names += longs[:1]
    return names


def _suggest(name: str, choices: list[str]) -> str | None:
    alias = OPTION_ALIASES.get(name)
    if alias and alias in choices:
        return alias
    close = difflib.get_close_matches(name, choices, n=1, cutoff=SIMILARITY_CUTOFF)
    return close[0] if close else None


def empty_value_options(raw: list[str]) -> list[str]:
    """값이 빈 문자열로 넘어온 옵션 (`--preset ''`, `--url=`) — 대개 $VAR 가 비어 있다."""
    empty = []
    for index, token in enumerate(raw):
        if token.startswith("--") and token.endswith("=") and "=" in token:
            empty.append(token[:-1])
        elif token == "" and index > 0 and raw[index - 1].startswith("--"):
            empty.append(raw[index - 1])
    return empty


def _example(parser: argparse.ArgumentParser) -> str:
    """동작 파서는 선언한 예시(epilog 의 '예: ...'), 없으면 usage 한 줄."""
    match = re.search(r"예:\s*(.+)", parser.epilog or "")
    if match:
        return match.group(1).strip()
    return " ".join(parser.format_usage().split())[len("usage: "):].replace("[-h] ", "")


def diagnose(parser: argparse.ArgumentParser, raw: list[str], reason: str) -> dict:
    """bad_args 에 덧붙일 필드: unknown · did_you_mean · valid_options(또는 commands/actions) · example · empty_values."""
    found: dict = {}
    target, path = parser, []
    tokens = list(raw)
    # 명령 > 동작 순으로 내려가며 대상 파서를 찾는다. 모르는 이름이면 거기서 멈추고 비슷한 이름을 준다
    while tokens and _subparsers(target):
        choices = _subparsers(target)
        head = tokens[0]
        if head.startswith("-"):
            break
        if head not in choices:
            found["unknown"] = [head]
            suggestion = difflib.get_close_matches(head, list(choices), n=1, cutoff=SIMILARITY_CUTOFF)
            if suggestion:
                found["did_you_mean"] = {head: suggestion[0]}
            found["commands" if target is parser else "actions"] = list(choices)
            break
        target = choices[head]
        path.append(head)
        tokens = tokens[1:]
    if target is not parser and "unknown" not in found:
        _diagnose_options(found, target, tokens, reason)
    if path:
        found["example"] = _example(target)
    empty = empty_value_options(raw)
    if empty:
        found["empty_values"] = empty
        found["empty_values_note"] = (f"{', '.join(empty)} 의 값이 비어 있다 — 값을 넣거나, "
                                      "$VAR 로 넘겼다면 그 환경변수가 설정됐는지 확인한다")
    return found


def _diagnose_options(found: dict, target: argparse.ArgumentParser, tokens: list[str], reason: str) -> None:
    """모르는 옵션과 남는 위치 인자를 찾는다. 옵션 목록은 이 명령(동작) 것만 싣는다."""
    known = _option_strings(target)
    valid = _long_options(target)
    unknown = [t.split("=", 1)[0] for t in tokens
               if t.startswith("--") and t.split("=", 1)[0] not in known]
    extra = re.search(r"unrecognized arguments:\s*(.+)$", reason)
    extras = extra.group(1).split() if extra else []
    # 모르는 옵션 바로 뒤 토큰은 그 옵션의 값이다 — 위치 인자로 세지 않는다 (--issue 3)
    positionals = [t for i, t in enumerate(extras)
                   if not t.startswith("-") and not (i > 0 and extras[i - 1].startswith("--"))]
    if unknown or positionals:
        found["unknown"] = unknown + positionals
    suggestions = {name: hint for name in unknown if (hint := _suggest(name, valid))}
    if suggestions:
        found["did_you_mean"] = suggestions
    name_option = next((o for o in NAME_OPTIONS if o in valid), None)
    if positionals and name_option:
        found["positional_hint"] = f"옵션 이름 없이 값만 넘긴 것 같다 — {name_option} {positionals[0]} 처럼 넘긴다"
    found["valid_options"] = valid
