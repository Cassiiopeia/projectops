---
name: pro-brain
description: "At the end of an issue, keep what the next person needs (decisions, reasons, cautions) as one note in the repo's knowledge folder, committed with the work, when version.yml turns it on. Skips trivial issues. Never touches any brain. Use after pro-report, or for 'save this to the team brain'."
---

# Project Brain Note

## When to use

- Right after `pro-report` posted the report, before the issue is closed (`pro-report` points here when the repo switch is on).
- The user says "save this to the team brain", "write the knowledge note", "remember this decision for the project".
- Not this skill: the report of what changed (`pro-report`, posted on the issue); personal memory of the user (their own brain tools);
  syncing a brain (the brain's own sync job reads the committed folder).

`pro-report` is what changed in this issue. `pro-brain` is what stays true about the project afterwards: the decision,
why it was made, and what the next person must not trip over. Reply in the user's language.

## What it never does

It writes **one repo note (plus files the repo's own vault rules require)** and nothing else. It never writes to, reconfigures
or assumes any brain, MCP server, hook, mount or source, whether the user runs a local brain, a remote HTTP brain, a team
brain or none. A brain that syncs the folder picks the note up from the default branch on its own schedule.

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
Output is always JSON (`ok`, `code`, `summary`, `next`). The CLI is read-only: it collects facts, you judge and write.

## Steps

### 1. Is it on for this repo?

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/brain_cli.py status
```

The switch lives in the repo, so every teammate who clones it sees the same answer: `version.yml`
`metadata.template.options.knowledge` (`references/note-format.md` §Repo switch).

| `code` | Do |
|---|---|
| `switch_off` | Say in one line that knowledge capture is off for this repo, and stop. If `summary` says the private registry wants it on, show the user the `version.yml` block to add; do not add it unasked |
| `switch_on` | Go on. `sync_target.known: false` is normal for teammates and new machines: still write the note, and say in the final line that no sync target is known on this machine |

### 2. Did this issue produce durable knowledge?

Read the issue, its report comment, the PR and the diff. Write a note only if at least one holds:

- A choice between alternatives was made (what was picked, what was dropped and why).
- A reason that the code does not show (a constraint, an outside rule, a past incident).
- A caution or trap the next person would hit (ordering, a flaky tool, a value that must change together with another).
- A project fact changed: a contract, a convention, a deploy or infra fact, a data rule.
- A bug's confirmed root cause worth recognizing next time.

Skip with one line (`Skipped pro-brain: <reason>`) for typos, version bumps, formatting, renames, dependency bumps
without behavior change, routine release chores, or knowledge an existing note already holds (link that note in the
report thread instead). Never write an empty or filler note.

### 3. Collect the metadata

Get the PR first with `pro-github list-prs` (head = the issue branch) when one exists. Then:

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/brain_cli.py collect [--issue N] [--base SHA --head SHA] [--branch NAME] \
  [--pr-number N --pr-url URL] [--deploy-target TARGET --deploy-version X.Y.Z]
```

| Situation | Range input |
|---|---|
| On the issue branch | nothing: base = merge-base with the development branch |
| Shared branch, commit messages link the issue URL | `--issue N` (only those commits are counted) |
| Anything else | `--base` (commit before the first issue commit) and `--head` |

`code: range_unknown` means the CLI could not tell the issue's commits apart: pass `--base`/`--head`. The response has
`metadata`, ready `frontmatter` lines (flat keys, `references/note-format.md` §Metadata keys) and `created` (Asia/Seoul date).

### 4. Write the note

Follow `references/note-format.md`: the repo's own `rules` and `template` first, then the default format. Append the
`frontmatter` lines to the note's frontmatter as is; never remove keys the repo's schema requires. Body: decisions, why,
cautions for the next person, links (issue, PR, report comment, related notes). If `check` is set, run it on the files you
wrote and fix only the errors you caused.

Right before saving, run the self-review in `../references/sensitive-info.md`. No secrets, hosts, account names,
personal data, and no personal chat content: describe the decision, do not paste what someone said.

### 5. Commit it with the issue's work

- Stage only the note and the files the repo rules made you touch (`git add <paths>`), commit with `pro-commit`.
- Issue PR still open: commit on the issue branch so the note ships in the same PR.
- Already merged: commit on the development branch as a follow-up. Never commit to `main` or a deploy branch directly.
- Push only when the user asks. The brain sync reads the default branch, so the note reaches the brain after release.

### 6. Report in one line

`Brain note: <path> (<n> keys, sync: <brain name and source id | none known on this machine>)` or the skip line.
Then continue the pipeline: label done and close (`pro-github finish-issue`).

## Shared references

| Document | Read when |
|---|---|
| `references/note-format.md` | Step 1 and 4: repo switch, default note, metadata keys, compatibility with vault rules, source naming |
| `../references/sensitive-info.md` | Right before saving the note: masking table and self-review |
| `../references/config-rules.md` | Only when reading the owner's private registry by hand (§7 `project-blueprint`) |

## Customize

Your own language, tone and rules apply: see `../references/preferences.md`. Read them once at the start: run the snippet in `../references/preferences.md` with `SKILL_ID=pro-brain`.
Keys for this skill: the common `language`, `tone`, `rules` only.
Preferences change presentation only; the durability check, secret protection and the never-touch-a-brain rule stay in force.
