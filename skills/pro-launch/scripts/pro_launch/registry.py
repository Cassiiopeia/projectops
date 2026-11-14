"""Declaration and auto-discovery of commands and actions.

A new subcommand is just one module in `commands/` that exports `COMMANDS`.
A new `web`·`app` action is just one module in that command's `actions/` that exports `ACTION`.
No other file changes — parser, help and dispatch are built from these declarations.

If one module fails to import, other commands must still run. Failures are kept in `LOAD_ERRORS`
and reported only when that command is called.
"""
from __future__ import annotations

import argparse
import importlib
import pkgutil
from dataclasses import dataclass
from typing import Callable

# What the action needs. The dispatcher decides preparation from this value.
#   nothing        run(args)                      — reads neither state nor browser (web setup)
#   launch         run(args, root, state_file)    — launches a new browser (web open)
#   state_offline  run(args, state, state_file)   — touches only the state file. No browser needed
#   state_online   run(args, state, state_file)   — needs info on the running browser but does not connect
#   page           run(page, args, state) -> dict — attaches and drives one page. Returns a result dict
NEEDS = ("nothing", "launch", "state_offline", "state_online", "page")
# How the action uses the device (#953). The dispatcher checks ownership and records with this value
#   mutate  changes device or app state — refused without --yes if another session owns it
#   read    read-only — only a warning if another session owns it
#   none    does not use the device, or the action judges it itself
DEVICE_USES = ("mutate", "read", "none")


@dataclass(frozen=True)
class Command:
    """One subcommand. `name` is what the CLI calls it."""

    name: str
    help: str
    run: Callable[[argparse.Namespace], int]
    configure: Callable[[argparse.ArgumentParser], None] | None = None
    # Arguments after `--` are not parsed but returned in the argument of this name (e.g. local sudo -- <command>)
    tail_dest: str | None = None


@dataclass(frozen=True)
class Action:
    """One action inside a command like `web`·`app`. Its own options are added via `configure`."""

    name: str
    run: Callable
    needs: str = "page"
    configure: Callable[[argparse.ArgumentParser], None] | None = None
    # One-line description and one example for `<command> <action> --help`
    help: str = ""
    example: str = ""
    # Shared option names this action uses. None accepts all shared options (commands not split per action — app)
    options: tuple[str, ...] | None = None
    # Actions of device-using commands (app) must declare it (DEVICE_USES) — the test catches omissions
    device_use: str | None = None
    # dest of the option that can also be given as a bare value (e.g. "url" > `web goto http://…`). One per action (#622 · #1149)
    positional: str | None = None

    def __post_init__(self) -> None:
        if self.needs not in NEEDS:
            raise ValueError(f"needs must be one of {NEEDS}: {self.needs!r}")
        if self.device_use is not None and self.device_use not in DEVICE_USES:
            raise ValueError(f"device_use must be one of {DEVICE_USES}: {self.device_use!r}")
        if self.options is not None and not isinstance(self.options, tuple):
            raise ValueError(f"options must be a tuple: {self.options!r}")


# Field holding the positional value · field naming the option to move it to (apply_positional_value)
POSITIONAL_VALUE_DEST = "positional_value"
POSITIONAL_TARGET_DEST = "positional_target"

# module name → error. One broken module does not stop the other commands
LOAD_ERRORS: dict[str, str] = {}


def _modules(package):
    for info in pkgutil.iter_modules(package.__path__):
        if info.name.startswith("_"):
            continue
        full = f"{package.__name__}.{info.name}"
        try:
            yield info.name, importlib.import_module(full)
        except Exception as e:   # noqa: BLE001 — one module must not block everything
            LOAD_ERRORS[info.name] = f"{type(e).__name__}: {e}"


def discover_commands(package) -> list[Command]:
    """Collect `COMMANDS` exported by modules under `package`. Duplicate names are an error."""
    found: dict[str, Command] = {}
    for mod_name, mod in _modules(package):
        for cmd in getattr(mod, "COMMANDS", []):
            if cmd.name in found:
                raise ValueError(f"Duplicate subcommand name: {cmd.name} ({mod_name})")
            found[cmd.name] = cmd
    return list(found.values())


def discover_actions(package) -> dict[str, Action]:
    """Collect `ACTION` exported by modules under `package` (actions folder), sorted by name."""
    found: dict[str, Action] = {}
    for mod_name, mod in _modules(package):
        act = getattr(mod, "ACTION", None)
        if act is None:
            continue
        if act.name in found:
            raise ValueError(f"Duplicate action name: {act.name} ({mod_name})")
        found[act.name] = act
    return dict(sorted(found.items()))


# ── Per-action parsers (#896) ────────────────────────────────────────────────────
#
# Putting every shared option on one parser shows 30 in `web type --help` and silently accepts options the action does not use.
# Each action gets a subparser with only the shared options it declares + its own options.


class ActionParser(argparse.ArgumentParser):
    """Parser for one action. Options the action does not accept are rejected (listing usable options), not silently passed."""

    def parse_known_args(self, args=None, namespace=None):
        namespace, extras = super().parse_known_args(args, namespace)
        unsupported = [a.split("=", 1)[0] for a in extras if a.startswith("-") and len(a) > 1]
        if unsupported:
            # cli.main puts the last stderr line into the bad_args error — keep it to one line
            # prog (e.g. launch_cli web type) is prefixed, so the action name is not repeated
            self.error(f"This action does not take {' '.join(unsupported)} (unsupported option). "
                       f"Available options: {' '.join(self.option_names())}")
        return namespace, extras

    def option_names(self) -> list[str]:
        """Long option names this parser accepts (excluding --help)."""
        names = []
        for act in self._actions:
            longs = [o for o in act.option_strings if o.startswith("--") and o != "--help"]
            names += longs[:1]
        return names


def shared_option_defaults(shared: dict[str, Callable[[argparse.ArgumentParser], None]]) -> dict:
    """(dest → default) for every shared option. Undeclared actions still need the attribute so the dispatcher reads without getattr.

    Some options (--timeout) use the same flag with different defaults per action, so each is read separately; on overlap the earlier table entry wins.
    """
    defaults: dict = {}
    for add in shared.values():
        scratch = argparse.ArgumentParser(add_help=False)
        add(scratch)
        for dest, value in vars(scratch.parse_args([])).items():
            defaults.setdefault(dest, value)
    return defaults


def add_action_parsers(parser: argparse.ArgumentParser, actions: dict[str, Action],
                       shared: dict[str, Callable[[argparse.ArgumentParser], None]],
                       always: tuple[str, ...] = ()) -> None:
    """Add a subparser per action: always-on shared options + declared shared options + the action's configure.

    Undeclared shared options are not accepted on the command line; only their defaults are filled.
    """
    defaults = shared_option_defaults(shared)
    sub = parser.add_subparsers(dest="action", required=True, metavar="<action>",
                                parser_class=ActionParser)
    for name, action in actions.items():
        chosen = tuple(shared) if action.options is None else always + action.options
        unknown = [o for o in chosen if o not in shared]
        if unknown:
            raise ValueError(f"{name}: unknown shared option {unknown} (available: {sorted(shared)})")
        p = sub.add_parser(name, help=action.help or None, description=action.help or None,
                           epilog=f"e.g. {action.example}" if action.example else None,
                           formatter_class=argparse.RawDescriptionHelpFormatter)
        p.set_defaults(**defaults)
        for option in dict.fromkeys(chosen):
            shared[option](p)
        if action.configure:
            action.configure(p)
        if action.positional:
            p.add_argument(POSITIONAL_VALUE_DEST, nargs="?", default=None, metavar=action.positional.upper(),
                           help=f"same as --{action.positional.replace('_', '-')}")
            p.set_defaults(**{POSITIONAL_TARGET_DEST: action.positional})


def apply_positional_value(args: argparse.Namespace) -> str | None:
    """Positional value > moved into the declared option. Error message if both differ, otherwise None"""
    value = getattr(args, POSITIONAL_VALUE_DEST, None)
    target = getattr(args, POSITIONAL_TARGET_DEST, None)
    if value is None or not target:
        return None
    current = getattr(args, target, None)
    if current and current != value:
        return f"got both {value} and --{target.replace('_', '-')} {current}; pass one"
    setattr(args, target, value)
    return None


def action_usage_lines(parser: argparse.ArgumentParser) -> list[str]:
    """Per-action option summary for `<command> --help` — one line per action."""
    sub = next((a for a in parser._actions if isinstance(a, argparse._SubParsersAction)), None)
    if sub is None:
        return []
    lines = []
    for name, p in sub.choices.items():
        options = p.option_names() if isinstance(p, ActionParser) else []
        lines.append(f"  {name:<9} {' '.join(options)}")
    return lines
