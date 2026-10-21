# MCP-style subcommand design standard

When you add a new subcommand that deals with an external system (GitHub API, SSH, and so on) to a skill's `<scope>_cli.py`, **you must follow this standard.**
It is the concrete implementation reference for the "Python behavior script standard" in CLAUDE.md.

> **Model examples**: the `actions` and `deploy-status` subcommands (`skills/pro-changelog-deploy/scripts/changelog_cli.py`). Read these two before building a new command and give it the same shape.

## Core principle

The agent **passes exactly the right arguments and decides the next action from the returned JSON**. So a subcommand
① has **a clear input contract**, ② **always outputs JSON**, and ③ carries **a next-action hint (`next`)**.
Then the agent has no reason to write ad-hoc Python in `/tmp` — ad-hoc Python wastes tokens, breaks Windows compatibility, and causes heredoc escaping bugs.

---

## 1. Input contract — the agent interprets, the .py executes

- A subcommand takes **only clear arguments**. It **does not interpret** things such as parsing URLs or tracing a PR to a run. The agent interprets the user's input (URL / PR number / branch / empty input) and passes the exact subcommand and arguments.
- When a group grows, bundle it as **group + sub-subcommand**, like `actions show-run` / `secrets set` (do not list everything flat at the top level).
- Define arguments with argparse (`JSONArgumentParser`, §8). **Do not line up several optional positional arguments** (#622) — argparse fills from the left, so if each subcommand's different value (`run_id`/`job_id`/`pr_number`/`branch`) gets its own slot, everything lands in the first slot. Keep **one** positional argument (`arg`) and let the subcommand interpret it (`actions` in `changelog_cli.py`).

---

## 2. Output is always JSON — via `emit`

- On every path, write JSON to stdout with `common.emit.emit(payload)` (no plain-text mode, and no `--json` option). `emit` fills in defaults for `ok`/`code`/`summary`/`next`.
- Both success and failure are JSON. **Do not throw an error to stderr and exit 1** (the agent cannot parse that).

### Standard return schema

| Field | Required | Meaning |
|------|------|------|
| `ok` | ✅ | Success or not (true/false) |
| `error` | On failure | Error message for people and agents to read |
| `code` | ✅ (emit fills it) | Classification code (`ok`, `missing_pat`, `github_api_404`, and so on) |
| (data fields) | ✅ | The actual result (`issues`, `repos`, `pr`, and so on — per command) |
| `verdict` | Status-judging commands | The situation in one word (`merged`, `waiting`, `no_pr`, and so on) |
| `summary` | Recommended | One-line natural-language summary |
| `next` | ✅ | Hint for the next subcommand the agent should call (`null` if none) |

### Data in the helper (gh_client), judgment in the command layer

`gh_client.py` functions do **pure API lookups** only (return raw dicts, no judgment). The `cmd_*` functions in `<scope>_cli.py`
handle **verdict judgment + JSON assembly + the next hint**. So helpers are tested on their own, and the judgment logic is verified separately.

```python
# gh_client.py — lookup only
def get_thing(owner, repo, id, pat) -> dict:
    data = _request("GET", f"{_API_BASE}/...", None, pat)
    return {"id": data["id"], "state": data["state"], ...}  # raw extraction

# <scope>_cli.py — judgment + assembly
def cmd_thing(args):
    ...
    thing = get_thing(args.owner, args.repo, args.id, pat)
    verdict = "ready" if thing["state"] == "open" else "closed"
    return emit({"ok": True, "thing": thing, "verdict": verdict,
                 "summary": "...", "next": f"thing-detail {args.owner} {args.repo} {args.id}"})
```

---

## 3. Reuse `get_github_pat` for the PAT

```python
from common.config import get_github_pat

pat = get_github_pat(args.owner, args.repo)
if not pat:
    return emit({"ok": False, "code": "missing_pat", "error": "PAT 없음"})
```

It loads automatically from the `GITHUB_PAT` environment variable, then `config.json` (per-repo `pat` → `global_pat`). Do not open the config file directly inside a subcommand.

---

## 4. Catch GitHubAPIError and turn it into JSON

```python
try:
    ...
except GitHubAPIError as e:
    return emit({"ok": False, "error": str(e), "code": f"github_api_{e.status_code}"})
```

For non-fatal partial failures (for example a failed workflow run lookup), **set that field to `null` and keep going**. See how `deploy-status` handles `workflow=null`.

---

## 5. Standard library first; otherwise an external package with corporate-network handling

- Where possible, solve it with `urllib`/`json` only (works on mac, Windows, and closed networks without `pip install`).
- For work the standard library cannot do (for example Secret encryption with PyNaCl), use an external package, but **if the `import` fails, try `pip install`, and if that fails, give manual install instructions**.
- Endpoints that redirect (job logs and so on) go through the `_StripAuthRedirect` handler in `gh_client.py` (prevents Azure 403).

---

## 6. Registration + tests

1. Register the command the way that CLI already does.
   - Single-file CLI: `sub.add_parser(...)` + `set_defaults(func=cmd_xxx)` in `build_parser()` (some old CLIs use a `_COMMANDS` dict).
   - CLI split into a package (`pro_github/` in `pro-github`, `pro_launch/` in `pro-launch`, and so on): put the handler and a `Command(name=..., ...)` declaration in `commands/<topic>.py`; the entry file's `build_parser()` only collects and assembles the declarations. You do not have to write every subcommand in one `build_parser()` body.
   - In a package CLI, if tests mock attributes of the entry file (`get_github_pat`, gh_client functions), handlers must look those names up on the entry module at call time (`pro_github.registry.Dependencies`).
2. Add unit tests for the verdict/judgment logic in `scripts/tests/` (mock the gh_client functions, call in-process).
3. Add urllib-mocked unit tests for new `gh_client.py` helpers.

```python
def _call_cmd(mock_data, argv, capsys):
    import <scope>_cli
    with patch.object(<scope>_cli, "get_github_pat", return_value="ghp_fake"), \
         patch.object(<scope>_cli, "get_thing", return_value=mock_data):
        <scope>_cli.run_cli(<scope>_cli.build_parser(), argv)
    return _json.loads(capsys.readouterr().out.strip())
```
---

## 7. Rules for writing SKILL.md

- SKILL.md describes **only how to call** (subcommands, arguments, environment variables + routing rules of the form "this input → this subcommand"). Calls take the form `{PYTHON} {SCRIPTS}/<scope>_cli.py`, found with `common-rules.md` §Standard call pattern.
- Do not inline long Python heredocs in SKILL.md. A `$PYTHON - <<'EOF'` block in SKILL.md violates the standard — move it into a subcommand.
- Spell out the agent's action per `verdict` in a table (see the verdict table for `deploy-status`).
- **Every subcommand defined in the CLI must have a call example in that skill's SKILL.md (or a document it explicitly references).** Without an example, the agent guesses the signature and fails (#329). If you cannot give an example, remove it from the CLI surface or move it into an internal function.
- A call example contains ① a `bash` line with the exact argument order, ② one line of expected JSON output, and ③ one line on how to use the result.
- `scripts/tests/test_cli_signatures_doc_sync.py` enforces this matching.

---

## 8. argparse failures must be JSON too — `JSONArgumentParser` is mandatory

By default, argparse prints text to stderr and raises `SystemExit(2)` on argument errors. The agent parses only stdout JSON, so it cannot self-correct from that.
Every `_cli.py` uses `JSONArgumentParser` + `run_cli` from `scripts/common/cli_parser.py`.

```python
from common.cli_parser import JSONArgumentParser, run_cli

def build_parser() -> JSONArgumentParser:
    parser = JSONArgumentParser(prog="scope_cli", description="...")
    sub = parser.add_subparsers(dest="command", required=True)
    # ... add_parser calls ...
    return parser

def main() -> int:
    return run_cli(build_parser())
```

`run_cli` turns argparse errors into the JSON below on stdout.

```json
{
  "ok": false,
  "code": "bad_args",
  "error": "unrecognized arguments: extra1 extra2",
  "hint": "scope_cli <subcommand> — available: ...",
  "available_subcommands": ["...", "..."],
  "summary": null,
  "next": null
}
```

When the agent sees `code == "bad_args"`, it picks the right subcommand from `available_subcommands` and calls again.
Leave `--help`/`-h` with argparse's default behavior (help text for people running it directly).

---

## Checklist (when adding a new subcommand)

- [ ] Is the input contract clear? (one positional argument)
- [ ] Does every path output JSON through `emit`? (no stderr + exit 1)
- [ ] Does it include the `ok`/`next`/`summary` fields?
- [ ] Is data lookup in common.gh_client and judgment in `<scope>_cli`?
- [ ] Does it reuse `get_github_pat` and convert `GitHubAPIError` to JSON?
- [ ] Is it registered in `build_parser()` (for a package CLI, a `Command` declaration in `commands/<topic>.py`) with tests added?
- [ ] Does SKILL.md give only the call usage instead of inline Python?
