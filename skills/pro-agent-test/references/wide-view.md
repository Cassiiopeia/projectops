# Look wide — cross-cutting · symmetry · other people's environments · ripple effects · proposals

> When to read: right after walking the requested flow (Phase 4.5 – 4.8). Always before writing the report.

This expands Phase 4.5 · 4.6 · 4.7 · 4.8 of `SKILL.md`.

## Phase 4.5 — Other places of the same kind ⚠️

**One feature passing is not the end.** Check whether other places of the same kind behave the same.
Defects found here survive the longest — if you look only at the one requested screen, you never see them.

### What actually gets missed — on any target

| Target | The requested spot passes | But elsewhere |
| --- | --- | --- |
| **App** | Sign-up password confirmation got "shake on mismatch" | Other password entry screens in the same app do not shake |
| **Server** | The create API got an owner check | **The update and delete APIs do not have it** — you can delete someone else's data |
| **Server** | The login API logs a request ID | The other APIs do not — only that stretch can be traced in an outage |
| **Web** | One form got double-submit protection | Other forms send twice when clicked twice |
| **Web** | One list has a page limit | Other lists are unlimited — they break once data grows |

**If you look only at the requested spot, everything is a "pass".** It is a defect only when you look at the whole project.

To catch this you **must know rules** such as "this project signals failure with a shake" or "resources have owners".
So only a QA who knows the project can do this step, and
that is exactly why it is valuable.

### Three lenses

| Lens | Question | How to find |
|---|---|---|
| **Cross-cutting** | Do **all** places of the same kind behave the same | State the behavior you just checked as a one-sentence rule, then find every place in the code that rule should reach |
| **Symmetry** | Does the paired action get the same treatment | The pair list below |
| **Ripple effect** | If this is touched, what is affected | **Counted separately in Phase 4.7** — not only code but docs, tests and copies |

### Symmetric pairs — if one side has it, the other should too

| If this side has it | Check the other side too |
|---|---|
| Input validation on sign-up | The same validation **on profile edit** |
| Permission check on create | Permission check **on read, update, delete** |
| Confirmation dialog before delete | On **other** irreversible actions too |
| What is created on sign-up | Is it cleaned up **on withdrawal** |
| Turn on | Turn off |
| State after login | Cleanup **after logout** (tokens, cache, screens) |
| Message on success | Message **on failure** |

### Order of work

1. From what you just walked, **state the rule in one sentence**

   | Target | Example rules |
   | --- | --- |
   | App · web | "Failures are signaled by a shake, not by color" · "Irreversible actions require confirmation" |
   | Server | "Resources have owners, and every verb (read, update, delete) checks it" |
   | Server | "Every request is logged with an identifier" |
   | Common | "Anything that returns a list has a limit" |
2. **Find every place in the code** that the rule should reach
   — only the agent can do this. It needs the judgment that "these are the same kind"
3. Check them one by one. **The places that fail are the defects**
4. Record the rule

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/e2e_cli.py note constraint --root {ROOT} --text "{what must hold}" --check "{what you see that means a violation}"
```

**The more rules accumulate, the faster this step gets.** Read them with `note show` at the start and compare against the accumulated rules
as they are. New screens automatically become check targets — this is where this skill
gets smarter the more you use it.

**Report what comes out of here separately.** It is a state where the requested feature passed but another place does not work.
If you mix them, it reads as "this work failed" ("consistency defect" in `reporting.md`).

## Phase 4.6 — The first run in someone else's environment ⚠️

**This applies to any target.** Apps have "works on my phone", and servers have "works on my local
DB". If Phase 4.5 looks at **other places of the same kind**, this looks at **the same thing in a different environment**.

| Lens | Question | How to walk it |
| --- | --- | --- |
| **Defaults** | Does it rely on environment defaults without setting them explicitly | Create an environment with different defaults and run |
| **Installed tools** | Does it rely on something only on my machine | Hide it and run |
| **First state** | Does it start from the empty state of a first-time user | Run where settings and records are cleared |
| **Unwalked branches** | Are there paths taken only when conditions match | Count branches in the code and walk the ones not walked |
| **Outputs** | Did you look at what was produced | Open the outputs |

### This skill itself fell into all five

| What | Why it did not blow up here |
| --- | --- |
| Missing workflow token permission | This repo's default is `write`. Other people's repos are new, so `read` |
| Shell syntax error | A branch taken only when triggered by an issue comment, so never walked |
| Instruction text looked at an old key | My machine had a browser installed, so that check was **always skipped** |
| 921 lines of test code copied into other people's home | Nobody opened the **result** of the copy |
| Record and scenario commands all broken | Tests only checked names and **never ran them** |

All of them were **"passes in my environment, blows up in someone else's"**. Not one of the five
was caught by the existing axes.

```bash
# hide installed tools and run
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/e2e_cli.py other run --command "{command}" --env PATH=/usr/bin:/bin

# run from an empty state
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/e2e_cli.py other run --command "{command}" --env HOME={empty directory}

# actually look at what was produced
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/e2e_cli.py other run --command "{command}" --watch {expected path} --twice
```

## Phase 4.7 — Count the ripple effects ⚠️

As important as finding the defect is **what breaks silently after it is fixed**.

| Step | What to do |
| --- | --- |
| ① | Write in one sentence **what the spot to fix was promising** (its contract) |
| ② | Count everything that **reads** that promise — call sites, docs, tests, copies, people's habits |
| ③ | Check one by one whether each still holds under the new promise |
| ④ | Report those that no longer hold along with the defect. Fixed or not, **the fact that you counted** must remain |

**② is the key.** If you count only code call sites, you miss half. Docs, tests, copies and assumptions also
read that promise.

### How it actually spread — the story of this skill

> **Decision**: move accumulated records from inside the project to the home directory (they disappeared with each worktree)
> **Broken promise**: "records are inside the project"

| Where that promise was read | What happened |
| --- | --- |
| Relative path computation in the completion message | `ValueError` — **5 commands crashed 100% of the time** |
| Output protection check | It was guarding a dead path |
| "Commit to the repo" in the reporting doc | Told users to commit what is no longer committed |
| Example output in the learning doc | Showed a screen that never appears |
| Secret-block reason "stays in history" | No longer true |
| The team-sharing assumption | Teammates no longer received it |

**Six places were affected, and nobody counted them at the time.** What could have been finished at once came out over three
releases. A machine cannot do the counting — what "reads that promise" is a question of meaning. You count it.

## Phase 4.8 — Ask whether this is right

Write down things that are **not defects but seem to have a better approach**. Do not fix them — only give an opinion.

| What to check | Example |
|---|---|
| Does the user know what to do next | It only says it failed, with no word on what to do |
| Can it be undone | Is there a way out after an accidental tap |
| Is the same thing done in two ways | Some screens use a sheet, others a dialog |
| Can you tell while waiting | It takes long, with no progress indicator |

**Do not write "my taste".** If it cannot be explained as a problem the user will hit, do not write it.
