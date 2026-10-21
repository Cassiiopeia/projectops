---
name: pro-changelog-deploy
description: "Release flow: push develop, open the deploy PR to main with release notes in the body so automerge proceeds, and re-trigger by reopening the PR if automerge fails. Use for 'deploy', 'deploy PR', 'changelogfix'."
---

# Changelog Deploy Mode

## When to use

- 'deploy', 'deploy it', 'open the deploy PR', 'changelogfix', 'the deploy PR did not merge', 'reopen the PR'
- Korean triggers: 'deploy해줘', '배포해줘', 'deploy PR 올려줘', 'changelogfix', 'deploy 머지 안 됐어', 'PR 다시 열어줘'
- For a repo whose release goes straight into App Store / Play Store review (app review aware), show a review warning banner on the release notes and apply stricter cleanup.

> **⚠️ Model recommendation**: the main job of this skill is writing release notes. **Run it on a lite (haiku) model.** It only analyzes commits and rewrites them in plain language, so a strong model is not needed.

A projectops-only skill. It works with the `PROJECT-COMMON-RELEASE-CHANGELOG` workflow: detect the release PR → if the body already has release notes, use them as is; otherwise generate them through the provider ladder (AI if a key exists → commit analysis) → finalize the version → update CHANGELOG → automerge. It does not wait for CodeRabbit (#566).

This skill does: push head → write release notes → open the release PR to base **with the notes in the body** → confirm automerge. On failure, fix mode closes the existing PR and re-triggers with a new PR. The notes use the `Summary by CodeRabbit` format. Only the format name says CodeRabbit; no bot is needed. The workflow respects that body and parses it and automerges right away.

Arguments: $ARGUMENTS

**Talk to the user in their language** (or the configured `language` preference). The message templates in this skill and its references give the meaning; say them in that language.

## Do not use when

- Ordinary commit or PR work that is not a deploy
- The project has no release head branch on the remote (the development branch fixed in [Before you start §5], standard `develop`). This skill only handles a head → base release PR. The branch name itself is not fixed. **Exception**: if `detect-release-context` returns `release_shape: deploy_branch` (no development branch, `main` → `deploy`), follow its `release_branches` and `release_steps`. Do not use a missing `develop` as head
- The repository has no `PROJECT-COMMON-RELEASE-CHANGELOG` workflow

## Core principles (safety rules — do not change their meaning)

- Never run `git push --force`
- **Never close or open a PR without user confirmation** (fix mode)
- **Show the release-note body to the user before creating the PR** (deploy 5.5 / fix 4.5). Only when auto mode is explicitly configured: show it and proceed at once
- **App review repos (`APP_RELEASE == true`) need approval every time, even in auto mode.** The release goes straight into store review, so a blanket delegation does not apply (#821)
- **Before the release PR, merge the reverse difference base → head first** (deploy 1-1). The release workflow leaves the version commit only on base. Skip this and the next deploy hits a version-file conflict
- **Creating the PR is the last step, after the release notes are written** (see the race note below)
- **Never show config key names or file paths to the user.** For the auto/manual toggle, take a plain-language answer and let the agent update the config
- **Do not hard-code branches (#456).** The source of truth for head/base branches and the provider is **`detect-release-context` (version.yml)** (#842). The config is only a per-repo record for repos without version.yml; branch and provider keys in the global config are not read. `develop`/`main`/`commit` are only fallbacks when no value can be read. Replace `develop`/`main` in the steps below with the resolved values
- **The user never edits the config by hand.** If you can decide, do not ask. Ask in plain language only when it is unclear, record the answer, and never ask again once recorded

## What you want → command → details

Every command is `PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/changelog_cli.py <command>`.

| Goal | Command | Details |
|---|---|---|
| Read release branches, provider, app review signals (no PAT needed) | `detect-release-context --project-root {PROJECT_ROOT}` | `references/config.md` |
| Overall verdict on the deploy PR (merge, body, workflow, HEAD) | `deploy-status {OWNER} {REPO} [--pr N] --base B [--head H]` | verdict table below |
| Create the release PR with the notes in the body | `create-pr {OWNER} {REPO} "{title}" "{notes file}" {HEAD} {BASE} --project-root {PROJECT_ROOT} [--user-approved]` | step 6 below · `references/deploy-steps.md` |
| Update or close an existing PR body | `update-pr {OWNER} {REPO} {N} "{notes file}"` · `update-pr ... "-" --state closed` | `references/deploy-steps.md` · `references/fix-steps.md` |
| List PRs | `list-prs {OWNER} {REPO} --state open` | — |
| Workflow failure logs | `actions show-run\|joblog\|list-failed\|resolve-pr\|resolve-branch {OWNER} {REPO} [arg]` | `../pro-github/references/actions.md` |
| PAT, auto approval, app review, branch resolution and config records | — (Read/Write tools) | `references/config.md` |
| Note-writing rules, fixed structure, approval messages | — | `references/release-notes.md` |

## Before you start

### 1) Scripts · OWNER · REPO · PYTHON · PROJECT_ROOT (once)

> **If the fixed entry point exists, skip the search below** (#942): `~/.projectops/bin/projectops_cli.py` appears after the CLI runs at least once. On every call it finds the newest installed script and passes the arguments through. A plugin update during the session does not pin you to an old path.
> `PYTHONIOENCODING=utf-8 python3 ~/.projectops/bin/projectops_cli.py changelog-deploy <subcommand> ...` (if it is missing or returns `scripts_not_found`, use the search below). If the response has `newer_installed`, call again through this entry point.

> **⚠️ Do not store the command in a variable and call it (zsh).** `P="python3 …/changelog_cli.py"; $P deploy-status …` does not word-split in zsh. The whole command is read as one file name and ends with `exit 127` (command not found). To shorten it, wrap it in a function: `cl() { PYTHONIOENCODING=utf-8 "$PYTHON" "$SCRIPTS/changelog_cli.py" "$@"; }; cl deploy-status …`

**Bash is stateless.** Variables and `export` do not survive between calls. **Remember the values printed below and write the real values into every later block** (in the `{PYTHON}` slots and so on, or redeclare them on the first line of the block, like `OWNER="..."; ...`). Never assume a variable from an earlier call is still alive.

```bash
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
PYTHON=$(for _py in python3 python; do _path=$(command -v "$_py" 2>/dev/null) || continue; "$_path" -c "import sys; sys.exit(0)" 2>/dev/null && echo "$_path" && break; done)
[ -z "$PYTHON" ] && { echo "❌ Python을 찾을 수 없습니다."; exit 1; }
SKILL=pro-changelog-deploy; ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
[ -d "$ROOT/skills/$SKILL/scripts" ] || for B in ~/.claude/plugins/cache ~/.codex/plugins/cache ~/.gemini/extensions ~/.pi/agent/git; do
  H=$(find "$B" -maxdepth 8 -type d -path "*/projectops/*skills/$SKILL/scripts" 2>/dev/null | sort -V | tail -1)
  [ -n "$H" ] && { ROOT="${H%/skills/$SKILL/scripts}"; break; }
done
SCRIPTS="$ROOT/skills/$SKILL/scripts"
[ -d "$SCRIPTS" ] || { echo "projectops 스킬 스크립트를 찾지 못했습니다. 플러그인 설치를 확인하세요."; exit 1; }
REMOTE_URL=$(git remote get-url origin 2>/dev/null || echo "")
OWNER=$(echo "$REMOTE_URL" | sed -E 's|.*github\.com[:/]([^/]+)/.*|\1|')
REPO=$(echo "$REMOTE_URL" | sed -E 's|.*github\.com[:/][^/]+/([^/.]+)(\.git)?$|\1|')
echo "PROJECT_ROOT=$PROJECT_ROOT PYTHON=$PYTHON SCRIPTS=$SCRIPTS OWNER=$OWNER REPO=$REPO"
PYTHONIOENCODING=utf-8 "$PYTHON" "$SCRIPTS/changelog_cli.py" detect-release-context --project-root "$PROJECT_ROOT"
```

From the `detect-release-context` output, remember `branches` (branches and provider), `branches_source`, `conflict`, `signals` and `hint` (app review signals), and `release_shape`. If `release_shape == deploy_branch` (origin has no development branch but has `deploy`), set `HEAD_BRANCH`/`BASE_BRANCH` from `release_branches` (usually `main` → `deploy`) instead of `branches`, and follow `release_steps`. Confirm this pair with the user once. If it is `standard`, nothing changes. The CLI reads owner/repo from the origin URL and the config from its fixed path on its own (read-only). Only when you look at another repo, pass them explicitly: `detect-release-context --project-root {PROJECT_ROOT} --owner {OWNER} --repo {REPO}`.

### 2)~5) Resolve values from the config — details in `references/config.md`

| § | Value | Rule |
|---|---|---|
| 2 | `PAT` | **Do not read or remember the PAT.** The CLI loads it on its own (opening the config with Read leaves the PAT in the session log). If you get `missing_pat`, tell the user "register the PAT with `/pro-github` first" and stop. When you must read other settings such as auto approval, use only the fixed path `~/.projectops/config/config.json`, and do not copy values out |
| 3 | `AUTO_APPROVE`, `CONFIG_HAS_KEY` | `changelog_deploy.auto_approve`: per repo → global → otherwise `false` (manual). The old key `auto_approve_release_notes` is ignored |
| 4 | `APP_RELEASE` | `changelog_deploy.app_release`: **per repo only** → otherwise `unset` |
| 5 | `HEAD_BRANCH`, `BASE_BRANCH`, `PROVIDER`, `BRANCH_SOURCE` | **Use `branches` from `detect-release-context` as is.** CLI resolution order: version.yml (always, if present) → per-repo config (only without version.yml) → fallback. Global keys are not read. If there is a `conflict`, go with version.yml and say one line about it. Only when `branches_source == fallback` and there is no version.yml, do the first-time resolution (ask if unclear → record in the per-repo config) |

**Provider three-step rule (#821)**: `branches.provider` is the value the CLI already resolved. ① explicit `changelog.provider` in version.yml → ② unset + `.coderabbit.yaml` at the repo root → `coderabbit` → ③ neither → `commit`. The workflow uses the same rule, so the decisions never diverge. `github-ai` (service shut down) comes back from the CLI as `commit`. Never ask about the provider.

## Choosing the mode

- **deploy mode**: "deploy it", "open the deploy PR" (Korean: "deploy해줘", "배포해줘", "PR 올려줘") → start at step 1
- **fix mode**: "it did not merge", "changelogfix", "do it again", "retry the PR" (Korean: "머지 안 됐어", "changelogfix", "다시 해줘", "PR 재시도") → start at fix step 1

## deploy mode — steps and decisions (commands and messages in `references/deploy-steps.md`)

If the preferences have a `template`, use it as the release-note lead-in.

**Step 1 Check commit state** — run `git status --short`, `git fetch origin`, the current branch, `git log origin/{BASE}..HEAD` and `git log origin/{HEAD}..HEAD` **each separately**.
- If the uncommitted changes are **yours** (made in this task), stop and commit them first.
- If they are **someone else's changes whose intent you do not know** (another session), leave them alone, list them for the user and continue. A deploy only pushes commits. But if the 1-1 merge overlaps those files and fails, stop and hand it to the user.
- If the current branch is not `HEAD_BRANCH`, **stop** and tell the user. Do not switch branches on your own (another session may have moved it).
- Only when **both** logs are empty, say "nothing to deploy" and stop. If either has commits, go to 1-1.

**Step 1-1 Bring base up to date (never skip)** — the order is the contract:
1. `git pull --rebase origin {HEAD}` first, to align head with the remote (if you pull --rebase after making a merge commit, the merge gets undone).
   If the working tree has **someone else's uncommitted changes** and pull --rebase is refused, do not stash. Align with `git fetch origin` → `git merge --ff-only origin/{HEAD}` (this works on a dirty tree when no files overlap). If it cannot fast-forward (it diverged from your local commits), stop and ask.
2~3. `PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/changelog_cli.py sync-base --head {HEAD} --base {BASE} --project-root {PROJECT_ROOT}` — fetch > check the reverse difference > merge it if there is one, all in one call.
   On `in_sync` (no difference) or `merged`, go to the next step. On `merge_conflict`, **stop** and agree on the resolution with the user. Do not run `merge --abort`, `reset` or drop one side on your own. On `wrong_branch`, tell the user without switching branches.
   - Before starting, look at `branches_check` from `detect-release-context`: if it has a `warning` (branch missing, 0 commits ahead), the configured head/base pair may differ from this repo's real release flow. Confirm with the user.

**Step 1.5 Release context awareness** — `hint` × `APP_RELEASE`:

| Situation | Action |
|------|------|
| `hint == backend_only` | **Pass silently.** No warning, no question, and do not touch the config |
| App review detected (`strong_app`/`app_release_likely`/`unknown`) **AND** `APP_RELEASE == unset` | Show the confirmation message **once** and save the answer in the config (`config.md` §4) |
| `APP_RELEASE == true` | Do not ask. Apply the review warning banner and strict cleanup in steps 5 and 5.5 |
| `APP_RELEASE == false` | Do not ask; continue without a warning |

**Step 2 Confirm before push** — show the list of commits to push and get approval.
**Step 3 Push** — `git push origin {HEAD}`. Do not pull --rebase again here (it undoes the 1-1 merge). On non-fast-forward, **never force push**: run `git pull --rebase=merges origin {HEAD}` and push again (if someone else's uncommitted changes block it, stop and ask — no stash). The version does not change here (the release PR finalizes it).

> **⚠️ Step order (prevents a race condition — always follow it)**
> RELEASE-CHANGELOG checks the body when the deploy PR is `opened`. If there is **no** `Summary by CodeRabbit`, it **resets the body**. If you create the PR with an empty body first, the workflow cuts in and the notes disappear. So the order is **commit analysis (4) → write notes (5) → approval (5.5) → create the PR with the notes in the body (6)**, with PR creation last. (Do not change the workflow logic.)

**Step 4 Commit analysis** — `git log origin/{BASE}..origin/{HEAD}` (based on `origin/{HEAD}`, not HEAD — workflows such as the README version update can put the remote ahead). Classification and rewrite rules: `references/release-notes.md`.

**Step 5 Write the release notes** — branch on `PROVIDER`:

| PROVIDER | This step | Step 5.5 |
|----------|---------|---------|
| `copilot`·`openai`·`gemini`·`claude`·`groq`·`mistral`·`ollama`·`coderabbit` | The skill **writes the notes up front**. The workflow respects the body, so it does not call a generator | enter |
| `commit` (default) | **Ask once**: "Should I polish the release notes, or leave them to automatic generation from the commit history?" → **polish**: write them up front; **leave it**: go to step 6 without a notes file (empty-body PR — the workflow fallback job fills it from commit analysis) | polish = enter / leave it = skip |

Writing up front is safe whatever the provider: the workflow respects a `Summary by CodeRabbit` that the skill put in first (`already_found`), regardless of provider. The only exception is `commit` "leave it".
Write the notes to `~/.projectops/tmp/{OWNER}__{REPO}__release_notes.md` with the skeleton below (create the tmp folder first if it does not exist). You may omit the marker comments and the `## Summary by CodeRabbit` header; `create-pr`/`update-pr` add them when missing. Use only these five category names and delete empty categories. Open `references/release-notes.md` only when you need good/bad examples or the approval messages.

The headings below are the `ko` names from the release-note catalog (`.github/scripts/i18n/ko.json`), which the release workflow also uses. If the repo's `version.yml` sets `options.language: en`, use the `en` names instead: `Release notes` / `New features` / `Bug fixes` / `Improvements` / `Documentation` / `Other`.

```
## 릴리스 노트

* **새 기능**
  * (feat — a change the user can feel, one line, 40 characters or fewer)

* **버그 수정**
  * (fix)

* **개선**
  * (refactor·perf·style)

* **문서**
  * (docs)

* **기타**
  * (the rest)
```

Rewrite rules: do not copy commit messages. Drop file, class and function names, prefixes like `feat:`, issue numbers and URLs, and internal details such as libraries and APIs. Write one line from the user's point of view. If `APP_RELEASE == true`, drop internal, CI/CD, test and build items entirely (the notes become the store release notes).
**After step 5 — per-language store translation drafts** — right after writing the notes file, Read `metadata.template.options.store_locales` in `version.yml`. **If there are two or more languages**, read `references/store-translations.md` and append translation drafts to the end of the notes file (translate them yourself, without calling an external AI). If the key is missing or has one language, this step does not exist.
> **⚠️ AGENT MUST READ: after creating the notes file, always run through step 6 (PR creation). But do not jump there directly; go through step 5.5 first.**

**Step 5.5 Approval gate** (messages in `references/release-notes.md`):
- **🔒 If `APP_RELEASE == true`, use B (manual) regardless of `AUTO_APPROVE`.** Print the **review warning banner** above the body first and do not show C. Even for "leave it", ask right before step 6: "Leave the notes to automatic generation and create a deploy PR that leads into app review?"
- commit "leave it" (not app review) → skip 5.5 and go to step 6.
- **A. Auto** (`AUTO_APPROVE == true` AND `APP_RELEASE != true`) — only show the notes and go straight to step 6. If the user says "ask me first" ("확인받게 해줘"), update the config **before** step 6 and switch to B.
- **B. Manual** (`AUTO_APPROVE == false` OR `APP_RELEASE == true`) — show the notes and get approval. On an edit request, rewrite the notes and go back to the start of 5.5 (loop until approved).
- **C. First-run automation offer** — only when B was approved + `CONFIG_HAS_KEY == false` + `APP_RELEASE != true`, once, right before step 6.

**Step 6 Create the deploy PR** — first look for an open deploy PR with `deploy-status --head`. **If one exists, do not close it; reuse it** and update only the body with `update-pr` (opening a new one re-triggers the workflow and risks a body reset). If none exists, pass the absolute path of the notes file to `create-pr` as the body (an empty string for "leave it"). Delete the notes file when done.
Always pass `--project-root {PROJECT_ROOT}` to `create-pr`. Action per rejection code:

| code | Meaning | Action |
|---|---|---|
| `needs_user_approval` | There are app review signals and the app review record is not "regular deploy" | Show the review warning banner + the notes body and get approval. **Only when the user actually approved in this conversation**, rerun the same command with `--user-approved`. Never add it without approval or report "approved" when it was not |
| `pr_exists` | An open PR for the same head → base already exists (`number`·`url`) | Do not create a new one. To change the notes, `update-pr {N}`; otherwise follow `next` (`deploy-status --pr N`) |
| `nothing_to_deploy` | No commits ahead of base | Do not create the PR; tell the user. Check whether it was pushed and the branch pair (`branches_check`) |
| `body_file_not_found` | The notes file path is wrong | Retry with the absolute path written in step 5 |

**Step 7 Verify automerge** — decide with a single `deploy-status --pr {N} --base {BASE}` (no ad-hoc Python in `/tmp`). See the verdict table below.

**Step 8 Report the result** — push target, PR number, whether notes were written, Actions link.

## deploy-status verdict → next action

| verdict | Meaning | Action |
|---------|------|------|
| `merged` | automerge done | Report the result, then **wrap up**: for each issue in the release (issue URLs in the PR commit messages), post a report comment with `pro-report` → mark it done with `pro-github finish-issue`. Do not end without this step |
| `waiting_for_workflow` | The RELEASE-CHANGELOG run is queued or in_progress, or it has not started yet (right after PR creation, or the repo queue is delayed) | **Do not close or reopen the PR** (reopening does not clear a queue delay; it only stacks another run). Wait as `next` says with `deploy-status --pr N --wait 540`. This verdict never turns into `stuck` |
| `waiting_for_automerge` | The workflow finished and automerge is pending | **No sleep.** Wait inside the tool with `deploy-status --pr N --wait 540` (it returns as soon as it is done, `waited_seconds`). If the verdict is still this, use ScheduleWakeup and check again. After 10 minutes the tool switches to `stuck` on its own |
| `stuck` | No automerge for over 10 minutes (`stuck_reason`: `no_workflow_on_head` = no RELEASE run for this PR on the head branch and the queue is empty · `workflow_done_not_merged` = the workflow finished but nothing merged) | Stop waiting. Tell the user, and **after confirmation**, close and recreate the PR in fix mode |
| `missing_coderabbit_summary` | The workflow finished but the body has no `Summary by CodeRabbit` | **Do not go to fix mode right away and do not run `update-pr` right away.** Check again with `deploy-status` after 60 seconds, and suggest fix mode **only when the same verdict comes twice in a row**. After one occurrence, assume a race first (#331 — a real, repeated incident where the body vanished when it overlapped the workflow's PATCH) |
| `workflow_failed` | The latest RELEASE run for this PR failed (if `workflow.is_current_head == false`, it is a run for an old head SHA from before the push) | Share `workflow.run_url` + rerun through fix mode |
| `conflict` | Merge conflict (dirty) | Explain the conflict and ask for a manual check |
| `behind` | Behind base | Merge base into head with `sync-base` and push |
| `blocked` | The merge is blocked (waiting on required checks, reviews or protection rules) | Check on the PR page what blocks it and tell the user |
| `no_pr` | No open deploy PR | Check with `deploy_branch.head_sha` whether it already merged, then report |

## fix mode — steps and decisions (commands and messages in `references/fix-steps.md`)

1. **Check state** — `deploy-status --base {BASE}` (without `--pr` it finds the open deploy PR on its own). `no_pr` → go to step 3 / `merged` → report and stop / otherwise → remember `pr.number` as `EXISTING_PR` and go to step 2.
2. **Close the existing PR** — **only after the user confirms**, `update-pr ... "-" --state closed`.
3. **Commit analysis** — same as deploy step 4. If you entered fix mode directly and `APP_RELEASE == unset`, run deploy step 1.5 once before this step.
4. **Write the notes** — same location and structure as deploy step 5 (including per-language store translation drafts — `references/store-translations.md`). Do not jump straight to step 5.
4.5. **Approval gate** — **exactly the same** branches as deploy step 5.5 (A/B/C; for app review, banner + manual approval).
5. **Create the new PR** — `create-pr` with the notes in the body (title `🚀 Deploy {YYYYMMDD} (재시도)`, where `재시도` means "retry"). In fix mode too, **creating the PR is the last step**.
6. **Report the result**, then verify with `deploy-status --pr`.

## Notes

- **Always verify with `deploy-status` after creating or retrying a PR.** Do not write ad-hoc status-check Python into `/tmp`.
- **Create the PR with the notes in the body.** If you create it empty and fill it later, the race condition wipes the notes.
- **Do not skip the approval gate.** Only when auto mode is explicitly configured, show and proceed; app review repos need approval even in auto mode. Speak in plain language only and never surface config keys or paths.
- The only criteria for moving to fix mode are in the verdict table above (`missing_coderabbit_summary` twice in a row · `workflow_failed` · `waiting_for_automerge` over 10 minutes = `stuck`). `waiting_for_workflow` (queue delay) is not one of them — do not close and reopen.
- If a deploy PR already exists, reuse it instead of closing it.
- **curl exit 35 (SSL error) on a Windows internal network**: add `--ssl-no-revoke` to curl calls (`../references/common-rules.md`, Windows internal network section).

## Customize

Your own language, tone and rules apply: see `../references/preferences.md`. Read them once at the start: run the snippet in `../references/preferences.md` with `SKILL_ID=pro-changelog-deploy`.
Keys for this skill: `template` (release-note lead-in) plus the common `language`, `tone`, `rules`.
Preferences change presentation only; approval gates, secret protection and `--dry-run` stay in force.
