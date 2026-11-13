# Script call standard

How every skill calls its Python CLI, and the fallback when the fixed entry point is not there yet.
Read when the fixed entry point is missing or answers `scripts_not_found`, or when you change the call shape.

## Contents

- [Fixed entry point](#fixed-entry-point)
- [Fallback lookup block](#fallback-lookup-block)
- [3-layer architecture](#3-layer-architecture)
- [Finding the scripts: why the fallback block has this shape](#finding-the-scripts-why-the-fallback-block-has-this-shape)
- [Setting the PYTHON variable — why this shape](#setting-the-python-variable--why-this-shape)
- [OS compatibility (verified by measurement)](#os-compatibility-verified-by-measurement)
- [MCP-style JSON output standard (4 fields enforced)](#mcp-style-json-output-standard-4-fields-enforced)
- [GitHub work principles](#github-work-principles)
- [Windows corporate network](#windows-corporate-network)

## Fixed entry point

Every skill calls its CLI through one fixed entry point (#942):

```bash
PYTHONIOENCODING=utf-8 python3 ~/.projectops/bin/projectops_cli.py <skill> <subcommand> [args]
```

On Windows use `python` instead of `python3`. `<skill>` is the skill name without `pro-`
(github · commit · report · review · testcase · changelog-deploy · init-worktree · figma · agent-test · ui-design ·
presentation · oss-consult · launch · image · code-consult). The entry point finds the newest installed script and passes the arguments through.
`newer_installed` in the response means an old version is running.

- **In zsh, do not store a command in a variable** — with `P="python3 …/projectops_cli.py github"; $P get-issue …`, zsh treats the variable as one word and fails with `exit 127`. Wrap it in a function instead:
  `G(){ PYTHONIOENCODING=utf-8 python3 ~/.projectops/bin/projectops_cli.py github "$@"; }` then `G get-issue {owner} {repo} {number}`.
- **Do not `cd` into the scripts folder** — once you leave the project folder, the git root and issue number can no longer be found (#943). When calling from outside the project, pass `--root <project>`.
- Calls that carry Korean or other non-ASCII text must set `PYTHONIOENCODING=utf-8`.

## Fallback lookup block

Use this when `~/.projectops/bin/projectops_cli.py` does not exist yet (first run), answers `scripts_not_found`,
or answers `bad_args` with a skill list that lacks your skill (an older copy; a direct call updates it).
Set `SKILL=` to the skill folder (for example `pro-github`). **The Bash tool resets its state on every call**, so run it once
per skill run and write the printed paths into later calls as values: `PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/<scope>_cli.py <subcommand> [args]`.

```bash
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
PYTHON=$(for _py in python3 python; do _path=$(command -v "$_py" 2>/dev/null) || continue; "$_path" -c "import sys; sys.exit(0)" 2>/dev/null && echo "$_path" && break; done)
[ -z "$PYTHON" ] && { echo "Python not found"; exit 1; }
SKILL=<skill>; ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
[ -d "$ROOT/skills/$SKILL/scripts" ] || for B in ~/.claude/plugins/cache ~/.codex/plugins/cache ~/.gemini/extensions ~/.pi/agent/git; do
  H=$(find "$B" -maxdepth 8 -type d -path "*/projectops/*skills/$SKILL/scripts" 2>/dev/null | sort -V | tail -1)
  [ -n "$H" ] && { ROOT="${H%/skills/$SKILL/scripts}"; break; }
done
# Home-copied installs from npx projectops: GitHub Copilot and Cursor (#200)
[ -d "$ROOT/skills/$SKILL/scripts" ] || for B in ~/.copilot ~/.cursor; do [ -d "$B/skills/$SKILL/scripts" ] && { ROOT="$B"; break; }; done
SCRIPTS="$ROOT/skills/$SKILL/scripts"
[ -d "$SCRIPTS" ] || { echo "projectops skill scripts not found. Check the plugin installation."; exit 1; }
echo "PYTHON=$PYTHON SCRIPTS=$SCRIPTS PROJECT_ROOT=$PROJECT_ROOT"
```

To find and call in one block (the self-contained 5-line principle), put
`PYTHONIOENCODING=utf-8 "$PYTHON" "$SCRIPTS/<scope>_cli.py" <subcommand> [args]` in place of the `echo` line.
To call another skill's script, change only the `SKILL=` value. **Do not change the block's shape** — the reasons are below.

## 3-layer architecture

`config-get` / `init-config` were removed — the agent handles config directly with the Read/Write tools (`config-rules.md`).
The single `scripts/suh_template/` module was removed too. Each skill owns `skills/<skill>/scripts/<scope>_cli.py`,
and shared domain logic is imported from `scripts/common/`.

- **Layer 1** `scripts/common/`: pure domain functions such as GitHub HTTP, config loading, paths, titles, and issue numbers
- **Layer 2** `skills/<skill>/scripts/<scope>_cli.py`: 1 skill = 1 py = argparse subcommands
- **Layer 3** `SKILL.md`: user conversation, writing documents, calling Python

Examples: `pro-github/scripts/github_cli.py` · `pro-report/scripts/report_cli.py` ·
`pro-review/scripts/review_cli.py` · `pro-changelog-deploy/scripts/changelog_cli.py` (other skills follow the same rule).
Config is handled by the agent with Read/Write, not by the CLI (`config-rules.md`).

`github_cli.py` absorbed issue create, read, edit, search, comments, labels, assignees, PRs, secrets, actions, and
`normalize-title`, `create-branch-name`, `get-commit-template` (pro-issue merge, #464).

## Finding the scripts: why the fallback block has this shape

Local → fallback to harness install paths (#524·#528·#542).

The fallback block **resolves only the "plugin root"**, so no skill name is baked into a path. That way, in every
skill only the `SKILL=` value differs and the rest is character-for-character identical. Even as harnesses are added,
this is the only shape that needs changing.

| Location | When | Version level |
|---|---|---|
| `$ROOT/skills/<skill>/scripts/` | **The projectops repo itself** (the only place where `skills/` really exists) | n/a |
| `~/.claude/plugins/cache/{marketplace}/projectops/{version}/` | Claude Code | yes |
| `~/.codex/plugins/cache/{marketplace}/projectops/{version}/` | Codex | yes |
| `~/.gemini/extensions/projectops/` | Gemini | no |
| `~/.pi/agent/git/github.com/{owner}/projectops/` | pi | no |

**Check harnesses one at a time with `for`; do not list them on one line (#542 — never revert this).**
If several path patterns are listed in one `ls`, zsh **does not run the whole command** with `no matches found`
as soon as any one of them does not match. Claude Code's shell is zsh, so for users without Codex, the Claude path
listed next to it was thrown away too. In measurements, an empty value came back even though the latest cache
(4.2.44) existed; when another install was present, **an old version (4.2.19) ran silently**; and in an environment
with only Claude Code installed, the skill died outright.

**Use `find` per location instead of `ls` + a list.** `find` skips only the paths that do not exist.
The order of the `for` list sets the priority, and `sort -V | tail -1` picks the newest of several versions in one location.

Do not remove the final `[ -d "$SCRIPTS" ] || { ...; exit 1; }` guard either. `cd ""` does not fail and stays in
the current directory, so without the guard a missing script passes silently and runs from the wrong place.

The `ROOT=...` line falls back to **local if present, otherwise the harness install**. It is correct in both environments.

- User projects have no `skills/` (excluded on integration) → the harness install is used automatically.
- The projectops repo has `skills/` → its own code is used. **Changes can be tested immediately.**

The cache used to be checked first (#386), and then edits to skills in this repo **could not be used until a
release refreshed the cache.** A newly added subcommand failed right away with "no such command".

`_cli.py` imports `scripts/common` relative to `Path(__file__).parents[3]` (independent of cwd),
so as long as the script file is in the right place, imports resolve regardless of where you `cd`.
Config (`~/.projectops/config/config.json`) is always relative to the user's home, independent of the project location.

## Setting the PYTHON variable — why this shape

Instead of only `command -v python3`, it confirms real execution with `-c "import sys; sys.exit(0)"`. On Windows,
when `python3` points to the Microsoft Store stub, it exists but fails to run with `Exit code 49`.
For the same reason, do not call `python3 -c` directly. Calls that carry Korean (non-ASCII) text add
`PYTHONIOENCODING=utf-8` (#653 — an incident where Korean text was committed garbled under Windows' default cp949).

## OS compatibility (verified by measurement)

- Windows Git Bash MINGW64 ⭕
- WSL Linux bash 5.2 ⭕
- macOS bash/zsh ⭕ (POSIX compatible)
- PowerShell not supported (the Claude Code Bash tool forces bash)

## MCP-style JSON output standard (4 fields enforced)

Every `<scope>_cli.py` subcommand's output = JSON on stdout. `emit()` in `scripts/common/emit.py` guarantees the 4 fields.

| Field | Meaning | Example |
|---|---|---|
| `ok` | Success or not | `true` / `false` |
| `code` | Identifier (for debugging on error) | `ok`, `missing_pat`, `github_api_404` |
| `summary` | One-line human-friendly summary | `"created PR #123"` |
| `next` | Next-action hint | `"deploy-status owner repo --pr 123"` or null |

For designing a new subcommand, see `mcp-subcommand-rules.md`.

## GitHub work principles

**Call GitHub API work through each skill's `<scope>_cli.py` subcommands.** Do not add curl recipes,
Python heredocs, or temporary Python files to skill docs.

- The CLI loads the PAT automatically from the `GITHUB_PAT` environment variable, then `config.json` (`scripts/common/config.py:get_github_pat`).
- If you need a new GitHub API behavior, read `mcp-subcommand-rules.md` and add a `scripts/common/gh_client.py` helper + a subcommand in that skill's `_cli.py` + tests.
- The `gh` CLI is not used because it needs a separate install and behaves differently across Windows and macOS.
- Direct curl calls are temporarily allowed only for urgent investigation where no subcommand exists yet. If it gets used repeatedly, promote it to a subcommand right away.

Typical call: `PYTHONIOENCODING=utf-8 python3 ~/.projectops/bin/projectops_cli.py github get-issue {owner} {repo} {number} --with-comments`.

### Common GitHub API error handling

| HTTP code | Cause | Action |
|-----------|------|------|
| 401 | PAT expired or not sent | Guide PAT re-registration with `config-rules.md §2~5` |
| 403 | Insufficient permissions (no repo/workflow scope) | Ask to check the PAT's permissions |
| 404 | owner/repo typo or private repository access | Recheck `git remote get-url origin` |
| 422 | Bad request value (missing label, duplicate PR, and so on) | Parse the error message and tell the user |
| 35 (curl exit) | Windows corporate network SSL error | Add `--ssl-no-revoke` and retry (below) |

## Windows corporate network

- If curl fails with `exit 35` (SSL error), certificate revocation checking is blocked → retry curl with `--ssl-no-revoke`.
- `pip install` may not work on a closed network. Scripts prefer the standard library; if an external package is truly needed,
  they try to install it and, on failure, give manual install instructions (`mcp-subcommand-rules.md` §5).
