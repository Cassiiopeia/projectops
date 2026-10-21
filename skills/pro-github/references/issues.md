# Issue read · edit · comments · labels · assignees · helpers

> When to read: when reading or editing issues, handling comments, labels or assignees, or when you need the output format of the issue helpers (title normalization, branch name, commit template, doc path).

Every command has the form `PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py <subcommand> ...`. Replace `{PYTHON}` and `{SCRIPTS}` with the real paths from "Find the scripts" in SKILL.md.
Creating a new issue (write + file) does not use this document; follow the `../../references/issue-creation.md` workflow.

## Read an issue

When the user names a number, as in `#number` or "check issue 427", read that issue. Add `--with-comments` when you need both the body and the comments.

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py get-issue {owner} {repo} {issue_number}
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py get-issue {owner} {repo} {issue_number} --with-comments
```

Output JSON: `{"ok":true,"issue":{number,title,url,state,body,labels,assignees,created_at,updated_at,comments_count},"comments":...,"number","title","url","state","labels","assignees","body","summary","next":null}`. Read labels directly from the top-level `labels` (`--field labels`).

Read several issues at once:

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py get-issues {owner} {repo} 712 707 715
```

If some issues return 404, only those entries come back as `{number,error,code}`; the rest of the lookup continues.

List issues:

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py list-issues {owner} {repo} --state open
# --state open|closed|all (default open)
```

Output JSON: `{"count":N,"issues":[{number,title,url,state,labels}]}`. PRs are excluded. To narrow by label use `--labels "a,b"` (issues that have all of them); to see everything use `--limit 0` (default 50). To narrow by assignee, the agent filters the result itself.

Keyword search (also used for duplicate checks):

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py search-issues {owner} {repo} "{key keywords}"
```

Output JSON `{"count":N,"items":[{number,title,url,state,labels}]}`. Pass the keyword as the last argument as is (spaces allowed); it is URL-encoded internally.

## File an issue (create-issue)

Used in the filing step of the creation workflow:

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py create-issue {owner} {repo} "{title}" "{absolute path of body .md}" "{labels csv}" --assignees "{assignee}" --rename-body-file
# Labels can also be given as --labels "{labels csv}" instead of the positional argument
```

Output JSON: `{"number","url","title","assignees":[...],"branch","commit_template","next","body_file_renamed_to"}`. Labels that do not exist are filtered out automatically (`label_warning`). If there is an `assignee_warning`, the issue was still created; relay only the warning in plain language.

- `--rename-body-file`: if the body file name has the form `YYYYMMDD_NNN_title`, `NNN` is replaced with the real issue number (`20260710_001_title.md` → `20260710_245_title.md`, same folder). The new path is in `body_file_renamed_to`. If the form differs or the name already exists, it is not renamed and you get `rename_warning`. Do not `mv` it by hand.
- `branch` and `commit_template` are the same values as `create-branch-name` and `get-commit-template`; do not call those separately. `next` is: create the branch > `finish-issue --outcome in-progress` (switch to in progress).

## Change issue state (close / reopen)

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py close-issue {owner} {repo} {number}                         # done (default --reason completed)
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py close-issue {owner} {repo} {number} --reason not_planned    # cancelled
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py reopen-issue {owner} {repo} {number}
```

Output JSON: `{"number":...,"url":...,"title":...,"state_reason":"completed"}`.
Done and cancelled handling in the work pipeline (SKILL.md §Finish an issue) needs no confirmation. Otherwise, close or reopen someone else's issue only when the user asks (`../../references/common-rules.md` §Issue state rules).

## Edit an issue

You can change the title, state (open/closed), labels, assignees and body. Pass only the options to change; the rest keep their current values.

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py update-issue {owner} {repo} {issue_number} \
  --title "New title" --labels "status: in progress" --assignees "Cassiiopeia"
# Replace the body with --body-file "{body file path}", --state open|closed
```

The body file can also be given as a positional argument after the number instead of `--body-file` (`update-issue {owner} {repo} {number} "{body file}"`).

> To close, use SKILL.md §Finish an issue (`finish-issue`) instead of `update-issue --state closed`. Never close an issue that still carries an open status label.

## Add / list / edit / delete comments

The body may contain non-ASCII text, emoji and line breaks, so **save the comment body to a file** and pass the path.

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py add-comment {owner} {repo} {issue_number} "{comment body file path}"
# --body-file "{comment body file path}" also works (same shape as update-issue)
```

Edit and delete target the **comment ID (comment_id)**, not the issue number (shared by issues and PRs). Get the comment ID from `list-comments` or the `id` in an earlier `add-comment` response.

```bash
# List comments (to find the id)
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py list-comments {owner} {repo} {issue_number}
# Edit a comment body (pass the body as a file to keep non-ASCII text and line breaks)
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py edit-comment {owner} {repo} {comment_id} "{new body file path}"
# Delete a comment
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py delete-comment {owner} {repo} {comment_id}
```

`list-comments` returns `{count,comments:[{id,url,author,body,created_at}]}`; pass the `id` as is to `edit-comment` and `delete-comment`. `edit-comment` returns `{id,url}`, `delete-comment` returns `{comment_id,status:"deleted"}`.

## Labels (add / remove / replace all)

To keep existing labels, use `add-labels`/`remove-label`. To replace them wholesale, use `set-labels`.

```bash
# Labels defined in the repo
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py list-labels {owner} {repo}
# Add while keeping existing labels (csv)
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py add-labels {owner} {repo} {issue_number} "priority: urgent"
# Remove one label (others stay; idempotent if absent)
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py remove-label {owner} {repo} {issue_number} "status: todo"
# Replace all labels (empty string removes all). Every label not in the list is removed, including type: and area:
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py set-labels {owner} {repo} {issue_number} "type: bug,status: in progress"
```

> To change only the status label, use `finish-issue --outcome done|cancelled|in-progress`, not `set-labels` (non-status labels stay). In a `set-labels` response, `removed` lists removed labels and `warning` means non-status labels were removed. If that was unintended, restore them with `add-labels` from `next`.

Status labels exist in both English standard and Korean form: `status: todo` (`작업전`) · `status: in progress` (`작업중`) · `status: needs review` (`담당자확인`) · `status: feedback` (`피드백`) · `status: done` (`작업완료`) · `status: on hold` (`보류`) · `status: cancelled` (`취소`), plus `priority: urgent` (`긴급`) · `documentation` (`문서`). Whichever form you pass, the CLI maps it to the one the repo has (#776).

`add-labels` ignores labels the repo does not have and reports them as `label_warning`. `remove-label` returns `code:"label_not_present"` (no change) if the issue did not have that label. Korean labels are URL-encoded and work normally.

## Assignees (add / remove)

Assignees are also handled while keeping existing ones. To replace them all, use `update-issue --assignees` (full replace).

```bash
# Add while keeping existing assignees (csv, up to 10)
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py add-assignees {owner} {repo} {issue_number} "Cassiiopeia"
# Remove only the named assignees (others stay)
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py remove-assignees {owner} {repo} {issue_number} "Cassiiopeia"
```

Output JSON: `{"number":...,"url":...,"assignees":[...]}`. GitHub silently drops users without permission or who are not collaborators, so `add-assignees` reports them as `assignee_warning`.

## Issue helpers (title normalization / branch name / commit template / doc path)

Pure computation helpers used by the issue creation workflow and commit message assembly (no API calls):

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py normalize-title "❗[Bug] Login button does not respond!"
# → {"normalized":"Bug_Login_button_does_not_respond", ...}   Hyphens become _ (pro-launch → pro_launch). Korean titles work too ("❗[버그] 한글 제목!" → "버그_한글_제목")
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py create-branch-name "Login button does not respond" 235 --date 20260710
# → {"branch":"20260710_#235_Login_button_does_not_respond","issue_number":235, ...}   Like other commands, {owner} {repo} "issue title" 235 also works
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py get-commit-template "❗[Bug][Skills] Login button does not respond" "https://github.com/o/r/issues/235" --repo-root "{PROJECT_ROOT}"
# → {"template":"...{description}...","source":"...","warnings":[]}   The format follows team and personal settings (with the team format: "Login button does not respond : fix : {description} https://..."). The type is inferred from the title tag (bug → fix, feature → feat)
#   Always name the repo whose format to use with --repo-root (without it, the git root of the cwd). --scope S fills the {scope} placeholder. Tell the user about any warnings
#   Pass --type fix|docs|chore etc. only when the tag and the actual work differ
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py get-output-path issue --title "❗[Bug][Skills] Login button does not respond"
# → {"path":".../issue/20260710_001_Login_button_does_not_respond.md", ...}   Save path for the issue doc (serial number before filing)
```

- Use the commit template `template` value as is. Do not rewrite the type to `feat`; in a `semver_auto` repo a bug fix would then bump the minor version.
- Do not build the issue doc path yourself; use `path` from `get-output-path issue` (the output root can change with settings). It is computed from the current repo, so call it from the project root.
