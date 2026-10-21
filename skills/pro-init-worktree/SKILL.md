---
name: pro-init-worktree
description: "Create a git worktree from a branch name and copy only the needed local files (found via .gitignore) with reasons. Use for worktree creation, branch-isolated work, or /init-worktree."
---

# Git worktree setup

## When to use

- When you need a worktree, branch-isolated work or an independent work environment, or on `/init-worktree`.
- Typical requests: "create a worktree", "set up a worktree for this branch" (Korean: "워크트리 만들어줘", "worktree 생성해줘").

Take a branch name, **create the git worktree automatically, survey local-file candidates from .gitignore, and copy only the files the worktree needs, each with a reason.**

Talk to the user in the user's language (or the configured `language` preference).

## User input

$ARGUMENTS

## No input

Show the usage:
```
/init-worktree
20260120_#163_Add_a_template_for_Github_Projects
```

## Process

### Step 1: Extract the branch name
- Extract the branch name from the user input (keep it as is, including `#`)
- If there is no branch name, show the usage and stop

### Step 2: Prepare the environment
```bash
# Go to the project root
cd [project_root]

# Git long path support (Windows, once)
git config --global core.longpaths true
```

### Step 3: Create the worktree

Do not write a temporary Python script. Pass the branch name (with `#` and non-ASCII text as is) to `--branch` (script lookup: `../references/common-rules.md` §Standard call pattern, `SKILL=pro-init-worktree`).

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/worktree_cli.py create --root {source_root} --branch "{branch name}" --base origin/develop
```

- **A new branch is cut from `--base`.** Without it, the branch is cut from the currently checked-out HEAD, so calling it on top of another work branch drags in unrelated commits. Name the development branch (`origin/develop` and so on). An existing local or remote branch is used as is, regardless of `--base`.
- `worktree` in the result JSON is the new folder path. If it fails, read the first error in `output_tail`.

### Step 4: Survey and selectively copy gitignored local files

**Read `references/local-files.md` and follow it as written.** The essentials:

- **Recall first**: `{PYTHON} {SCRIPTS}/worktree_cli.py recall --root {source_root}` (script lookup: `../references/common-rules.md` §Standard call pattern, `SKILL=pro-init-worktree`).
  If there is a set from last time, copy `copy_now` as is and **judge only `new_candidates`**. On the first run (`first_time`), judge everything.
- **Do not `cp` the remembered set by hand**: `{PYTHON} {SCRIPTS}/worktree_cli.py copy --root {source_root} --to {worktree_path}` (files that already exist in the target are not touched without `--overwrite`; for newly judged files use `--files a,b`).
- **Record right after copying**: `{PYTHON} {SCRIPTS}/worktree_cli.py record --root {source_root} --copied a,b --skipped c`.
  Pass relative paths only (never file contents or values). If you skip this call, the next worktree makes the same judgment again.
- First build an **inventory of candidates that really exist in the source** from `.gitignore`. Do not copy only file names you happen to recognize.
- Classify each candidate as `copy recommended` / `needs judgment` / `copy not recommended`. If unclear, check whether project files **reference** it and promote it.
  (`.env*` · `application-*.yml` · `key.properties` · `*.jks` · `google-services.json` · `GoogleService-Info.plist` are recommended; caches, IDE files, dependencies and logs are not.)
- Print copied, skipped and missing candidates **all with a reason**. Missing candidates are not treated as failures.

### Step 5: Output the result

```
✅ Worktree created!
📍 Path: [worktree_path]
📋 Copied files:
  ✅ android/app/google-services.json
  ✅ ios/Runner/GoogleService-Info.plist

📝 Commit message template:
{template from get-commit-template, as is}
```

Do not build the commit template yourself. Call `github_cli.py get-issue {owner} {repo} {number}` with the issue number from the branch name
to get the original title and URL, then show the `template` from `github_cli.py get-commit-template "{original title}" "{issue URL}"` as is.
The type is inferred from the title tag (bug → `fix`, feature → `feat`). If you hard-code `feat`, a bug fix bumps the minor version in a `semver_auto` repo.
If the issue cannot be read (no PAT and so on), leave out the template line.

## Branch name rules

- `#`: **kept as is** in the git branch name; converted to `_` only in the folder name
- Special characters: converted to `_` when building the folder name
- Worktree location: the `{project name}-Worktree/` folder (for example `myapp-Worktree`)

## Script location

> **Skip the search below if the fixed entry point exists** (#942): `~/.projectops/bin/projectops_cli.py` appears after any CLI has run once. Each call finds the newest installed script and passes the arguments through, so a plugin update mid-session does not pin you to an old path.
> `PYTHONIOENCODING=utf-8 python3 ~/.projectops/bin/projectops_cli.py init-worktree <subcommand> ...` (if it is missing or returns `scripts_not_found`, use the search below). If the response has `newer_installed`, call this entry point again.
> In zsh, do not store the command in a variable (`P="python3 …"; $P` exits 127). To shorten it, wrap it in a function: `G(){ PYTHONIOENCODING=utf-8 python3 ~/.projectops/bin/projectops_cli.py init-worktree "$@"; }` → `G recall --root {source_root}`.

Look for `worktree_manager.py` in this order:
1. `scripts/worktree_manager.py`

## Customize

Your own language, tone and rules apply: see `../references/preferences.md`. Read them once at the start: run the snippet in `../references/preferences.md` with `SKILL_ID=pro-init-worktree`.
Keys for this skill: the common `language`, `tone`, `rules` only.
Preferences change presentation only; approval gates, secret protection and `--dry-run` stay in force.

## Remove a finished worktree

Do not type `git worktree remove --force` yourself. First check that the issue is really closed, then:

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/worktree_cli.py remove --root {source_root} --branch "{branch name}"
```

If there are uncommitted changes, it returns `dirty` with the change list and stops. Use `--force` only after the user decides they can be discarded. The branch and commits remain.
