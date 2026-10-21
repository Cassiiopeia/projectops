# deploy mode — commands and messages per step

> When to read: when you actually run deploy mode. SKILL.md has the summary of each step's decision rules; this file has the bash to run as is and the messages to show the user. Show the messages in the user's language (or the configured `language` preference).

**Bash is stateless.** Write the **real values** obtained in [Before you start] into `{PAT}` · `{OWNER}` · `{REPO}` · `{PYTHON}` · `{SCRIPTS}` · `{PROJECT_ROOT}` · `{HEAD_BRANCH}` · `{BASE_BRANCH}` below. Never assume a variable from an earlier Bash call is still alive. `{HEAD_BRANCH}`/`{BASE_BRANCH}` are the values resolved in [Before you start §5] (fallback develop/main). Do not hard-code them.

## Step 1: Check commit state

Run each command below **separately**. Never combine them into one line.

```bash
git status --short
```

```bash
git fetch origin
```

```bash
# Check that the current branch is the release head — merging or pushing from another branch changes the wrong place
git branch --show-current
```

```bash
# Commits not yet in base (production) — the key check, since the goal is a head→base PR
git log "origin/{BASE_BRANCH}..HEAD" --oneline 2>/dev/null
```

```bash
# Fallback in case the result above is empty — also compare against the head remote
git log "origin/{HEAD_BRANCH}..HEAD" --oneline 2>/dev/null
```

Message when there are uncommitted changes:
```
There are uncommitted changes. Commit them first and run this again.
```

## 1-1. Bring base up to date (merge the reverse difference — never skip)

> **Why**: RELEASE-CHANGELOG leaves the version finalize commit **only on base (main)**. If head (develop) opens the next release PR without that commit, the version file conflicts and the workflow fails.

```bash
# Align head with the remote first. If you pull --rebase after creating a merge commit, the merge is undone and base commits get rewritten.
git pull --rebase origin "{HEAD_BRANCH}"
# If someone else's uncommitted changes block it (no stash — it would sweep in another session's work):
#   git fetch origin && git merge --ff-only "origin/{HEAD_BRANCH}"
#   This works on a dirty working tree when no files overlap. If it cannot fast-forward (diverged), stop and ask the user.
# Commits that base has and head does not (the reverse difference)
git log "origin/{HEAD_BRANCH}..origin/{BASE_BRANCH}" --oneline
```

If there are results, show the list to the user and merge:

```bash
git merge --no-edit "origin/{BASE_BRANCH}"
```

- The merge commit shows up in the step 2 push list and is pushed in step 3.
- **On a conflict, stop** and tell the user which files conflict. Do not drop one side or run `git merge --abort` or `reset` on your own. Agree with the user on a resolution that keeps the intent of both sides.

## Step 1.5: Release context awareness (is this an app review repo?)

> **Why**: in a repo with automatic App Store / Play Store review submission, a `main` release is not an "internal deploy" but a **user-facing release**. The release notes become the store's "What's New" text and go into review as is. **Backend repos (spring/python and so on) pass silently with no effect.**

Collect signals (no PAT needed, scans local files only):

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/changelog_cli.py detect-release-context --project-root "{PROJECT_ROOT}"
```

Get `signals` (facts) and `hint` (a weak hint) from the returned JSON. **`hint` is only a reference; the agent makes the final call.** The branch table is in SKILL.md step 1.5.

Confirmation message (**once**, when `APP_RELEASE == unset` and app review is detected; plain language only — no config keys or file paths):

```
📱 This repository looks like it deploys into App Store / Play Store review.
   If so, the release notes you write now become the store's "What's New"
   text as is and go into review.

Should I treat this repository as an "app review deploy" from now on and handle release notes more carefully?
1. Yes (it is an app review deploy)
2. No (it is a regular deploy)
```

Config updates per answer: `config.md` §4. Then go to step 2.

## Step 2: Confirm before push

```
📋 Commits to push ({HEAD_BRANCH} → not yet in {BASE_BRANCH}):
  - {commit message 1}
  - {commit message 2}

Push to the {HEAD_BRANCH} branch?
1. Yes, push
2. Cancel
```

## Step 3: Push

```bash
# The remote sync already happened in step 1-1. A pull --rebase here would undo the 1-1 merge commit.
git push origin "{HEAD_BRANCH}"
```

- If it is rejected as non-fast-forward, **do not force push.** Integrate with `git pull --rebase=merges origin "{HEAD_BRANCH}"`, which keeps the merge commit, then push again.
- The version does not go up after the push. RELEASE-CHANGELOG finalizes the version in the release PR right before the merge (+1 per release).

## Step 4: Commit analysis

Analyze the head → base changes **before** creating the PR:

```bash
git fetch origin "{BASE_BRANCH}" "{HEAD_BRANCH}" 2>/dev/null || true
# The analysis base is origin/{HEAD_BRANCH}, not HEAD — workflows such as the README version update can put the remote ahead
git log "origin/{BASE_BRANCH}..origin/{HEAD_BRANCH}" --pretty=format:"%s" | grep -v "\[skip ci\]" | head -60
```

Classification and rewrite rules: `release-notes.md`.

## Step 5 · Step 5.5

Note writing, file location, fixed structure and approval messages: `release-notes.md`. Branch conditions: SKILL.md.

## Step 6: Create the deploy PR (with the release notes in the body)

Create the deploy PR without waiting for the VERSION-CONTROL workflow. The key is to **create it with the release notes file from step 5 as the body**. The PR must contain `Summary by CodeRabbit` from the start, or RELEASE-CHANGELOG resets the body.

**6-1. Find an open deploy PR** — read `pr.number` from the output JSON. If it has a value, reuse it (6-2a); if not (`no_pr`), create a new one (6-2b).

```bash
GITHUB_PAT="{PAT}" PYTHONIOENCODING=utf-8 "{PYTHON}" "{SCRIPTS}/changelog_cli.py" \
  deploy-status "{OWNER}" "{REPO}" --base "{BASE_BRANCH}" --head "{HEAD_BRANCH}"
```

**6-2. Update or create with the body** — `NOTES_FILE` must be the same absolute path written in step 5
(home directory + `{OWNER}__{REPO}` prefix → independent of cwd, isolated per repo, and `$HOME` works in Windows Git Bash too).

```bash
NOTES_FILE="$HOME/.projectops/tmp/{OWNER}__{REPO}__release_notes.md"
# For commit provider "leave it", step 5 creates no notes file → pass an empty string for an empty-body PR; the workflow fallback job fills it.
[ -f "$NOTES_FILE" ] || NOTES_FILE=""

# 6-2a. Reuse the existing PR — do not close it (opening a new one re-triggers the workflow and risks a body reset). Update only the body.
GITHUB_PAT="{PAT}" PYTHONIOENCODING=utf-8 "{PYTHON}" "{SCRIPTS}/changelog_cli.py" \
  update-pr "{OWNER}" "{REPO}" {EXISTING_PR} "$NOTES_FILE" && rm -f "$NOTES_FILE"

# 6-2b. New — pass the absolute notes path as body_file to create the PR with a body. Title: "🚀 Deploy {YYYYMMDD}".
# For an app review repo, append --user-approved only when the user saw and approved the notes in this conversation.
GITHUB_PAT="{PAT}" PYTHONIOENCODING=utf-8 "{PYTHON}" "{SCRIPTS}/changelog_cli.py" \
  create-pr "{OWNER}" "{REPO}" "🚀 Deploy $(date '+%Y%m%d')" "$NOTES_FILE" "{HEAD_BRANCH}" "{BASE_BRANCH}" \
  --project-root "{PROJECT_ROOT}" && rm -f "$NOTES_FILE"
# Delete the notes file only on success — on a rejection (needs_user_approval and so on), call again with the same file
```

Run **only one** of 6-2a and 6-2b. Remember `number` from the output JSON as the PR number (step 7 `--pr`). Handle rejection codes
(`needs_user_approval`·`pr_exists`·`nothing_to_deploy`) per the SKILL.md step 6 table. In any other case where there is no `number`,
show "❌ PR create/update failed" with the response JSON and stop.

## Step 7: Verify automerge (deploy-status)

Right after creating the PR, **do not write ad-hoc Python into `/tmp`**; check with this one reusable command. It looks up the PR merge state, the CodeRabbit body, the workflow run and the deploy HEAD at once and returns JSON with a `verdict`. Action per verdict: the SKILL.md table.

```bash
GITHUB_PAT="{PAT}" PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/changelog_cli.py \
  deploy-status "{OWNER}" "{REPO}" --pr "{PR_NUMBER}" --base "{BASE_BRANCH}"
```

> **Do not use sleep when re-checking.** Claude Code Bash blocks `sleep 120`. If you need to wait, set your own pace with `ScheduleWakeup`, and when you wake up, call the `deploy-status` command from the `next` hint again.
>
> **Re-check interval (measured)**: when the PR is created with the release notes in the body, there is no 10-minute CodeRabbit wait, so automerge **usually finishes within 60 seconds** (one cycle of VERSION-CONTROL → CHANGELOG → automerge; measured in #317 and #318, both merged within 60 seconds). So re-check with `ScheduleWakeup(delaySeconds=60)` and repeat every 60 seconds until `merged`. **The minimum `ScheduleWakeup` value is 60 seconds**, so 45 or 30 is clamped to 60 — 60 seconds is effectively the shortest interval. Do not use longer values like 90 seconds; they notice a finished deploy late and waste time. (60 seconds is within the 270-second cache window, so there is no cost penalty.)

## Step 8: Report the result

```
✅ Done!

📋 Summary:
  • push: origin/{HEAD_BRANCH}
  • deploy PR: #NNN
  • release notes: written

The RELEASE-CHANGELOG workflow uses the release notes in the body ("Summary by CodeRabbit" format)
as is, updates CHANGELOG, and then automerges into {BASE_BRANCH}.

Progress: https://github.com/{owner}/{repo}/actions
```
