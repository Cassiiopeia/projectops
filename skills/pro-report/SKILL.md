---
name: pro-report
description: "Generate an implementation report from the git diff and issue analysis, with a mermaid flowchart, and post it as an issue or PR comment. Use after finishing work, for PR descriptions, or /report."
---

# Report Mode - Implementation report

## When to use

- When a report is needed after implementation, when writing a PR description, or on `/report`.
- Typical requests: "write the report", "post a report on the issue" (Korean: "보고서 작성해줘", "구현 보고서 남겨줘").

You are an implementation report writer. **Generate an implementation report from the git diff and the issue.**
Apply the **absolute rules** in `../references/common-rules.md` (no git commits, protect sensitive data).

Talk to the user in the user's language (or the configured `language` preference). Write the report itself in the configured `language`; if none is set, match the repo (its issues, existing reports and README) or the user.

> **⚠️ Model advice**: this needs both summarizing and **explaining**. **Summary-only models (lite/haiku) are not a good fit**; use a mid tier.
> A report's value is in the explanation, not the summary. The diff already shows "what changed". **Why it had to be done this way**
> and **why touching this part later is risky** (§Caveats) need judgment. Without that detail the report is pointless.

## Goal → command → details

Every command is `{PYTHON} {SCRIPTS}/report_cli.py <command>`.

| Goal | Command | Details |
|---|---|---|
| Get the report save path | `get-output-path report --title "{title}" [--issue {number}]` | `../references/doc-output-path.md` |
| Post as an issue comment | `add-comment {owner} {repo} {number} "{absolute .md path}"` | `references/posting.md` |
| Body template · mermaid rules | — | `references/output-template.md` |
| Attach screenshots | pro-github `upload-image` | `references/posting.md` |
| Finish the issue | pro-github `finish-issue` | Step 7 below |

## Approval gate · questions before starting (required)

This skill produces a md file, so **follow `../references/approval-and-questions.md`** (#526).

1. **Before starting**: ask only about items that change the result a lot, one at a time. Do not ask if the input already answers it.
2. **Before saving**: show the content and get approval. In an auto-mode repo, show a summary and save right away.
   Once saving is approved, continue through posting the comment (Step 6). If the user picks "view only", neither save nor post.
3. **Once, on first run**: ask whether to proceed without confirmation from now on, and remember the answer.
4. Do not show config key names or file paths to the user.

## Find the scripts · save path (once)

> **Skip the search below if the fixed entry point exists** (#942): `~/.projectops/bin/projectops_cli.py` appears after any CLI has run once. Each call finds the newest installed script and passes the arguments through, so a plugin update mid-session does not pin you to an old path.
> `PYTHONIOENCODING=utf-8 python3 ~/.projectops/bin/projectops_cli.py report <subcommand> ...` (if it is missing or returns `scripts_not_found`, use the search below). If the response has `newer_installed`, call this entry point again.
> In zsh, do not store the command in a variable (`P="python3 …"; $P` exits 127). To shorten it, wrap it in a function: `G(){ PYTHONIOENCODING=utf-8 python3 ~/.projectops/bin/projectops_cli.py report "$@"; }` → `G get-output-path report --title "{title}"`.

**The Bash tool resets its state on every call.** Find the paths once, then **write the real paths as literal values in later blocks.**

```bash
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
PYTHON=$(for _py in python3 python; do _path=$(command -v "$_py" 2>/dev/null) || continue; "$_path" -c "import sys; sys.exit(0)" 2>/dev/null && echo "$_path" && break; done)
[ -z "$PYTHON" ] && { echo "Python not found"; exit 1; }
SKILL=pro-report; ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
[ -d "$ROOT/skills/$SKILL/scripts" ] || for B in ~/.claude/plugins/cache ~/.codex/plugins/cache ~/.gemini/extensions ~/.pi/agent/git; do
  H=$(find "$B" -maxdepth 8 -type d -path "*/projectops/*skills/$SKILL/scripts" 2>/dev/null | sort -V | tail -1)
  [ -n "$H" ] && { ROOT="${H%/skills/$SKILL/scripts}"; break; }
done
# Home-copied installs from npx projectops: GitHub Copilot and Cursor (#200)
[ -d "$ROOT/skills/$SKILL/scripts" ] || for B in ~/.copilot ~/.cursor; do [ -d "$B/skills/$SKILL/scripts" ] && { ROOT="$B"; break; }; done
SCRIPTS="$ROOT/skills/$SKILL/scripts"
[ -d "$SCRIPTS" ] || { echo "projectops skill scripts not found. Check the plugin installation."; exit 1; }
echo "PYTHON=$PYTHON SCRIPTS=$SCRIPTS"
PYTHONIOENCODING=utf-8 "$PYTHON" "$SCRIPTS/report_cli.py" get-output-path report --title "{title}"
```

**Do not build the path yourself.** Use the returned `path` as is (#525). Shape (for reference): `{output root}/report/YYYYMMDD_{issue number}_{normalized title}.md`.
**If you worked on the development branch (`develop` and so on), also pass `--issue {number}`.** The branch name has no number, so a `_001_` serial is used otherwise.
You can pass the issue title as is (the CLI strips emoji, `[tags]` and a leading copy of the same issue number).
The output root can change with team settings, so do not hard-code `docs/projectops`.

## Core principles

- **Conversation context first**: before investigating, check whether the conversation already has the answer. If so, use it; investigate only what is missing (Step 0)
- **Efficient analysis · minimal git**: check changed file names with `git status` → pick only the files related to the issue and read them directly with Read
- **Short and clear**: make the approach easy to understand
- **Visualize the flow**: draw a mermaid flowchart when there are multiple steps, branches or state transitions (`references/output-template.md`)
- **Sensitive data**: apply the masking rules in `../references/common-rules.md`

**Never include**: meta information such as `**Author**:` / `**Date**:` / `## Author info` · wording like `Claude`, `AI`, `auto-generated` · unneeded reviewer or approver info.

## Process

### Step 0: Check the conversation context (do this first)

If the implementation happened in the same conversation, **what changed and why is already in the conversation.** Do not investigate again.

| What the report needs | If it is in the conversation | If not |
|---|---|---|
| Changed file list | Use it | Do Step 1 |
| What changed | Use it | Do Step 2 |
| **Why it was done that way** | Use it (cannot be rebuilt; it exists only in the conversation) | Ask the user |
| Verification results (tests, runs) | Use it | Check if needed |
| Pitfalls hit · caveats | Use it (cannot be rebuilt) | Ask the user |

**The "why" and the "pitfalls" cannot be recovered from the diff.** When they are in the conversation, always keep them. If you have everything, skip Steps 1 and 2.
If you have only part, investigate **only what is missing**. If the conversation has no context (for example, another session's work), start from Step 1.

### Step 1: Find the changes (only if not in the conversation)

Check only the changed file names with `git status`, then pick the files related to the issue.

### Step 2: Read the files directly (only if not in the conversation)

Read the changed files directly with Read. No extra git diff calls are needed.

### Step 3: Decide whether a flowchart is needed → Step 4: Write the report

Draw one for multiple steps, branches, state transitions or several cooperating components; skip it for simple changes. Output template, decision table and mermaid rules (separate subgraph IDs,
`flowchart TD` only, no `\n` or self-loops, and so on) are in `references/output-template.md`.

If preferences have `sections` or `template`, use them for the report's section layout.

### Step 5: Self-check for sensitive data right before saving → save

Review the whole body with the **self-check protocol before saving files** in `../references/common-rules.md`. Mask anything found, then
save to the `path` from `get-output-path` (`../references/doc-output-path.md`).

### Step 6: Post a GitHub comment (only when a PAT exists)

Issue number detection order (worktree folder name → branch name → conversation → ask), PAT and repo checks, and image attachment order are in `references/posting.md`.
Read only the fixed config path `{HOME}/.projectops/config/config.json`. Do not dig through plugin caches. If it is missing, save locally and stop.

```bash
PYTHONIOENCODING=utf-8 "{PYTHON}" "{SCRIPTS}/report_cli.py" add-comment {owner} {repo} {issue_number} "{absolute path of the report .md file}"
```

report_cli loads the PAT from config.json automatically (an environment variable wins). Use `url` from the output in the completion message.

| Failure `code` | Next action |
|---|---|
| `github_api_401` | Tell the user the PAT expired → point them to re-register it in `/pro-github`. Finish with the local save only |
| `github_api_404` | Recheck the issue number and repo, then ask the user |
| `bad_args` / file missing | Check the absolute `body_file` path and the argument order (`owner repo number body_file`) |

### Step 7: Finish the issue (after posting the report)

Once the report comment is posted, finish the issue. Follow the "Finish an issue" recipe in the `pro-github` SKILL.md exactly; do not define a separate procedure here.

- **If the work is done**: pro-github `finish-issue {owner} {repo} {number}`. It changes only the status label to `status: done` (`작업완료`) and closes the issue (other labels such as `type:` and `area:` stay).
  Do not use `set-labels {…} "status: done"` instead. `set-labels` **replaces all labels**, so every other label is removed
- **If work remains** (follow-up commits, waiting for verification after deploy, or the user said "not yet"): **skip** this step and keep `status: in progress`. State what remains in the completion message
- If the repo `CLAUDE.md` sets a different rule, follow it
- If no comment was posted because there is no PAT, skip this step too

### Completion message

```
Report saved: {path returned by get-output-path}
GitHub comment: https://github.com/{owner}/{repo}/issues/{number}#issuecomment-{id}
Issue status: replaced with status: done and closed (or: remaining work {what}, left open)
```

Without a PAT:
```
Report saved: {path returned by get-output-path}
(No GitHub PAT set; saved locally only)
```

## Customize

Your own language, tone and rules apply: see `../references/preferences.md`. Read them once at the start: run the snippet in `../references/preferences.md` with `SKILL_ID=pro-report`.
Keys for this skill: `sections`, `template` plus the common `language`, `tone`, `rules`.
Preferences change presentation only; approval gates, secret protection and `--dry-run` stay in force.
