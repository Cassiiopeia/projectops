"""Argument error diagnosis: unknown option·subcommand > similar names > that command's options > one example line (#886).

bad_args is the most frequent failure, yet it only said "see usage", so the agent retried by guessing.
Common mistakes: options from other skills (--project-root·--issue), passing a name without --cred, empty values ('' — unset $VAR).
"""
from __future__ import annotations

import argparse
import difflib
import re

# Option names coming from other CLIs·skills > this CLI's name (suggested only for commands that accept it)
# Action names agents think of first > the real name (spelled too differently for difflib, #1149)
ACTION_ALIASES = {
    "screenshot": "shot", "capture": "shot", "snap": "shot",
    "navigate": "goto", "visit": "goto", "go": "goto",
}
OPTION_ALIASES = {
    "--project-root": "--root", "--project": "--root", "--repo-root": "--root", "--repo": "--root",
    "--cwd": "--root", "--dir": "--root", "--workdir": "--root",
    "--credential": "--cred", "--account": "--cred",
    "--udid": "--device", "--serial": "--device",
    "--link": "--url", "--address": "--url",
    "--size": "--viewport",
    # Pressing by text (click uses --selector 'text=…') · input value name mix-ups — --timeout was wrongly suggested in practice
    "--text": "--selector", "--value": "--text",
}
SIMILARITY_CUTOFF = 0.6
# 'name' options easily passed as positional args by mistake (earlier ones win)
NAME_OPTIONS = ("--cred", "--name", "--key")


def _subparsers(parser: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    action = next((a for a in parser._actions if isinstance(a, argparse._SubParsersAction)), None)
    return dict(action.choices) if action else {}


def _option_strings(parser: argparse.ArgumentParser) -> list[str]:
    return [o for a in parser._actions for o in a.option_strings if o not in ("-h", "--help")]


def _long_options(parser: argparse.ArgumentParser) -> list[str]:
    """One representative long name per option."""
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
    """Options passed as empty strings (`--preset ''`, `--url=`) — usually an empty $VAR."""
    empty = []
    for index, token in enumerate(raw):
        if token.startswith("--") and token.endswith("=") and "=" in token:
            empty.append(token[:-1])
        elif token == "" and index > 0 and raw[index - 1].startswith("--"):
            empty.append(raw[index - 1])
    return empty


def _example(parser: argparse.ArgumentParser) -> str:
    """For action parsers, the declared example (the 'e.g. ...' in the epilog), otherwise the one-line usage."""
    match = re.search(r"e\.g\.\s*(.+)", parser.epilog or "")
    if match:
        return match.group(1).strip()
    return " ".join(parser.format_usage().split())[len("usage: "):].replace("[-h] ", "")


def diagnose(parser: argparse.ArgumentParser, raw: list[str], reason: str) -> dict:
    """Fields added to bad_args: unknown · did_you_mean · valid_options (or commands/actions) · example · empty_values."""
    found: dict = {}
    target, parent, path = parser, None, []
    tokens = list(raw)
    # Walk down command > action to find the target parser. On an unknown name, stop there and offer similar names
    while tokens and _subparsers(target):
        choices = _subparsers(target)
        head = tokens[0]
        if head.startswith("-"):
            break
        if head not in choices:
            found["unknown"] = [head]
            suggestion = ([ACTION_ALIASES[head]] if ACTION_ALIASES.get(head) in choices
                          else difflib.get_close_matches(head, list(choices), n=1, cutoff=SIMILARITY_CUTOFF))
            if suggestion:
                found["did_you_mean"] = {head: suggestion[0]}
            found["commands" if target is parser else "actions"] = list(choices)
            break
        parent, target = target, choices[head]
        path.append(head)
        tokens = tokens[1:]
    if target is not parser and "unknown" not in found:
        _diagnose_options(found, target, tokens, reason, parent)
    if path:
        found["example"] = _example(target)
    empty = empty_value_options(raw)
    if empty:
        found["empty_values"] = empty
        found["empty_values_note"] = (f"{', '.join(empty)} has an empty value — pass a value, or "
                                      "if you passed $VAR, check that the environment variable is set")
    return found


def _actions_taking(parent: argparse.ArgumentParser | None, option: str) -> list[str]:
    """Sibling actions that do accept this option (web download --frame > click, find, ...)."""
    if parent is None:
        return []
    return [name for name, sibling in _subparsers(parent).items() if option in _option_strings(sibling)]


def _diagnose_options(found: dict, target: argparse.ArgumentParser, tokens: list[str], reason: str,
                      parent: argparse.ArgumentParser | None = None) -> None:
    """Find unknown options and leftover positional args. The option list covers only this command (action)."""
    known = _option_strings(target)
    valid = _long_options(target)
    unknown = [t.split("=", 1)[0] for t in tokens
               if t.startswith("--") and t.split("=", 1)[0] not in known]
    extra = re.search(r"unrecognized arguments:\s*(.+)$", reason)
    extras = extra.group(1).split() if extra else []
    # The token right after an unknown option is its value — not counted as a positional arg (--issue 3)
    positionals = [t for i, t in enumerate(extras)
                   if not t.startswith("-") and not (i > 0 and extras[i - 1].startswith("--"))]
    if unknown or positionals:
        found["unknown"] = unknown + positionals
    # A real option of other actions is not a typo — say which actions take it instead of a look-alike name
    taken_elsewhere = {name: actions for name in unknown if (actions := _actions_taking(parent, name))}
    if taken_elsewhere:
        found["accepted_by"] = taken_elsewhere
        found["accepted_by_note"] = ("This action does not take " + ", ".join(taken_elsewhere) + "; the actions in "
                                     "accepted_by do. Use one of them, or reach the same result another way")
    suggestions = {name: hint for name in unknown if name not in taken_elsewhere and (hint := _suggest(name, valid))}
    if suggestions:
        found["did_you_mean"] = suggestions
    name_option = next((o for o in NAME_OPTIONS if o in valid), None)
    if positionals and name_option:
        found["positional_hint"] = f"Looks like a value was passed without its option name — pass it as {name_option} {positionals[0]}"
    found["valid_options"] = valid
