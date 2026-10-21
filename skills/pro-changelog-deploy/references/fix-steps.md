# fix mode — commands and messages per step

> When to read: when automerge failed and you close the existing deploy PR and open a new one to re-trigger ("it did not merge", "changelogfix", "do it again", "retry the PR"; Korean: "머지 안 됐어", "changelogfix", "다시 해줘", "PR 재시도"). The step order and safety rules are in SKILL.md. Show the messages below in the user's language (or the configured `language` preference).

**Bash is stateless.** Write the **real values** obtained in [Before you start] into `{PAT}` · `{OWNER}` · `{REPO}` · `{PYTHON}` · `{SCRIPTS}` · `{HEAD_BRANCH}` · `{BASE_BRANCH}` (branches are the values resolved in [Before you start §5], fallback develop/main).

## fix step 1: Check the current deploy PR state (deploy-status)

Instead of ad-hoc curl parsing, query everything with `deploy-status`. Without `--pr` it finds the open deploy PR on its own.

```bash
GITHUB_PAT="{PAT}" PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/changelog_cli.py \
  deploy-status "{OWNER}" "{REPO}" --base "{BASE_BRANCH}"
```

Branch on `verdict`:

- `no_pr` → no open PR. Go to fix step 3 (prepare a new PR)
- `merged` → already merged. No retry needed; report, then follow `next` for the per-issue report and completion
- `waiting_for_workflow` → the workflow is queued or running. **Do not close it**; wait with `--wait` from `next`
- anything else (`waiting_for_automerge`/`missing_coderabbit_summary`/`workflow_failed`/`conflict`) → remember `pr.number` as `EXISTING_PR` and go to fix step 2

## fix step 2: Close the existing PR (after user confirmation)

```
There is an open deploy PR #NNN.
Close it and open a new one to re-trigger the workflow?

1. Yes, close it and create a new one
2. Cancel
```

After confirmation, run:

```bash
GITHUB_PAT="{PAT}" PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/changelog_cli.py \
  update-pr "{OWNER}" "{REPO}" "{EXISTING_PR}" "-" --state closed
```

## fix step 3: Commit analysis

> If you entered fix mode directly and `APP_RELEASE == unset`, run the signal collection and confirmation of deploy step 1.5 (`deploy-steps.md`) once **before** this step to set the value.

```bash
git fetch origin "{BASE_BRANCH}" "{HEAD_BRANCH}" 2>/dev/null || true
# The analysis base is origin/{HEAD_BRANCH} (same reason as deploy step 4 — HEAD may be behind origin/{HEAD_BRANCH}).
git log "origin/{BASE_BRANCH}..origin/{HEAD_BRANCH}" --pretty=format:"%s" | grep -v "\[skip ci\]" | head -60
```

Classify and rewrite with **exactly the same rules** as deploy steps 4 and 5 (`release-notes.md`). Like app store update notes: no file names, technical prefixes, implementation details, issue numbers or URLs; only changes the user feels directly, 40 characters or fewer.

## fix step 4: Write the release notes

Write with **the same location, file name rule and fixed structure** as deploy step 5 (including `Summary by CodeRabbit`): `~/.projectops/tmp/{OWNER}__{REPO}__release_notes.md`; create the tmp folder first if it does not exist (`release-notes.md`).

> **⚠️ AGENT MUST READ: after creating the notes file, do not jump straight to fix step 5 (PR creation); go through fix step 4.5 (approval gate) first.**

## fix step 4.5: User approval gate

Use **the same logic and messages** as deploy step 5.5 (`AUTO_APPROVE` / `CONFIG_HAS_KEY` from [Before you start §3] as is).

- If `APP_RELEASE == true`, print the review warning banner above the body first and get **manual approval regardless of `AUTO_APPROVE`**. Fix mode is usually a retry that already went through step 1.5, so the value is already set.
- Auto mode (`AUTO_APPROVE == true` and `APP_RELEASE != true`): only show the body and go straight to fix step 5. If the user says "switch to manual" ("수동으로 바꿔줘"), update the config and switch to the manual branch
- Manual mode (`AUTO_APPROVE == false` or `APP_RELEASE == true`): show the body + approve/edit branch. On an edit request, go back to fix step 4, rewrite, and re-enter fix step 4.5
- First run (`CONFIG_HAS_KEY == false`, `APP_RELEASE != true`): right after manual-mode approval, offer automation once (this repo only / all repos / confirm every time) → update the config per the answer

## fix step 5: Create the new deploy PR (with the release notes in the body)

The PR must be born with `Summary by CodeRabbit`, or the workflow resets the body.

```bash
# Release notes temp file — must be the same absolute path written in fix step 4.
NOTES_FILE="$HOME/.projectops/tmp/{OWNER}__{REPO}__release_notes.md"
# If commit provider "leave it" left no notes file, use an empty string → empty-body PR (the workflow fills it).
[ -f "$NOTES_FILE" ] || NOTES_FILE=""

# Pass the absolute notes path as create-pr's body_file to create the PR with a body (same pattern as deploy 6-2b).
GITHUB_PAT="{PAT}" PYTHONIOENCODING=utf-8 "{PYTHON}" "{SCRIPTS}/changelog_cli.py" \
  create-pr "{OWNER}" "{REPO}" "🚀 Deploy $(date '+%Y%m%d') (재시도)" "$NOTES_FILE" "{HEAD_BRANCH}" "{BASE_BRANCH}" \
  --project-root "{PROJECT_ROOT}" && rm -f "$NOTES_FILE"
# For an app review repo, add --user-approved only after approval (needs_user_approval). On a rejection the notes file stays
```

Read `number` from the output JSON as the new PR number. If it is missing, show "❌ PR creation failed" with the response JSON and stop.
If it is there, verify with `deploy-status --pr {number}` as in deploy step 7.

## fix step 6: Report the result

```
✅ New deploy PR #NNN created!

The workflow uses the release notes in the body as is and proceeds with automerge.
Progress: https://github.com/{owner}/{repo}/actions
```
