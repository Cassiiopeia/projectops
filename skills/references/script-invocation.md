# Script call standard (detail)

The rationale and detail behind `common-rules.md` §"Distributed per-skill Python calls" and §"Finding the scripts". The standard block itself is in
`common-rules.md` §"Standard call pattern" — read this document only when you change its shape.

## 3-layer architecture

`config-get` / `init-config` were removed — the agent handles config directly with the Read/Write tools (`config-rules.md`).
The single `scripts/suh_template/` module was removed too. Each skill owns `skills/<skill>/scripts/<scope>_cli.py`,
and shared domain logic is imported from `scripts/common/`.

- **Layer 1** `scripts/common/`: pure domain functions such as GitHub HTTP, config loading, paths, titles, and issue numbers
- **Layer 2** `skills/<skill>/scripts/<scope>_cli.py`: 1 skill = 1 py = argparse subcommands
- **Layer 3** `SKILL.md`: user conversation, writing documents, calling Python

`github_cli.py` absorbed issue create, read, edit, search, comments, labels, assignees, PRs, secrets, actions, and
`normalize-title`, `create-branch-name`, `get-commit-template` (pro-issue merge, #464).

## Finding the scripts: local → fallback to harness install paths (#524·#528·#542 — do not change this shape)

The standard block **resolves only the "plugin root"**, so no skill name is baked into a path. That way, in every
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
| `summary` | One-line human-friendly summary | `"PR #123 생성 완료"` (literal output, "PR #123 created") |
| `next` | Next-action hint | `"deploy-status owner repo --pr 123"` or null |

For designing a new subcommand, see `mcp-subcommand-rules.md`.

## GitHub work principles

**Call GitHub API work through each skill's `<scope>_cli.py` subcommands.** Do not add curl recipes,
Python heredocs, or temporary Python files to skill docs.

- The CLI loads the PAT automatically from the `GITHUB_PAT` environment variable, then `config.json` (`scripts/common/config.py:get_github_pat`).
- If you need a new GitHub API behavior, read `mcp-subcommand-rules.md` and add a `scripts/common/gh_client.py` helper + a subcommand in that skill's `_cli.py` + tests.
- The `gh` CLI is not used because it needs a separate install and behaves differently across Windows and macOS.
- Direct curl calls are temporarily allowed only for urgent investigation where no subcommand exists yet. If it gets used repeatedly, promote it to a subcommand right away.

Typical call: after finding the scripts with the standard block and `SKILL=pro-github`,
`PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py get-issue {owner} {repo} {number} --with-comments`.

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
