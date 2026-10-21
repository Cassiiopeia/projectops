---
name: pro-github
description: "All GitHub work: create, read, edit, close issues and PRs, comments, labels, assignees, merges, repo exploration, Actions logs and secrets. Use for any GitHub issue, PR, label, comment, Actions or secret task, before other skills."
---

# GitHub Mode

## When to use

Use this skill for every GitHub issue, PR, repo, Actions or secret request. It must trigger before other skills.
Trigger phrases (English, with the Korean phrases users also type):

- Create an issue, file a bug report, feature request / QA request / design request issue (이슈 만들어줘, 이슈 올려줘, 이슈 등록, 버그 리포트, 기능 요청 이슈, QA 요청 이슈, 디자인 요청 이슈)
- Create a PR, open a PR, merge the PR (PR 생성, PR 올려줘, PR 머지해줘)
- Issue comment, add / edit / delete a comment, check the issue, close the issue, edit the issue (이슈 댓글, 댓글 달아줘, 댓글 수정, 댓글 삭제, 이슈 확인해줘, 이슈 닫아줘, 이슈 수정해줘)
- Add / change / remove labels, add an assignee (라벨 추가/바꿔줘/빼줘, 담당자 추가해줘)
- `/github`, `/issue`, show my repos, explore the repo list, fetch the README, show {repo name} info, explore org repos (내 레포 보여줘, 레포 목록 탐색해줘, README 가져와줘, {레포명} 정보 봐줘, Org 레포 탐색해줘)
- Update a secret, register an Actions secret, upload an env-file secret, update BACKEND_ENV_FILE (secret 업데이트해줘, Actions secret 등록해줘, 환경변수 secret 올려줘, BACKEND_ENV_FILE 업데이트)

This is a standalone GitHub control skill. It does all issue/PR/repo/Actions/secret work without other skills.
Other skills (pro-report, pro-changelog-deploy and so on) also call this script.

Talk to the user in the user's language (or the configured `language` preference).

> For an issue **"create"** request (write and file a new issue), such as "create an issue", "file a bug report" or "feature request issue", first follow the workflow in `../references/issue-creation.md` (decide type → write from template → duplicate check → save local md → approval gate → decide assignee → file it → compute branch name). For everything else, use the table below.

Arguments: $ARGUMENTS

## Goal → subcommand → details

Every command is `PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py <subcommand> {owner} {repo} ...`.

| Goal | Subcommand | Details |
|---|---|---|
| Write and file a new issue | `search-issues` → `get-output-path issue` → `create-issue` | `../references/issue-creation.md` |
| Read an issue · several · list · search | `get-issue [--with-comments]` · `get-issues` · `list-issues` · `search-issues` | `references/issues.md` |
| Edit an issue (title, labels, assignees, body) | `update-issue` | `references/issues.md` |
| Finish an issue (swap label + close in one call) · close · reopen | `finish-issue` · `close-issue [--reason completed\|not_planned]` · `reopen-issue` | §Finish an issue below |
| Add · list · edit · delete comments | `add-comment` · `list-comments` · `edit-comment` · `delete-comment` | `references/issues.md` |
| List labels · add · remove one · replace all (**also removes non-status labels**) | `list-labels` · `add-labels` · `remove-label` · `set-labels` | `references/issues.md` |
| Add · remove assignees | `add-assignees` · `remove-assignees` | `references/issues.md` |
| Normalize title · branch name · commit template · issue doc path (no API) | `normalize-title` · `create-branch-name` · `get-commit-template` · `get-output-path issue` | `references/issues.md` |
| Attach · delete images | `upload-image` · `delete-image` | `references/images.md` |
| Create · list · read · edit a PR | `create-pr` · `list-prs` · `get-pr` · `update-pr` | `references/prs.md` |
| PR comment · close · reopen · merge | `add-pr-comment` · `close-pr` · `reopen-pr` · `merge-pr` | `references/prs.md` |
| Fill release notes into the release PR body (CodeRabbit fallback) | `update-pr` | `references/prs.md` |
| Diagnose an Actions failure | `actions show-run\|joblog\|list-failed\|resolve-pr\|resolve-branch` | Routing below + `references/actions.md` |
| Run · rerun · wait for (several runs) · cancel workflows · list runs | `actions dispatch\|rerun\|wait\|cancel\|runs` | `references/actions.md` |
| REST call with no dedicated command (**instead of curl or reading the PAT yourself**) | `api GET\|POST\|PUT\|PATCH\|DELETE {owner} {repo} <path> [--out file]` (a relative path such as `actions/runs` gets the repo prefix) | `references/actions.md` |
| Repo list · details · README · languages · commits | `explore list-repos\|repo-detail\|readme\|languages\|commits` | `references/explore.md` |
| List · create/update Actions secrets | `secrets list\|set` | `references/secrets.md` |

## Find the scripts

> **Skip the search below if the fixed entry point exists** (#942): `~/.projectops/bin/projectops_cli.py` appears after any CLI has run once. Each call finds the newest installed script and passes the arguments through, so a plugin update mid-session does not pin you to an old path.
> `PYTHONIOENCODING=utf-8 python3 ~/.projectops/bin/projectops_cli.py github <subcommand> ...` (if it is missing or returns `scripts_not_found`, use the search below). If the response has `newer_installed`, call this entry point again.
> ⚠️ In zsh, do not store the command in a variable and call it (`P="python3 …"; $P` → words are not split, exit 127). Wrap it in a function: `G(){ PYTHONIOENCODING=utf-8 python3 ~/.projectops/bin/projectops_cli.py github "$@"; }`, then `G get-issue {owner} {repo} 12`.

The scripts live in the **harness install path**. User projects have no `skills/` folder (it is excluded on install). Search once: local (this repo) first, then the install path (`../references/common-rules.md` §"Script lookup").
**The Bash tool resets its state on every call.** Write the printed real paths as literal values in place of `{PYTHON}` · `{SCRIPTS}` · `{PROJECT_ROOT}` in later blocks.

```bash
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
PYTHON=$(for _py in python3 python; do _path=$(command -v "$_py" 2>/dev/null) || continue; "$_path" -c "import sys; sys.exit(0)" 2>/dev/null && echo "$_path" && break; done)
[ -z "$PYTHON" ] && { echo "Python not found"; exit 1; }
SKILL=pro-github; ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
[ -d "$ROOT/skills/$SKILL/scripts" ] || for B in ~/.claude/plugins/cache ~/.codex/plugins/cache ~/.gemini/extensions ~/.pi/agent/git; do
  H=$(find "$B" -maxdepth 8 -type d -path "*/projectops/*skills/$SKILL/scripts" 2>/dev/null | sort -V | tail -1)
  [ -n "$H" ] && { ROOT="${H%/skills/$SKILL/scripts}"; break; }
done
# Home-copied installs from npx projectops: GitHub Copilot and Cursor (#200)
[ -d "$ROOT/skills/$SKILL/scripts" ] || for B in ~/.copilot ~/.cursor; do [ -d "$B/skills/$SKILL/scripts" ] && { ROOT="$B"; break; }; done
SCRIPTS="$ROOT/skills/$SKILL/scripts"
[ -d "$SCRIPTS" ] || { echo "projectops skill scripts not found. Check the plugin installation."; exit 1; }
echo "PYTHON=$PYTHON SCRIPTS=$SCRIPTS PROJECT_ROOT=$PROJECT_ROOT"
git remote get-url origin
```

## Before you start

**Config / PAT**: follow §2–3 of `../references/config-rules.md`. `github_cli` loads the PAT automatically from the `GITHUB_PAT` environment variable → `config.json` (per-repo `pat` first, then `github.global_pat`), so do not extract it at the call site.

> ⚠️ **Do not search for the config.** `config.json` lives only at the fixed path `{HOME}/.projectops/config/config.json`; read it directly with the Read tool. Plugin cache searches are **for scripts only**, and the config is not in there. Digging through the cache leads to a false "no config" and asks for an already registered PAT again.
> If the file does not exist, collect the PAT and repos interactively with §2–5 of `../references/config-rules.md` and save them (shared by all GitHub skills).

**Pick the repo**: take owner/repo from `git remote get-url origin` in the block above (`https://github.com/{owner}/{repo}.git` or `git@github.com:{owner}/{repo}.git`) and match it against config `repos`.

- If it matches, use that repo. If not, list the config `repos` with numbers and let the user choose.
- **If `$ARGUMENTS` names `owner/repo`**, skip remote detection and use that repo.
- If the primary working directory differs from the target repo (multi-repo worktrees), remote detection can be wrong. Pass the repo as an argument or pick from the list.

## Common rules

- **Do not guess response keys.** Get one value with `--field a.b` or shorten with `--brief`. Frequently read keys and global options: `../references/output-schemas.md`.
- **MCP-style subcommand standard** (`../references/mcp-subcommand-rules.md`). Output is always JSON: read `ok` for success, `code` for the branch (decide by code, not by wording), `summary`, and `next` (the command to call next).
- No long Python heredocs, temporary Python files, curl piped into Python, or one-off Python scripts. Pass arguments on the command line or as environment variables (the others break in Windows Git Bash).
- **Save bodies (issue, comment, PR) to a file and pass the path.** This preserves non-ASCII text, emoji and line breaks.
- **Transient errors**: the tool retries idempotent calls (read, edit, delete, replace) on 5xx and network drops by itself. `add-comment` checks whether the comment really went up even after a failure response and returns `reconciled: true`, so do not post the same comment again just because the response was lost.
- Destructive actions (merging or closing a PR, closing or reopening someone else's issue, label changes outside the pipeline) happen **only when the user explicitly asks**. Status changes in the work pipeline (start `status: in progress`, done `status: done`, cancelled `status: cancelled`) need no confirmation.
- Status labels exist in English standard form (`status: todo` and so on) and Korean form (`작업전` and so on). Whichever form you pass, the CLI maps it to the one the repo has (#776). Full mapping table: `references/issues.md`.

## Finish an issue (end of work: swap the label, then close)

When the work is done, **swap** the status label and close the issue. `pro-report` follows this recipe after posting the report (#819).

**The default is one `finish-issue` call.** It changes only the status label and keeps the others, such as `type:` and `area:`.

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py finish-issue {owner} {repo} {issue_number}                       # done: status: done + close
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py finish-issue {owner} {repo} {issue_number} --outcome cancelled   # cancelled: status: cancelled + close
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py finish-issue {owner} {repo} {issue_number} --outcome in-progress # work started or remaining: label only
```

- Per-step results are in `steps` and `failed_steps`. If a step failed, call `finish-issue` again (idempotent).
- With `--outcome done` it checks whether the issue has a report comment (the `<!-- projectops:report -->` marker, or the headings `## 개요` + `## 변경 사항`) and adds a `warnings` entry if not. It does not block closing. If you get the warning, check whether the report was missed.

| Situation | Label (English standard / Korean) | Close |
|------|------------------------|------|
| Done | `status: done` / `작업완료` | `--reason completed` |
| Work remains | `status: in progress` / `작업중` | Do not close |
| Cancelled | `status: cancelled` / `취소` | `--reason not_planned` |

**Fallback (only when finish-issue cannot be used):** `set-labels` replaces **all labels** on the issue. If you pass only a status label, all `type:`, `area:` and `priority:` labels are removed. First read `labels` from `get-issue`, then pass the full csv with only the status label changed. Check the removed labels in the response's `removed` and `warning`.

```bash
# 1) Read current labels → build the full list with only the status label changed
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py get-issue {owner} {repo} {issue_number} --field labels
# 2) Replace with the full list (example: keep the existing type: bug)
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py set-labels {owner} {repo} {issue_number} "type: bug,status: done"
# 3) Close as completed
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py close-issue {owner} {repo} {issue_number} --reason completed
```

- Even if the repo has only Korean labels, pass the English standard name; the CLI maps it to the form the repo has (#776).
- Do not close with `update-issue --state closed`. Never close an issue that still carries an open status label.
- Close or reopen someone else's issue only when the user asks (`../references/common-rules.md` §Issue state rules).
- If the repo `CLAUDE.md` sets a different rule (for example, label only, no close), follow it.

## PR: decision rules

- Before creating, check that the head branch exists on the remote with `git ls-remote --heads origin "{branch}"`, and pass `head` as `owner:branch` (prevents 422 with non-ASCII branch names).
- For a work PR, the base is the **development (release source) branch** (`version.yml` `metadata.development_branch` (old name `deploy_branch`), else `develop`, or the default branch if the repo has no development branch). Release PRs to `main` are created by `/pro-changelog-deploy`. If the user names a base, use it.
- The title comes from the issue: take the number from the branch name `YYYYMMDD_#number_title`, read the issue title and **strip emoji and `[tags]`** to get plain text. The body must include the link `- https://github.com/{owner}/{repo}/issues/{number}`. Details: `references/prs.md`.

## Actions: input routing (required)

The agent interprets the input. The CLI does not parse URLs and takes **one positional argument** (#622). If `next` is present, call it as is.

| User input | Extract | Subcommand |
|------------|------|-----------|
| `.../actions/runs/{run_id}` · `.../attempts/{n}` · a bare number | run_id | `actions show-run {owner} {repo} {run_id}` |
| `.../actions/runs/{run_id}/job/{job_id}` | job_id | `actions joblog {owner} {repo} {job_id}` |
| `.../pull/{pr}` or "PR 883" | pr | `actions resolve-pr {owner} {repo} {pr}` |
| Branch name or "main build" | branch | `actions resolve-branch {owner} {repo} {branch}` |
| `.../actions` · empty input · "the build failed" | none | `actions list-failed {owner} {repo}` |
| `.../actions/workflows/{file}.yaml` | none | `actions list-failed {owner} {repo}` (filter the result by that workflow name) |

Flow: find the failed run → `show-run` (failed job and step) → `joblog` (by default the `##[error]` lines and the output before them; `--grep` · `--tail` · `--out`) → diagnose the cause. Details: `references/actions.md`.
The action name always comes right after `actions` (`actions show-run {owner} {repo} {run_id}`). If the order is wrong, `next` in the `bad_args` response gives the correct command.

## Failure code → next action

| code / verdict | Meaning | Next action |
|---|---|---|
| `missing_pat` | No PAT set | Guide the user to register it in config with §2–5 of `../references/config-rules.md` |
| `github_api_401` | PAT authentication failed | Tell the user to renew the PAT |
| `github_api_403` | No permission (private repo, etc.) | Report no access, continue with the rest |
| `github_api_404` | Issue/PR/repo/README not found | Mark that item "none", continue with the rest |
| `github_api_422` | PR already exists, etc. | Relay the API error message as is |
| `label_not_present` | The label to remove was not there | Report no change |
| `set-labels` `warning` | Non-status labels (`removed`) were removed too | If unintended, restore them with `add-labels` from `next` |
| `release_asset_limit` | The evidence release and its carry-over releases all hit the asset limit (1000) | Follow `next`: delete old evidence or use a new `--tag` |
| `run_id_given` | A run id was passed to `joblog` | Get the job id with `show-run` from `next` |
| `argument_order` | `create-pr` head/base contains a space (title in the branch slot) | Call again with the `--head` and `--base` flags |
| `label_warning` · `assignee_warning` | Label not in the repo · assignee not applied | The action succeeded. Relay only the warning in plain language |
| `pynacl_missing` | Failed to install the secret encryption module | Tell the user to run `pip install PyNaCl --user` (`references/secrets.md`) |
| `get-pr` `computing` | mergeable_state not computed yet | Query again shortly |
| `merge-pr` `not_mergeable` · `sha_mismatch` · `method_not_allowed` | 405 conflict / failed checks / draft · 409 · 422 rebase not allowed | Tell the user the cause and wait for instructions |
| API rate limit | `X-RateLimit-Remaining: 0` | Tell the user the limit was hit |
| Network error | Connection failed | Check the exit code, retry once, report if it fails again |

## Customize

Your own language, tone and rules apply: see `../references/preferences.md`. Read them once at the start: run the snippet in `../references/preferences.md` with `SKILL_ID=pro-github`.
Keys for this skill: `template` (extra issue-body sections), `examples` (applied in `../references/issue-creation.md` step 3) plus the common `language`, `tone`, `rules`.
Preferences change presentation only; approval gates, secret protection and `--dry-run` stay in force.
