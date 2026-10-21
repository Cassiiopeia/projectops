---
name: pro-commit
description: "Create the commit with a message built from the issue number in the branch name. Use when committing issue-linked work or auto-generating a commit message, or on /commit."
---

# Commit Mode

## When to use

- Committing issue-linked work, generating a commit message automatically, or on `/commit`.
- Typical requests: "commit this", "write the commit message" (Korean: "커밋해줘", "커밋 메시지 만들어줘").

Extract the issue number from the branch name, read the issue through the GitHub API, then **build a message that follows the commit convention and commit it**.
Follow the commit convention in `../references/common-rules.md`. User input: $ARGUMENTS

Talk to the user in the user's language (or the configured `language` preference). The prompts below are written in English as templates; translate them when you show them.

## Goal → command → details

Every command is `{PYTHON} {SCRIPTS}/commit_cli.py <command>`.

| Goal | Command | Details |
|---|---|---|
| Read issue title and URL | `get-issue {owner} {repo} {number}` | Step 3 |
| Issue number of the current branch (cwd) | `get-issue-number` | Step 3 |
| Read commit format and tone (team > personal) | `resolve-style --repo-root "{PROJECT_ROOT}"` | Step 4 · Customize |
| Clean the issue title · build the message frame | `normalize-title "<title>"` · `get-commit-template "<title>" "<URL>" [--type fix] [--scope S] --repo-root "{PROJECT_ROOT}"` | `references/message-rules.md` |
| Strip the mention trailer right before commit | `sanitize-message "<message>"` | `references/message-rules.md` |
| Decide auto/manual approval · first-run offer | (config Read/Write) | `references/approval-gate.md` |

## Core principles

- **Never commit without user confirmation.** Always propose the message, get approval, then run.
- **Never create an issue automatically.** If there is no issue, offer choices and let the user decide.
- **Never stage everything with `git add -A` or `git add .`.** Several sessions share the same working tree, so bulk staging mixes another session's uncommitted changes into your commit. Show the change list and run `git add <path...>` with **only the paths this task touched**. Leave changes you do not understand alone.
- **Never run `git push`.** This skill stops at the commit (CLAUDE.md rule: push only with explicit permission).
- **Never leave a Claude/AI trace in the commit.** No `Co-Authored-By`, `Generated with Claude`, `🤖`, `@claude`, or any AI signature, footer or GitHub @mention trailer. Do not put any `@username` GitHub mention anywhere in the description or footer (remove mentions copied from the issue body too). The commit uses only the user's git config, so it looks like the user wrote it. Write only the message body.
- **In auto mode (`auto_approve == true`), still show the proposed message before committing.** Show it and proceed at once; do not wait for a reply.
- **Do not show config key names or file paths to the user.** The user toggles auto/manual in natural language ("go ahead automatically" / "ask me every time"; Korean: "자동으로 진행해줘" / "매번 확인받게 해줘") and the agent updates the config itself. Every time you write the approval setting, also apply Rule D (format lock) in `references/approval-gate.md`.

## Before you start: decide auto approval

Read only one file, `~/.projectops/config/config.json` (Windows: `C:\Users\<user>\.projectops\config\config.json`), with Read,
and set `AUTO_APPROVE` and `CONFIG_HAS_KEY`. Precedence (per repo → global → default `false`) and how to update it: `references/approval-gate.md`.

## Find the scripts (once)

> **Skip the search below if the fixed entry point exists** (#942): `~/.projectops/bin/projectops_cli.py` appears after any CLI has run once. Each call finds the newest installed script and passes the arguments through, so a plugin update mid-session does not pin you to an old path.
> `PYTHONIOENCODING=utf-8 python3 ~/.projectops/bin/projectops_cli.py commit <subcommand> ...` (if it is missing or returns `scripts_not_found`, use the search below). If the response has `newer_installed`, call this entry point again.
> In zsh, do not store the command in a variable (`P="python3 …"; $P` exits 127). To shorten it, wrap it in a function: `G(){ PYTHONIOENCODING=utf-8 python3 ~/.projectops/bin/projectops_cli.py commit "$@"; }` → `G get-issue-number`.

**The Bash tool resets its state on every call.** Find the paths once, then **write the real paths as literal values in later blocks.**

```bash
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
PYTHON=$(for _py in python3 python; do _path=$(command -v "$_py" 2>/dev/null) || continue; "$_path" -c "import sys; sys.exit(0)" 2>/dev/null && echo "$_path" && break; done)
[ -z "$PYTHON" ] && { echo "Python not found"; exit 1; }
# When developing in this repo the local copy is newer than the cache, so prefer it (user projects use the installed copy)
SKILL=pro-commit; ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
[ -d "$ROOT/skills/$SKILL/scripts" ] || for B in ~/.claude/plugins/cache ~/.codex/plugins/cache ~/.gemini/extensions ~/.pi/agent/git; do
  H=$(find "$B" -maxdepth 8 -type d -path "*/projectops/*skills/$SKILL/scripts" 2>/dev/null | sort -V | tail -1)
  [ -n "$H" ] && { ROOT="${H%/skills/$SKILL/scripts}"; break; }
done
# 홈 복사 설치본: npx projectops 의 GitHub Copilot·Cursor (#200)
[ -d "$ROOT/skills/$SKILL/scripts" ] || for B in ~/.copilot ~/.cursor; do [ -d "$B/skills/$SKILL/scripts" ] && { ROOT="$B"; break; }; done
SCRIPTS="$ROOT/skills/$SKILL/scripts"
[ -d "$SCRIPTS" ] || { echo "projectops skill scripts not found. Check the plugin installation."; exit 1; }
echo "PYTHON=$PYTHON SCRIPTS=$SCRIPTS PROJECT_ROOT=$PROJECT_ROOT"
```

## Process

### Step 1: Check and stage changes

```bash
git diff --cached --stat
git status --short
```

**If files are already staged**, show the list and continue. If some look unrelated to this task, tell the user before committing (do not unstage them yourself).

**If nothing is staged**, show the changes in two groups and stage only the first group, path by path:

| Group | How to tell | Action |
|------|-----------|------|
| Paths this task touched | Files this session edited or created, files the user pointed to | Stage explicitly with `git add <path...>` |
| Changes you do not understand | Files in the working tree that this session did not create | **Leave them alone.** They may be another session's work in progress |

```bash
# Name each touched path. Quote paths with spaces or non-ASCII characters.
git add -- "{path1}" "{path2}"
git diff --cached --stat
```

- Do not use `git add -A`, `git add .` or `git add -u`. If you cannot tell what you touched, show the list and let the user choose.
- **If you cannot know which files this session changed** (called from a new session), do not guess. Show the change list and ask which paths to include.
- If there is no path to stage, do not commit. Just say so.
- If the user **cancels** later (Step 2 option 3 · Step 5 option 4), run `git restore --staged -- "{paths you staged}"` to undo **only what you staged**. Leave files that were staged from the start untouched.

### Step 2: Extract the issue number

```bash
BRANCH=$(git branch --show-current 2>/dev/null || echo "")
ISSUE_NUMBER=$(echo "$BRANCH" | grep -oE '#[0-9]+' | grep -oE '[0-9]+' | head -1)
REMOTE_URL=$(git remote get-url origin 2>/dev/null || echo "")
OWNER=$(echo "$REMOTE_URL" | sed -E 's|.*github\.com[:/]([^/]+)/.*|\1|')
REPO=$(echo "$REMOTE_URL" | sed -E 's|.*github\.com[:/][^/]+/([^/.]+)(\.git)?$|\1|')
```

Branch name example: `20260422_#260_기능개선_제목` → `260`. (`{PYTHON} {SCRIPTS}/commit_cli.py get-issue-number` returns the same value.)

**If there is no issue number**, stop and ask:

```
No issue number found in the branch name. (Current branch: {branch})

What should I do?
1. I'll enter the issue number
2. Commit in free form without an issue
3. Cancel
```

1 → take the number and go to Step 3 / 2 → take the message from the user and go to Step 5 (no issue format) / 3 → stop.

### Step 3: Read the issue (no inline Python)

commit_cli loads the PAT from config.json automatically (an environment variable wins if set).

```bash
PYTHONIOENCODING=utf-8 "{PYTHON}" "{SCRIPTS}/commit_cli.py" get-issue {owner} {repo} {issue_number}
```

Use `title` and `html_url` from the output. **Do not summarize or rewrite the title.** Apply only the cleaning rule (remove tags → remove leading emoji → trim; if empty, use the original). See `references/message-rules.md`.

| Failure | Next action |
|---|---|
| `github_api_401` | Tell the user the PAT expired → point them to re-register it in `/pro-github`. Take the title from the user directly |
| `github_api_404` | Tell the user the issue does not exist → recheck the number or take the title directly |
| `bad_args` | Check the argument order (`owner repo number`) |

### Step 4: Build the message

The format comes from settings, not from hard-coded text. Do this in order.

1. Run `resolve-style --repo-root "{PROJECT_ROOT}"` to get `template`, `source`, `preset`, `language`, `tone`, `rules`, `examples`, `warnings`. If `warnings` or `ignored` is not empty, tell the user in one line.
2. Run `get-commit-template "<title>" "<URL>" [--type T] [--scope S] --repo-root "{PROJECT_ROOT}"` to get the frame. Only `{description}` remains in it. Without `--repo-root` it uses the git root of the cwd, but the skill may be called from a subfolder or another repo, so always pass it.
3. Fill `{description}` from the staged diff. Follow `language`, `tone`, `rules`. Use `examples` only as a reference for voice and length; never copy them. If they are empty, use the default behavior.

- Use the cleaned issue title and URL exactly as the CLI returns them (no summarizing or rewriting).
- Suggest the type from the staged diff (feat/fix/refactor/docs/chore/test/style; table in `references/message-rules.md`). If you omit `--type`, it is derived from the title tag.
- **Add `!` only for breaking changes** (`feat!` → major bump on release, #546). If unsure, do not add it; ask.
- Do not put `@username` mentions in `{description}`.

### Step 5: Approval gate

- `AUTO_APPROVE == true` → only show the message, then go straight to Step 6.
- `false` → propose it and ask 1 (commit) / 2 (change type) / 3 (edit description) / 4 (cancel). **Do not commit before the reply.**
- On first run (`CONFIG_HAS_KEY == false`), if the user picks 1, make the automation offer **once** right before committing.
- If `source` from `resolve-style` is `default` or `legacy-default` (the user never set a format), add **one line** at the end of this session's first proposal: "Commit format and tone can be customized; see Customize" (in the user's language). Do not add it again in the same session.

Full wording, branches and config update rules: `references/approval-gate.md`.

### Step 6: Commit

**Never add an AI signature or footer.** Commit with the user's git config as is, without `--author` or trailers.
Force-remove the mention trailer at the end of the message with `sanitize-message` (no shell `sed`, #523; reason in `references/message-rules.md`).

Save the message to a file, then clean, stage and commit with one command (no need to unpack JSON in the shell):

```bash
PYTHONIOENCODING=utf-8 "{PYTHON}" "{SCRIPTS}/commit_cli.py" commit --message-file "{message file}" --root "{PROJECT_ROOT}" --paths "{path1}" "{path2}"
```

- Pass to `--paths` **only the paths this task touched**, as decided in Step 1. Omit it if they are already staged.
- If you only need the cleaned message, use `sanitize-message "$RAW_MSG" --raw`.

- If cleaning fails or returns empty (`empty_message`), **stop the commit**. Do not copy the cleaning rule into the docs as a fallback.
- If `mention_removed: true`, go back to Step 4 and find how the mention got in. Mentions in the middle of the body are kept.

After a successful commit:

```
✅ Committed!
Message: {commit message}
Hash: {first 7 characters of the commit hash}

To push, run it yourself:
git push origin {current branch}
```

## Customize

Your own language, tone and rules apply: see `../references/preferences.md`. Read them once at the start: run the snippet in `../references/preferences.md` with `SKILL_ID=pro-commit` (or call `resolve-style`, which also returns them).
Preferences change presentation only; approval gates, secret protection and `--dry-run` stay in force.

Keys for this skill (set under `skills.pro-commit` in `~/.projectops/config/config.json`):

| Key | Meaning |
|---|---|
| `preset` | `conventional` (default for new users), `projectops`, `gitmoji`, or `custom` |
| `template` | your own format; beats a `preset` set in the same layer (the preset then becomes `custom`); placeholders `{issue_title}` `{issue_url}` `{issue_number}` `{type}` `{emoji}` `{scope}` `{description}`. Legacy `${issueTitle}`-style placeholders are accepted too |
| `examples` | sample messages to match in voice and length; never copied verbatim |
| `language` / `tone` / `rules` | how `{description}` is written |

```json
{"skills": {"pro-commit": {"preset": "conventional", "language": "en", "tone": "imperative",
                           "rules": ["max 72 chars in the first line"]}}}
```

- A repo with projectops installed (`version.yml` has `issue_helper.commit_template`, or `metadata`) uses the team format and it beats your preset and template (`source` is `version.yml` or `team-default`). Your `tone`/`rules`/`language` still apply inside it. The team `commit_type_map` also applies when the type is inferred from title tags.
- `preset` and `template` are one pair: the later layer that sets either one wins (a repo-level `preset` beats a global `template`).
- Existing users keep their format: if you already have approval settings (`github.commit` or `repos[].commit`) and never set `preset`/`template`, the format stays `projectops` (`source` is `legacy-default`) instead of switching to `conventional`.
- Show `warnings` from `resolve-style` / `get-commit-template` to the user.
