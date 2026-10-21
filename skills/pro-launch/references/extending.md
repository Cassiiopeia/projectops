# Extending — how to add a new control target or platform

> When to read: before you change code to add a new platform (app backend), a new web action, or a new subcommand to pro-launch.

**The code map is `scripts/pro_launch/ARCHITECTURE.md`. It says where everything lives and which file to change for each kind of work.**
This document only covers "how to add something new" on top of that.

First read the **"Python behavior script standard"** section of the repo `CLAUDE.md` and `skills/references/mcp-subcommand-rules.md`.
The key points:

- **Standard library first.** If an external package is truly needed, put install instructions in the result (Playwright goes into its own venv).
- **Output is always a single JSON object.** There is no plain-text mode.
- **The agent interprets, the script executes.** The script does not guess the project structure.
- Take arguments as argparse named flags or environment variables. Do not chain several optional positional arguments (#622).

## Output JSON contract

| Field | When | Meaning |
|---|---|---|
| `ok` | Always | Whether it succeeded |
| `code` | Always | `ok` or a snake_case failure name. The agent branches on this value — **on the code, not the message** |
| `summary` | Recommended on success | One-line summary |
| `error` · `hint` | On failure | What went wrong · how to fix it |
| `next` | Always, when possible | The one command the agent should call next (`null` when done) |
| `candidates` · `locale` | When an element was not found (`not_found`) | Values actually on screen · screen language — keeps the agent from repeating guesses |
| `shot` · `screen_changed` | When `--shot` was given | Path of the capture · whether the screen changed between before and after the action (`false` means no reaction) |

- Report a new failure with a **new code**. Do not change the meaning of an existing code — calling skills (`pro-agent-test` and others) rely on it.
- Never put secret values (passwords, tokens) in results or logs. If one might slip in, mask it as `***`.

## New app platform — one backend class + registry entry + tests

App actions (`app tap` · `swipe` · `tree`, #826) are handled by the **platform backends** in `scripts/app_input.py`. `pro_launch/commands/app/` only calls this module;
all platform differences live here. There are two today: `AndroidBackend` (adb + uiautomator, built into the device, nothing to install) and
`IOSMaestroBackend` (Maestro — simctl has no tap or screen-structure commands).

```python
BACKENDS = {
    "android": lambda app_id=None: AndroidBackend(),
    "ios": lambda app_id=None: IOSMaestroBackend(app_id=app_id),
}
# get_backend(platform, app_id) builds from this table. Keys must match the platform names returned by pick_device in runtime/devices.py
```

Subclass `Backend` and fill it in. Every action method returns `(success, human-readable reason)`.

| Member | Returns | Notes |
|---|---|---|
| `name` | Platform name | Same as the registry key |
| `available()` | `bool` | Is the tool installed? If not, `install_hint` (an install command string) goes into `next` with the code `{name}_tool_missing` — e.g. `ios_tool_missing` |
| `selects_itself` | `bool` | `True` means the backend finds and taps the element itself (`tap_selector`, the Maestro way). `False` means the element is found with `nodes()` and tapped with `tap_xy` |
| `locale(dev)` | Screen language or `None` | Included in `not_found` and `tree` responses |
| `nodes(dev)` | `list[dict]` or `None` | Each dict has `text`·`id`·`desc`·`clickable`·`bounds`·`center` (build it with `make_node`). `None` if the screen structure cannot be read |
| `tap_xy(dev, x, y)` | `(bool, str)` | Tap at pixel coordinates — internal, used to tap a `center` from `nodes` |
| `tap_ratio(dev, rx, ry)` | `(bool, str)` | Tap at 0–1 ratio coordinates (`--at`) |
| `tap_selector(dev, field, value)` | `(bool, str)` | `selects_itself` backends only. `field` is `text` · `id` · `desc` |
| `swipe_ratio(dev, start, end, ms)` | `(bool, str)` | Two points in ratio coordinates and a duration (ms). `SWIPE_DIRS` turns `--dir` into two points |
| `grab(dev)` | PNG `bytes` or `None` | Used by `--shot` to pick "the screen that settled after the change" and to set `screen_changed` |

Steps:

1. Create a class in `scripts/app_input.py` that subclasses `Backend`. Call external tools with `subprocess`.
   Move **anything that can be checked without a device** (such as screen-dump parsing) into module-level pure functions (`ui_nodes` · `maestro_nodes` · `match_nodes` · `parse_ratio` are examples).
2. Register it in `BACKENDS`. `pro_launch/commands/app/` only picks a backend and calls it, so it **should not need changes.**
   If it does, the interface is leaking; move that part into the backend.
3. Add tests (below). Registering alone makes `test_every_registered_backend_implements_the_contract` in `tests/test_launch_cli.py`
   check that the new backend has every contract member. Separately, add unit tests for that backend's parsing and failure paths.
4. Write down how to connect and the pitfalls in `references/app.md`. What worked on this Mac belongs to `learn`, not the docs.

**Forbidden**: implementations that tap coordinates with the host mouse (`cliclick` · AppleScript System Events · CGEvent). They steal the user's cursor,
and you cannot tell what was tapped. Only use methods that tap **inside the device**: accessibility tree, the device's built-in input, or E2E tools.

## New web action

One action is **one module** in `scripts/pro_launch/commands/web/actions/`. Do not change any other file —
`web` scans that folder to build its choices, options, and dispatch.

```python
# commands/web/actions/scroll.py
from pro_launch.commands.web.element import locate_target
from pro_launch.registry import Action

def configure(p) -> None:                       # options only this action uses (optional)
    p.add_argument("--pixels", type=int, default=600, help="distance to scroll (px)")

def execute(page, args, state) -> dict:          # needs="page" means (page, args, state) -> result dict
    element, info, failure = locate_target(page, args, state, "scroll", should_guard_mutating=False)
    if failure:
        return failure
    element.evaluate("(e, n) => e.scrollBy(0, n)", args.pixels)
    return {"action": "scroll", "target": info, "summary": "scrolled", "next": "web text"}

# options: shared options it uses (names from commands/web/options.py). Shared options not listed here are rejected with bad_args
ACTION = Action(name="scroll", run=execute, configure=configure, options=("selector", "ref"),
                help="scroll inside an element", example="web scroll --ref 3 --pixels 800")
```

`needs` decides what the dispatcher prepares for you.

| needs | Shape of `run` | When |
|---|---|---|
| `page` (default) | `(page, args, state) -> dict` | Connects and drives the screen. The dispatcher handles connecting, last-used time, exception conversion (secret masking), and disconnecting |
| `nothing` | `(args) -> int` | Reads neither state nor browser (`setup`) |
| `launch` | `(args, root, state_file) -> int` | Starts a new browser (`open`) |
| `state_offline` | `(args, state, state_file) -> int` | Touches only the state file. No browser needed (`viewport` · `route`) |
| `state_online` | `(args, state, state_file) -> int` | Needs the running browser's info but does not connect (`close`) |

Steps:

1. Create the module in the shape above. Each action has its own subparser, so its option names may overlap with other actions. Options used by several actions
   (`--url` · `--selector` · `--ref` · `--text` · `--timeout` …) live in `commands/web/options.py`; list only the ones you use in `options=`
   (#896 — `web <action> --help` shows only those plus `help` · `example`). `app` actions do not list `options` (they accept all).
2. **Anything that lives only while connected goes into the state file and is re-applied on every connect.** `web` connects over CDP (`connect_over_cdp`) on every call
   and then disconnects, so settings like console hooks, stealth, viewport, and response overrides disappear when the connection drops (#625, measured).
   Make new settings re-install in `web_connect` in `commands/web/session.py`. Do not start the browser with Playwright `launch()` — it dies with the driver.
3. If you add an action that changes things, check that the safety contract in `references/web.md` (local only · ask for anything else) applies.
   In a read-only session (`state["readonly"]`), filter with `is_mutating_target()` in `commands/web/targets.py` and return `mutating_blocked`.
4. **Return results the agent can judge (#825).** An action that changes the screen returns the `url` · `title` before and after, plus what it targeted.
   A failure returns a `code` (not a message) and the next command to call (`next`). If it only says "succeeded", the agent taps the wrong thing and moves on
   (measured on Play Console). Let the target be passed as a `ref` (`data-pops-ref`) from `web find` instead of a guessed selector.
5. Put unit tests in `tests/`. `tests/test_launch_architecture.py` checks the action's shape (`needs` and argument count) automatically.

## New app action

One module in `scripts/pro_launch/commands/app/actions/`. It is `ACTION = Action(name=..., run=execute, configure=...)`, and
`execute(args) -> int` emits its result directly with `out(...)`. It does not need to know the platform — `backend_for(args)` in
`commands/app/gestures.py` picks the backend.

## New subcommand

Put **one module** in `scripts/pro_launch/commands/`. The parser, help, and dispatch are built from the declaration, so do not change any other file.

```python
# commands/ping.py
from pro_launch.registry import Command
from pro_launch.runtime.output import out

def configure(p) -> None:
    p.add_argument("--host", required=True)

def cmd_ping(args) -> int:
    return out({"ok": True, "code": "ok", "summary": f"{args.host} checked", "next": None})

COMMANDS = [Command(name="ping", help="check that a host responds", run=cmd_ping, configure=configure)]
```

- Always emit results with `runtime.output.out()` — migration notices, root warnings, access-method scores, and memory attachments are added there for every command.
- Do not import other command modules. Anything used by two or more goes down into `runtime/` (`test_launch_architecture.py` enforces this).
- Behavior that branches on `sys.platform` lives only in `runtime/procs.py`.
- A new name **must appear as a call example in SKILL.md** (`scripts/tests/test_cli_signatures_doc_sync.py` reads the `Command(name=...)` declarations and enforces this).
  Add one line to the router table and put the details in references.
- Use only the path returned by `get-output-path` for outputs. Do not build paths yourself (#623).
- The order shown in `--help` is `HELP_ORDER` in `pro_launch/cli.py`. A command missing from it is still registered and is appended in name order.

## Test rules

| What | Where · how |
|---|---|
| Unit tests — **required** | `skills/pro-launch/tests/` (app backends in `test_launch_cli.py`, structure rules in `test_launch_architecture.py`). They run without a device or browser. Replace external commands with fake executables (scripts placed first on PATH) or monkeypatch, and check `nodes` parsing, ratio math, failure codes, and JSON fields |
| Needs a real device or browser | Mark with `@pytest.mark.local_only`. It runs locally when the tool is present and is skipped in CI (`CI=true`) |
| Pure value checks | Do not mark `local_only`. The test creates the "tool missing" state itself so it runs anywhere (#591) |

```bash
python3 -m pytest skills/pro-launch/tests -q
python3 -m pytest scripts/tests -q        # docs · subcommand consistency
```

Test code is not copied to users (`SKIP_IN_COPY` in `src/core/ide/skills-copy.js`). Before adding a helper file
to a skill, first ask: "Does someone using this skill need this?"
