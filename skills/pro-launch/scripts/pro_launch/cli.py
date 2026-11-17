"""Parser assembly and `main()` — gathers command declarations into one CLI.

No per-command knowledge here. `commands/` declares what exists; this file only gathers and runs it.
Output is always a single JSON — argument errors and unexpected exceptions also end as JSON, not tracebacks.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import os
import subprocess
import sys

from pro_launch import registry
from pro_launch.registry import Command
from pro_launch.runtime.arg_diagnosis import diagnose, empty_value_options
from pro_launch.runtime.context import ACCESS_CTX, INPUT_CTX, OUTPUT_CTX, ROOT_CTX, TARGET_CTX
from pro_launch.runtime import host_resources
from pro_launch.runtime.output import attach_known_fix, emit_shaped

# Order shown in help. Commands not listed here follow by name (registration itself is independent of this table)
HELP_ORDER = ("doctor", "detect", "devices", "device", "app", "web", "render", "http", "access", "db",
              "logs", "cred", "local", "ssh", "shrink", "mask", "redact", "recall", "learn", "tidy", "forget", "session-check",
              "kb", "journal", "harness", "get-output-path")


def load_commands() -> list[Command]:
    """Gather declarations under commands/ and return them in help order."""
    from pro_launch import commands

    found = {c.name: c for c in registry.discover_commands(commands)}
    first = [found[n] for n in HELP_ORDER if n in found]
    rest = [found[n] for n in sorted(found) if n not in HELP_ORDER]
    return first + rest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="launch_cli",
                                     description="Launch, drive and capture apps, web and servers")
    # Output shape options (#898) — actually taken out by _pop_output_options before parsing. Listed here for help
    parser.add_argument("--brief", action="store_true",
                        help="Output only the core keys: ok·code·summary·next·error·known_fix·memory·learn_hint·journal·harness, "
                             "plus the read result (lines·text·stdout·stderr·rows·json)")
    parser.add_argument("--fields", metavar="a,b,c",
                        help="Keep only these top-level keys (ok·code·summary·next·known_fix·memory·learn_hint·journal·harness are always kept)")
    sub = parser.add_subparsers(dest="command", required=True)
    for cmd in load_commands():
        p = sub.add_parser(cmd.name, help=cmd.help)
        if cmd.configure:
            cmd.configure(p)
        p.set_defaults(func=cmd.run, _tail_dest=cmd.tail_dest)
    return parser


def _split_tail(raw: list[str], commands: list[Command]) -> tuple[list[str], list[str]]:
    """Commands that use `--` (local sudo -- <command>) do not pass what follows to the parser.

    argparse REMAINDER would also swallow earlier options like --cred, so it is cut off beforehand
    and returned as `args.<tail_dest>` (#784).
    """
    if raw and "--" in raw:
        owner = next((c for c in commands if c.name == raw[0]), None)
        if owner and owner.tail_dest:
            i = raw.index("--")
            return raw[:i], raw[i + 1:]
    return raw, []


BRIEF_OPTION = "--brief"
FIELDS_OPTION = "--fields"


def _pop_output_options(raw: list[str]) -> tuple[list[str], bool, list[str] | None, str | None]:
    """Take out --brief · --fields wherever they are (before or after the subcommand) > (rest, is_brief, key list, error).

    Taken out before parsing instead of added to each subparser — covers nested actions (web shot, etc.) without touching them.
    What follows `--` (local sudo -- <command>) is someone else's command args, so it is left alone.
    """
    tail_start = raw.index("--") if "--" in raw else len(raw)
    head, rest = raw[:tail_start], raw[tail_start:]
    kept: list[str] = []
    is_brief = False
    field_names: list[str] | None = None
    index = 0
    while index < len(head):
        token = head[index]
        if token == BRIEF_OPTION:
            is_brief = True
        elif token == FIELDS_OPTION or token.startswith(FIELDS_OPTION + "="):
            if token == FIELDS_OPTION:
                index += 1
                if index >= len(head) or head[index].startswith("--"):
                    return raw, is_brief, field_names, "--fields has no key names (e.g. --fields path,url)"
                value = head[index]
            else:
                value = token.split("=", 1)[1]
            names = [name.strip() for name in value.split(",") if name.strip()]
            if not names:
                return raw, is_brief, field_names, "--fields has no key names (e.g. --fields path,url)"
            field_names = [*(field_names or []), *names]
        else:
            kept.append(token)
        index += 1
    return kept + rest, is_brief, field_names, None


def tool_timeout_payload(error: subprocess.TimeoutExpired) -> dict:
    """Hung external tool > tool_timeout with the tool, its timeout and host load (memory pressure is the usual cause)"""
    command = error.cmd if isinstance(error.cmd, (list, tuple)) else str(error.cmd).split()
    tool = os.path.basename(str(command[0])) if command else "tool"
    try:
        memory_pressure = host_resources.memory_summary()["pressure"]
    except Exception:   # noqa: BLE001 — load info is auxiliary
        memory_pressure = None
    return {"ok": False, "code": "tool_timeout", "tool": tool,
            "command": " ".join(str(part) for part in command[1:6]),
            "timeout_seconds": error.timeout, "memory_pressure": memory_pressure,
            "error": f"{tool} did not answer within {error.timeout:g} s",
            "next": "Check host load with `doctor --resources`. If memory pressure is high, ask the user before closing other "
                    "simulators or emulators, then call the same command again (do not switch to raw adb or simctl)"}


def main(argv: list[str] | None = None) -> int:
    from common.stable_entry import refresh_and_check
    refresh_and_check(sys.argv[0])   # refresh the fixed entry point like other skill CLIs (never blocks the command on failure)
    parser = build_parser()
    raw = list(sys.argv[1:] if argv is None else argv)
    raw, is_brief, field_names, option_error = _pop_output_options(raw)
    # When main is called several times in one process (tests), write fresh each time so the previous call's shape does not leak
    OUTPUT_CTX.clear()
    OUTPUT_CTX.update(is_brief=is_brief, field_names=field_names)
    if option_error:
        return emit_shaped({"ok": False, "code": "bad_args", "error": f"Invalid arguments: {option_error}",
                            "next": "launch_cli.py <subcommand> --help"})
    raw, tail = _split_tail(raw, load_commands())
    # Empty values ('' — unset $VAR) pass the parser but become odd errors in the action. Attach the offending option to the failure response (#886)
    INPUT_CTX.clear()
    INPUT_CTX.update(raw=raw, empty_values=empty_value_options(raw))
    err = io.StringIO()
    try:
        # Put the cause text argparse writes to stderr into error (the agent reads only JSON)
        with contextlib.redirect_stderr(err):
            args = parser.parse_args(raw)
        if getattr(args, "_tail_dest", None):
            setattr(args, args._tail_dest, tail)
        if positional_error := registry.apply_positional_value(args):
            return emit_shaped({"ok": False, "code": "bad_args", "error": f"Invalid arguments: {positional_error}",
                                "summary": f"Argument error: {positional_error}",
                                "next": "launch_cli.py <subcommand> --help"})
    except SystemExit as e:
        if e.code in (0, None):
            raise
        # argparse usage is not echoed: printed before the JSON it hid the did_you_mean hint under `| head` (#1224)
        reason = err.getvalue().strip().splitlines()[-1] if err.getvalue().strip() else ""
        payload = {"ok": False, "code": "bad_args",
                   "error": f"Invalid arguments: {reason}",
                   "next": "launch_cli.py <subcommand> --help"}
        # What was wrong · similar names · this command's options · example (#886)
        diagnosis = diagnose(parser, raw, reason)
        payload.update(diagnosis)
        payload["summary"] = ("Argument error: unknown " + " ".join(diagnosis["unknown"])
                              if diagnosis.get("unknown") else payload["error"])
        if diagnosis.get("accepted_by"):
            payload["next"] = diagnosis["accepted_by_note"]
        elif diagnosis.get("did_you_mean"):
            fixes = ", ".join(f"{wrong} > {right}" for wrong, right in diagnosis["did_you_mean"].items())
            payload["next"] = f"Fix the name and call again ({fixes})"
        elif diagnosis.get("example"):
            payload["next"] = f"e.g. {diagnosis['example']}"
        if registry.LOAD_ERRORS:
            # The subcommand may be missing because its module is broken — report the cause
            payload["load_errors"] = dict(registry.LOAD_ERRORS)
        attach_known_fix(payload)
        return emit_shaped(payload)
    # When main is called several times in one process (tests), keep the previous call's markers from leaking
    ROOT_CTX.clear()
    ACCESS_CTX.clear()
    TARGET_CTX.clear()
    try:
        return args.func(args)
    except subprocess.TimeoutExpired as e:   # a device tool (adb, simctl, ...) hung: not an input error (#1223)
        payload = tool_timeout_payload(e)
        attach_known_fix(payload)
        return emit_shaped(payload)
    except Exception as e:   # so unexpected input never ends in a traceback — the agent reads only JSON (#705)
        payload = {"ok": False, "code": "handler_error", "error": f"{type(e).__name__}: {e}",
                   "next": "Check the input (paths, values) and call again"}
        attach_known_fix(payload)
        return emit_shaped(payload)
