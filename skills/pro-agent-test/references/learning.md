# Accumulate what you learn, and keep outputs safe

> When to read: when you record screens, rules and pitfalls you learned with `note`, when you read accumulated records, and when you are unsure where outputs belong.

> **The default for the output folder is "do not upload".** In a folder where you cannot know in advance what will appear,
> making exceptions the default means a file with an account or address in it eventually goes up too — this
> nearly happened.
>
> Now the run folder that `get-output-path` creates **carries its own tracking exclusion** — there is nothing
> extra to do. `learned.json` is stored outside the project (in the home directory) in the first place, so it never reaches the repo.
> If there is a file to share, pick just that one and attach it to the issue.

This document expands **"Accumulating records"** in `SKILL.md`.
It covers the commands for leaving notes and why, plus the rules for putting test outputs in the repo.

### Keep what you learn for the project (self-improvement)

As you walk, you learn things that hold only for this app — where a button sits on a screen,
where you stumbled. **If you do not record them, next time you have to find them out from scratch.**

#### First, write down what this app must uphold

If you only know coordinates and pitfalls, you only see as far as "the screen appeared". **You must know this app's rules to recognize violations.**

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/e2e_cli.py note constraint \
  --text "Do not use warning colors for failures or errors" \
  --check "Violation if red text or Icons.error is on screen" --root {PROJECT_ROOT}
```

`--check` is the key. If you only write the rule, you will not recall it while walking. Write **what you see
that means a violation**, so you can judge the moment you see the screen.

Where to get them — the project's `CLAUDE.md`, service principles in `docs/`, design system documents.
In Phase 1, when you choose what to walk, **use this list as check items too.**

> Real case: in one project, registering "violation if it failed without an identifier" let us
> flag right away a state where the session had dropped but home still looked normal.

**Separate what goes where.** What holds only for this app goes in the project; what holds for any app goes in
**one place at this-computer scope** (why: burying general knowledge in each project means you hit it once more in the next project).
Tool usage (browser login method, recording commands, etc.) belongs to `pro-launch`'s `learn`, not here.

| scope | What | Where it is stored |
| --- | --- | --- |
| `project` | This app's screens, rules, setup | `~/.projectops/agent-test/{owner}__{repo}/learned.json` |
| `flutter` | Applies to every Flutter app | `~/.projectops/agent-test/_machine/learned.json` (shared by all repos) |
| `platform` | Device or OS level | Same as above |

```bash
# summary (5 constraints and 5 pitfalls, 120 chars per item). Everything: --all
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/e2e_cli.py note show --root {PROJECT_ROOT}

# clues that identify the screen and tap targets — elements first; ratios only for screens with an empty element tree (Flutter canvas, maps)
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/e2e_cli.py note screen --name Login --anchor "Sign in to get started" \
      --target "Google=text:Continue with Google" "Close=desc:Close" "MapPin=at:0.5,0.3725" \
      --screen-size 1080x2400 --root {PROJECT_ROOT}

# result of tapping that target with app tap --shot — ok if screen_changed is true, fail if not_found or false
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/e2e_cli.py note screen --name Login --target Google --result ok --root {PROJECT_ROOT}

# where you stumbled
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/e2e_cli.py note pitfall --text "The consent list needs 3-4 swipes to reach the end" --scope project --root {PROJECT_ROOT}

# you hit an existing pitfall or rule again (ok) or it was wrong (fail) — the number is the index from note show
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/e2e_cli.py note pitfall --index 3 --result fail --root {PROJECT_ROOT}

# this run's result
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/e2e_cli.py note run --name social-signup --text "Pass — 2 bugs found" --root {PROJECT_ROOT}
```

`--target` format: `label=text:text` · `label=id:resource-id` · `label=desc:description` (if the same text appears more than once, append `|index=1`) ·
`label=at:0.5,0.8` (0–1 ratio). **Pixels are rejected** (`pixels_rejected`) — `app tap` does not accept pixels, so they would be useless even if saved.
If you also pass `--screen-size`, it tells you the ratio-converted value in `hint`.

#### Tools bring the records back to you — memory principles (`skills/references/memory-principles.md`)

- **Reading**: the `memory` in `detect` and `scenario show` responses carries up to 2 rules, 2 pitfalls and 1 this-computer pitfall that fit the context.
  The same area (target for detect, scenario name for scenario) is included only once a day. Memories where failures clearly outweigh successes are not included.
- **Duplicates**: before writing a pitfall or rule, it looks for similar ones in this repo and at this-computer scope. If clearly the same (60% or more of distinctive words),
  it does not write a new one but merges (`merged_into`). If ambiguous (25–60%), it writes a new one but shows `related` — if you
  judge it the same knowledge, follow `next`: `note forget --kind pitfall --index <new number>`, then `--merge-into <that number> --text "…"`.
- **Score and staleness**: entries have `ok` · `fail` · `last_seen`. The same result on the same day counts once.
  After 90 days, or when failures lead, `verify` is attached and the entry moves back — it is not deleted. Delete only with `note forget`.
  Old entries (no score) are read as 0 · 0 · date added.
- **Screen record migration**: old pixel records (`taps`) are converted to ratios (`at`) using `measured_on` when read, and get `verify`.
  The original stays in `legacy_taps`. Records with unknown resolution are marked `unconverted` — measure again and record with `--target`.
  The file is saved in the new schema (`schema: 3`) on the next write.

#### Cleaning up mixed scopes — `note tidy`

Earlier, `flutter` and `platform` pitfalls were also stored in the repo. `note tidy` **only shows a plan**, and moves only when you pass `--apply`.
It only moves; it does not delete.

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/e2e_cli.py note tidy --root {PROJECT_ROOT}           # plan
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/e2e_cli.py note tidy --apply --root {PROJECT_ROOT}   # actually move
```

| Result field | Meaning |
| --- | --- |
| `to_machine` | `flutter` · `platform` pitfalls → this-computer scope. If the same one already exists, scores are merged |
| `to_launch` | Pitfalls that look like tool usage → `launch_cli learn` (project goes to the repo, the rest to this-computer scope) |
| `skipped` | Not moved — the area could not be decided (set it with `--launch number=web`) or it exceeds 200 characters (shorten it and `learn` directly) |
| `review` | Negative absolutes ("does not work", "cannot") — check whether still true, and if not, `note forget` |

#### Accumulated records survive skill updates

| What | Where | Effect of a skill update |
| --- | --- | --- |
| Procedures and scripts | Harness install path (`~/.claude/plugins/cache/...`, etc.) | Replaced entirely |
| **Accumulated records** | **Home** `~/.projectops/agent-test/{owner}__{repo}/learned.json` — survives creating worktrees | **None** |

The records belong to the project; the skill only reads them. So however many times the skill is updated,
and from whichever harness it is called (Claude Code, Codex, Gemini, Pi), the same file carries on.

Keep the following when reading and writing — **not losing what was accumulated always comes first.**

- **Do not touch unknown fields.** They may have been added by the next version or another harness
- **Do not delete what you cannot read.** If the file is broken, move it to `learned.broken-{timestamp}.json`,
  show a warning, and start fresh (overwriting silently would lose everything accumulated so far)
- **Write atomically.** It writes to a temp file and swaps it in, so the existing file stays intact even if writing stops midway
- The `schema` field marks the version. Bump it only for changes that **remove** a field

> Find tap targets **by element first** (`launch_cli.py app tap --text|--id|--desc`). `at:` ratio records are
> for screens with an empty element tree (Flutter canvas, maps) and are passed to `app tap --at` as is.
> The `targets` in the `note screen` response include the `app tap` arguments for tapping each target.
>
> Records are **hints, not guarantees.** When the screen changes, they miss. Even when using a recorded target, do not skip
> the step that checks the result after tapping (`stepping.md` Phase 3 ③), and record that result with `--result`.

### Do not put credentials in the records ⚠️

Records are stored in the **home directory, not the repo** (`~/.projectops/agent-test/{owner}__{repo}/`).
They are not committed, so there is no worry about history, but **they stay on disk in plain text and are
read again on every run.** Once in, they stay exposed, so block them before writing.

If `note` contains an email, phone number, JWT or password, it **refuses to record and tells you why.**
Write something like "with the test account" instead of the concrete value. `access` likewise does not accept password
values — record only which environment variable to read from.

```
{"ok": false, "code": "secret_detected",
 "error": "The text to record contains <kind of secret>",
 "hint": "This file stays on disk in plain text and is read again on every run. Write something like 'with the test account' instead of the actual value"}
```

(The script prints these messages in Korean: `error` says the content contains an email, and `hint` says the file stays on disk in plain text and is read again on every run.)

Where records are stored is reported by `knowledge_dir` in `detect`, or by `doctor --root`.

### Judge evidence for upload separately

Screenshots attached to an issue are uploaded with `upload-image` in `pro-github` (do not commit them to the repo —
`references/reporting.md`). **This cannot be filtered automatically**, because it requires judging even the text inside the
image. Social login screens **show the email address as is.** If it is truly needed to show the problem,
crop or mask that part before uploading.
