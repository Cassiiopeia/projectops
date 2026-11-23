---
name: pro-brain
description: "Keep decisions, reasons and cautions as notes in the repo's knowledge folder per issue, change set or merge. Onboarding asks how you use a brain (repo only, own GBrain, team brain) and connects only with consent. Lists merged work with no note. Use after pro-report or 'save this to the brain'."
---

# Project Brain Note

## When to use

- The repo's capture mode says it is time (status tells you): `issue-end` right after `pro-report`, before closing the issue;
  `session-end` at the end of a work session with meaningful changes or after a feature commit (`pro-commit` points here);
  `merge` after a branch or PR is merged into the default branch.
- The user says "save this to the team brain", "write the knowledge note", "remember this decision for the project",
  "set up pro-brain", "what merged work has no note?".
- "Connect this repo to my GBrain", "we have a team brain", "how do teammates read our knowledge?": step 2 (usage).
- Not this skill: the report of what changed (`pro-report`); the user's personal memory (their own brain tools);
  scheduled syncing of a brain (the brain's own job reads the committed folder).

The brain stores **why and where**; git stores **what**. Reply in the user's language. Non-technical summary for owners:
`references/how-it-works.md`.

## What it never does

It writes **notes in the repo** (plus the files the repo's own vault rules require), and during onboarding, after the user
agreed, the repo switch in `version.yml` and one marked rule block. The only brain change it ever makes is `connect`: after
the user agreed, it adds **one new source** (`<project>-knowledge`) to the user's **own local** GBrain and syncs it. It never
overwrites or removes a source, never passes `--force`, and never changes hooks, mounts or other sources. Its only MCP
change is `connect --team --apply --yes`: one user-scope entry for the repo's team brain (and `--rotate` replaces that same
entry). A team brain token lives only in the user's credential store (`~/.projectops/config/config.json`, mode 600,
`../references/config-rules.md` §9), typed by the user in a terminal and referenced by name; it never goes into the chat, a
note, `version.yml`, `.mcp.json` or any output. Secrets, personal data and chat content never go into a note.

## Find the scripts

```bash
PYTHON=$(for _py in python3 python; do _path=$(command -v "$_py" 2>/dev/null) || continue; "$_path" -c "import sys; sys.exit(0)" 2>/dev/null && echo "$_path" && break; done)
[ -z "$PYTHON" ] && { echo "Python not found"; exit 1; }
ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
SCRIPTS="$ROOT/plugins/projectops-extras/skills/pro-brain/scripts"
[ -d "$SCRIPTS" ] || for B in ~/.claude/plugins/cache ~/.codex/plugins/cache ~/.gemini/extensions ~/.pi/agent/git; do
  H=$(find "$B" -maxdepth 8 -type d -path "*/projectops-extras/*skills/pro-brain/scripts" 2>/dev/null | sort -V | tail -1)
  [ -n "$H" ] && { SCRIPTS="$H"; break; }
done
[ -d "$SCRIPTS" ] || { echo "pro-brain scripts not found. Check the projectops-extras installation."; exit 1; }
echo "PYTHON=$PYTHON SCRIPTS=$SCRIPTS"
```

The Bash tool resets its state on every call. Put the printed paths into `{PYTHON}` and `{SCRIPTS}` in later commands.
Every command is `PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/brain_cli.py <command> ...` (Windows: `python {SCRIPTS}\brain_cli.py`).
Output is always JSON (`ok`, `code`, `summary`, `next`). Only `setup --apply --yes`, `connect --apply --yes` and
`connect --team --apply --yes` write; everything else is read-only.

## Capture modes

| `capture` | When a note is written | One note per |
|---|---|---|
| `issue-end` (default) | After `pro-report`, before the issue is closed | Issue |
| `session-end` | End of a work session with meaningful changes, or right after a feature commit with `pro-commit` | Topic of the change set |
| `merge` | When a branch or PR is merged into the default branch (by the agent, not CI) | Merged change set |
| `manual` | Only when someone asks | Whatever was asked |

## Steps

### 1. Status

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/brain_cli.py status
```

| `code` / field | Do |
|---|---|
| `switch_off`, reached through a pointer | One line: knowledge capture is off for this repo. Stop |
| `switch_off`, the user asked directly (or `summary` says the registry wants it on) | Step 2 (onboarding), turning it on |
| `switch_on` + `onboarding.open_questions` not empty | Step 2, then continue |
| `switch_on` + `onboarding.rule_block_state: outdated` | Refresh in place: `setup --apply --yes --claude-md add` (consent was already given), mention it in one line |
| `switch_on`, nothing open | Step 3. `sync_target.known: false` is normal for teammates: still write the note |

### 2. Onboarding (once per repo, at most three questions; re-run any time to change)

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/brain_cli.py setup
```

It reads the repo and returns `questions` (each with `recommended`), `target_options`, `block`, `block_diff` and
`version_yml_diff`. Ask only the questions it returns, in the user's language, recommended answer first, so pressing yes is
enough (AskUserQuestion when available, all questions in one dialog):

1. **Capture mode**: show `recommended_capture.reason` in one line.
2. **Rule block**: "May I add the knowledge rule to the project CLAUDE.md? (recommended)". Show `block_diff`. The block tells
   any agent in the repo when to run `/pro-brain`, and to search the team brain MCP (`brain_mcp`) first for design and
   decision questions, falling back to the knowledge folder.
3. **Usage** (always asked; `multi_select`): "How do you use this repo's knowledge?" Show `usage.current` and `usage.why`,
   recommended (`usage.recommended`, auto-detected) first. A personal GBrain (2 or 3) can be combined with a team brain (4).

| Answer | What it means | Then |
|---|---|---|
| 1 `repo-only` (default, most repos) | Notes live in the repo; no brain | Nothing else to set up |
| 2 `local-gbrain` | Your own GBrain on this machine (PGLite or local Postgres) | `connect` (plan), show it, `connect --apply --yes` after a yes |
| 3 `remote-gbrain` | Your own GBrain on another machine, reached over HTTP | `connect` (`--remote` when gbrain is not installed here): give the host commands; change nothing here |
| 4 `team-brain` | A gbrain HTTP server your team runs | Ask name, URL, token contact (prefill from `usage.team_brain` or `usage.registry_mcp_hint`), apply with `--team-brain-*` (the URL is probed, see `team_brain_probe`), then §Team brain connection |
| 5 `install-guide` | No GBrain yet | §Guided install, then behave like 1 until a brain exists |

Choosing no team brain when one is recorded (or hinted by the private registry) is `--team-brain-off`: it stores
`team_brain: "none"`, so nobody is asked again and the block drops the team brain line.

When the project CLAUDE.md is **gitignored** (`files.claude_md_state: ignored`), worktrees and teammates never see it.
Explain in one line and offer `target_options` in order: a tracked `.claude/rules/pro-brain.md` (recommended: Claude Code
loads `.claude/rules/*.md` at launch like `.claude/CLAUDE.md`), else the local `CLAUDE.md` registered in the
`pro-init-worktree` copy set (this machine's new worktrees only). Never edit anything before the answer.

Then apply what the user chose:

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/brain_cli.py setup --apply --yes [--enable] --capture MODE \
  --claude-md add|decline [--target PATH] [--agents-md] \
  [--team-brain-name gbrain-<project> --team-brain-url https://<host>/mcp --team-brain-contact WHO | --team-brain-off]
```

- `decline` is stored as `claude_md: "declined"`, so nobody is asked again. `--agents-md` also writes a tracked
  `AGENTS.md` (Codex) when `files.agents_md_needs_block` is true and the user agreed to it in the same answer.
- Run what `next` says (the worktree copy-set command for the local option), and commit `version.yml` and a tracked rule
  file together with the work via `pro-commit`.
- Team brain: the name must not be `gbrain` (that is the personal entry) and the URL must not carry a token. A new
  `--team-brain-url` is probed (`team_brain_probe`; `--no-probe` offline): `brain_answers` is good; `unknown_brain` (404)
  usually means a mistyped brain key, so show it before applying. Then each member follows §Team brain connection. The
  rule block gains "search the team brain first" only in this mode.

#### Personal GBrain (answers 2 and 3)

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/brain_cli.py connect [--source-id ID] [--source-root PATH] [--remote]
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/brain_cli.py connect --apply --yes [--source-id ID] [--source-root PATH] [--no-sync]
```

| `code` | Do |
|---|---|
| `ready` | Show source id, path and checked-out branch; apply after a yes |
| `already_connected` | Nothing to add; apply only re-syncs |
| `source_id_taken` | Stop and report the existing source. Never overwrite; offer `--source-id <other>` |
| `folder_already_connected` | Stop and report: another source already reads this folder or the repo around it |
| `no_notes_yet` | Run `connect` again right after the first note is committed (gbrain imports committed files only) |
| `remote_brain` | Give `commands` to run on the brain's host (where its database is reachable); no MCP change |
| `brain_not_initialized` / `gbrain_missing` | The user creates a brain (`gbrain init`) or installs it (`usage.install_url`); keep repo-only meanwhile |

#### Team brain connection (answer 4, every member, every machine)

```bash
# 1. once, by the user in a terminal (Claude Code: ! prefix); hidden input, never through the chat
python3 ~/.projectops/bin/projectops_cli.py launch cred set --name gbrain-<project> --secret-field token --prompt
# 2. plan, then apply after a yes
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/brain_cli.py connect --team [--token-cred NAME] [--project-mcp-json] [--no-probe]
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/brain_cli.py connect --team --apply --yes [--rotate] [--project-mcp-json]
```

It reads `team_brain` from `version.yml` and the token from the credential entry (`--token-cred` > the registry's
`infra.brains.<name>.token_cred` > the MCP name), then runs `claude mcp add --scope user --transport http <name> <url>
--header "Authorization: Bearer ..."` with the token passed to that process only. Output shows `<token>` instead.

| `code` | Do |
|---|---|
| `token_missing` | Show `store_token_command`; the user runs it in a terminal, then `connect --team` again |
| `ready` | Show `command` (placeholder) and `team_brain_probe.verdict`; apply after a yes; tell the user to restart the session |
| `already_registered` | Nothing to do. After a new token: store it under the same name, then `connect --team --rotate --apply --yes` |
| `claude_cli_missing` | Give `command`; the user types it with their token in their own terminal |
| `no_team_brain` / `bad_team_brain` | Back to step 2 (setup with `--team-brain-*`) |

`--project-mcp-json` also writes (merges) a committed `.mcp.json` entry whose header is `Bearer ${GBRAIN_<PROJECT>_TOKEN}`,
so teammates get the server just by opening the repo once they set that variable. Say in one line that a project entry
overrides a user entry of the same name, so offer it only when the team wants env-var setup; commit it with `pro-commit`.

#### Guided install (answer 5)

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/brain_cli.py install                  # detects gbrain, returns one question
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/brain_cli.py install --choice CHOICE  # local | postgres | supabase | thin-client | team-server
```

Ask the one question (recommended first), then show `requires`, `commands` and `verify`. It never runs them: commands that
carry a password or key are typed by the user in a terminal (`secret_note`). `postgres` needs the database and role to
exist first. After the user ran them, run `install` again (`brain_ready`) and continue with `connect` or `connect --team`.

Notes enter the brain from **whatever branch is checked out** at the source path. Say so in one line and offer
`default_branch_recipe`: a dedicated clone of the default branch (`connect --source-root <clone>`) plus its hourly
`schedule` line, so only merged notes reach the brain.

### 3. Is it worth a note?

Read the issue or the change set (report comment, PR, diff). Write a note only if at least one holds: a choice between
alternatives was made; a reason the code does not show; a caution the next person would hit; a project fact changed
(contract, convention, deploy, data rule); a confirmed root cause worth recognizing. Skip with one line
(`Skipped pro-brain: <reason>`) for typos, version bumps, formatting, renames, dependency bumps without behavior change,
routine chores, anything matching the repo's `skip` list, or knowledge an existing note already holds (link that note).

### 4. Collect the metadata

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/brain_cli.py collect [--issue N | --change-set | --commits a,b,c] \
  [--base SHA --head SHA] [--branch NAME] [--pr-number N --pr-url URL] [--merge-commit SHA] \
  [--deploy-target server,play --deploy-version X.Y.Z] [--capture-mode manual] [--title-hint "few words"]
```

| Situation | Input |
|---|---|
| Issue branch | nothing (base = merge-base with the development branch) |
| Shared branch, commits link the issue URL | `--issue N` |
| Change set since the last note (session-end, merge) | nothing in those modes, or `--change-set` |
| Change set mixing topics | read `commit_outline`, then one `--commits a,b,c` run per topic |
| Anything else | `--base` (commit before the first one) and `--head` |

`range_unknown` means it could not tell the commits apart: pass `--base`/`--head` or `--commits`. Pass `--capture-mode manual`
when the user asked directly outside the repo's mode. Get the PR with `pro-github list-prs` first when one exists.

The response has `frontmatter` (flat lines to append as is), `metadata`, and `suggested`: `id`, `file_name`, `note_dir`,
`topic_hints`, `existing_topics` (reuse these tags) and `related` notes (link the ones that really relate).

### 5. Write the note

Follow `references/note-format.md`: the repo's own `rules` and `template` win, then the default note. Keep it compact
(about 30 to 80 lines): summary, background, decision with reasons and rejected alternatives, behavior change, code pointers
as `path > Symbol()`, cautions, verification, follow-ups. No diffs, code bodies or raw logs. If `check` is set, run it on
the files you wrote and fix only your errors. Right before saving, run the self-review in `../references/sensitive-info.md`.

### 6. Commit it with the work

- Stage only the note and the files the repo rules made you touch, commit with `pro-commit`.
- Issue PR still open: commit on the issue branch. Already merged: a follow-up commit on the development branch. Never
  commit to `main` or a deploy branch directly. Push only when the user asks; the brain syncs from the default branch.

### 7. Report in one line

`Brain note: <path> (<n> keys, sync: <brain and source | none known on this machine>)` or the skip line. If `connect` said
`no_notes_yet` earlier in this conversation, run `connect` again now that a note is committed. Then continue the
pipeline (in `issue-end`: label done and close with `pro-github finish-issue`).

## Gap check

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/brain_cli.py gaps [--since YYYY-MM-DD|REF] [--ref origin/main] [--format text]
```

Lists work merged into the default branch since the last note commit that has no note: issues in `issue-end`, PR merges,
merges and direct commits otherwise. Git and note files only (no network, no LLM), so team-brain sync scripts can run it
every hour (`references/note-format.md` §Gap check). For each gap, write a note (step 3 onward) or skip it with a reason.

## Shared references

| Document | Read when |
|---|---|
| `references/note-format.md` | Steps 2, 4, 5: repo switch keys, note content spec, default notes, metadata keys, vault compatibility, gap check in sync scripts |
| `references/how-it-works.md` | The owner asks how it works, which usage answer fits, or what a good note looks like |
| `../references/sensitive-info.md` | Right before saving the note: masking table and self-review |
| `../references/config-rules.md` | Only when reading the owner's private registry by hand (§7 `project-blueprint`) |

## Customize

Your own language, tone and rules apply: see `../references/preferences.md`. Read them once at the start: run the snippet in `../references/preferences.md` with `SKILL_ID=pro-brain`.
Keys for this skill: the common `language`, `tone`, `rules` only. Repo behavior (mode, folder, template, rules, team brain,
skip list) lives in the repo switch so teammates share it; a personal GBrain is detected on each machine, never shared.
Preferences change presentation only; the durability check, secret protection and the never-touch-a-brain rule stay in force.
