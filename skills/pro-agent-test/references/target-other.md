# Walk something that is not an app, web or server (target: other)

> When to read: when Phase 0 sets the target to `other` (CI workflows, CLIs, libraries, templates, batch jobs).

This document is for when `pro-agent-test` walks **CI workflows, CLI tools, libraries, templates, batch jobs and migration scripts**.
You do not need it when walking an app (`target-app.md`), web (`target-web.md`) or server (`target-server.md`).

## Do not split into kinds

It is deliberately not split into `pipeline` · `cli` · `library`. **Once split, anything not on the list cannot be done again.**
Forcing projects into predefined boxes is the illness this skill got rid of (#589).

Instead, you decide first.

## Decide first — what is this project's output

For an app the output is a screen; for a server, a response. For `other`, it is **not fixed.** Only once you decide this
do you know what to base the verdict on.

| If the project is | The output is | Walking it means |
| --- | --- | --- |
| CLI tool · script | Files created · settings changed · exit code | Run the command with real arguments |
| Build · bundler | What is inside `dist/` | Run the build and open what comes out |
| Template · scaffolder | What gets copied into someone else's project | Create an empty project and integrate into it |
| CI workflow | Run conclusion · job status · artifacts | Trigger it and read the logs |
| Library | Behavior of the public API | Write one line of consumer code and run it |
| Migration | DB schema and data | Run it, roll it back, run it again |

**"There is test code, so it is fine" does not hold.** This skill itself has broken several times in someone else's hands
while its tests passed. You must actually run it and look at what comes out.

## Walking

```bash
... other run --root {ROOT} --command "{command}"
#   --cwd {directory}         where to run (default: --root)
#   --watch {path} ...        watch file changes before and after the run
#   --twice                   run twice to see whether the state stays the same
#   --env K=V ...             set environment variables
#   --timeout N               default 120 seconds
#   --expect-exit N
#   --expect-output "{text}"   partial match
#   --expect-file "{path}"     must exist after the run
#   --expect-absent "{path}"   must **not** exist after the run
```

To walk a scenario to the end:

```bash
... other run --root {ROOT} --name {scenario}
```

Unlike app and web, **one call walks the whole scenario.** There is no screen to judge,
so there is no reason to split it. If an earlier step fails, later steps are not walked — the real cause would be buried.

### You do not have to give expected results

All `--expect-*` options are optional. Without them it just runs and returns the result. **Judging what is
correct is your job.** If you give conditions, the machine compares them for you.

## What the machine watches for you — the reason to use it

| What it watches | Why people miss it |
| --- | --- |
| **`files` — file changes before and after the run** | People look at output and **do not look at side effects** |
| **`second_run.settled` — does it stay the same when run twice** | Idempotency matters, but almost nobody tries it by hand |
| Exit code, output, duration | The basics |

> **Measured**: 921 lines of this skill's test code were being copied into users' home directories. The copy command
> finished fine with exit code 0, and nobody **opened the copied result.** This is why `--watch`
> exists.

### Keep `--watch` narrow

Without it, files are not watched. If you pass the whole repo (`.`), things like `node_modules` and `.git`
get mixed in, it is slow, and it tells you nothing. Pass **only the places you expect to change.**

### `settled` is based on content

"Is the state the same after running twice" is judged by **content**. If a file is overwritten and its modification time changes but the content
is the same, it is idempotent. `files`, on the other hand, uses modification time — "was it touched" and "is the state the same"
are different questions, so they use different criteria.

Broken idempotency is not automatically a defect. Logs or timestamps may be mixed in. **You
judge it.** The machine only reports the fact that "it differed".

## `expect_absent` — what must not appear

Until now this skill only looked at **"what should be there"**. But what actually blew up was on the other side.

| Appeared when it should not | How it surfaced |
| --- | --- |
| Test code in users' home directories | By chance, months later |
| Temp files not deleted | When the disk filled up |
| An old workflow that should have been removed | It kept running after being turned off |

```json
{"do": "npx projectops --type spring --yes",
 "expect_file": ".github/workflows/PROJECT-COMMON-VERSION-CONTROL.yaml",
 "expect_absent": "skills"}
```

## Walking a CI workflow

`other run` does not trigger or track runs itself. `actions` in `pro-github` already does —
putting the same job in two places makes them drift apart.

```bash
# ① check statically before running — cheapest
... other run --command "python3 -m pytest .github/scripts/test/ -q" --expect-exit 0

# ② trigger (get user approval — it uses runner time)
... github_cli.py add-comment {owner} {repo} {issue} {body file}

# ③ tracking and cause
... github_cli.py actions resolve-branch {owner} {repo} {branch}
... github_cli.py actions show-run {owner} {repo} {run_id}
... github_cli.py actions joblog {owner} {repo} {job_id} --grep error
```

### Do not count `skipped` as a pass ⚠️

**We were caught here twice in a row.** When an earlier job dies, later jobs become `skipped`, and
on the surface it looks like "the build runs but there is no result".

| What you see | What is real |
| --- | --- |
| Trigger workflow ✅ success | Only the trigger succeeded |
| Build job ❌ | It died at the first comment for lack of permission |
| Remaining jobs ⏭ skipped | **Nothing was produced** |

**Base the verdict on whether the output was actually produced.** `conclusion: success` alone is
not enough — a success without an APK is not a success.

### Make sure you are not fixing a branch that is not run

Workflows run through `repository_dispatch` execute **the definition on the default branch**. If you fix it on the development
branch and trigger again, the old definition still runs. It is easy to misread this as "the fix did not take".

## What works and what does not

| | Works | Notes |
| --- | :-: | --- |
| Run commands · exit code · output | ✅ | |
| Observe file changes | ✅ | Only paths given to `--watch` |
| Check idempotency | ✅ | `--twice`, by content |
| Inject environment variables | ✅ | `--env` |
| Commands that need interactive input | ❌ | Use a non-interactive flag like `--yes` |
| Judge by watching the screen while running | ❌ | That is `app` · `web` |
| CI trigger · artifact check | ⚠️ | Combine with `actions` in `pro-github` (above) |

## What to check before walking

**Exit code 0 is not a pass.** This illusion is especially easy with `other`.

1. **Open** what was produced — actually read the files in `files.created`
2. **Run it twice** (`--twice`) — working only the first time is common
3. **Start from an empty state** — make sure it does not rely on leftovers on your machine
4. Write **what must not appear** with `expect_absent`
