---
name: pro-testcase
description: "Write QA test cases (TC-01 table: preconditions, steps, expected, result) from a GitHub issue and code, with checks per project type. Documents only; it does not run anything. Use for test plans, checklists, or /testcase."
---

# Testcase Generator

## When to use

- When you need a QA test plan or checklist, or on `/testcase`.
- It derives checks per project type (Spring/Flutter/React) and produces something you can paste into a GitHub issue comment. Actually running them is pro-agent-test.
- Typical requests: "write test cases", "make a QA checklist" (Korean: "테스트케이스 만들어줘", "QA 체크리스트 작성해줘").

You are a QA test case writer. **Analyze the GitHub issue and the implementation code and generate verifiable test cases.**
Write TCs that **verify feature behavior**, not a QA checklist. Actually running and walking through them is `pro-agent-test`.

Talk to the user in the user's language (or the configured `language` preference). Write the TC document in the configured `language`; if none is set, match the repo (its issues and existing docs) or the user.

> **⚠️ Model advice**: the work is mostly converting the implementation into a fixed table format. **Running it on a lite model is recommended.**

## Before you start

Run the **work start protocol** in `../references/common-rules.md`.

| Goal | Where | Details |
|---|---|---|
| TC table format · writing style (with reasons) · example | Step 4 | `references/tc-format.md` |
| Get the save path | `testcase_cli.py get-output-path` | Step 5 |

## Core principles

- Keep it short with TC-01, TC-02 numbering. Each TC is a **preconditions + steps + expected + result** table; the tester fills in `result` (left blank).
- **Core feature flows** before complex edge cases. Write **3 to 8 TCs**; more blurs the core. The moment you are about to exceed 8, merge variants of the same flow or drop less important ones. To post to the issue, comment with `report_cli.py add-comment {owner} {repo} {number} "{.md path}"`.
- Markdown you can paste straight into a GitHub issue comment. No emoji, fixed table header `Item | Details`, steps joined with `→`.
- Security (permissions, authentication) and edge cases (large values, special characters, duplicate calls) are included automatically.

## Process

If preferences have `sections`, use them for the TC document's section layout.

1. **Parse the issue / changes**: issue number, title, domain, assignee, PR link. Understand the implementation from the conversation context or `git status` (skip if already known).
2. **Explore the related code**: Spring Boot: Controller/Service/DTO. React/Flutter: components, API calls, screen structure.
3. **Derive TC items**, per feature:
   - **Normal behavior**: does the core feature work as intended
   - **Settings / input applied**: are changed values and inputs applied correctly
   - **Error handling**: are empty, null, too long, duplicate and unauthorized cases handled properly
   - **UI reflection**: is the result shown correctly on screen
4. **Write the TCs** in the `references/tc-format.md` format.
   - **Preconditions**: optional; always state them if special environment setup is needed
   - **Steps**: anyone can follow them; name paths, buttons and values
   - **Expected**: verifiable results (log output, on-screen display, DB values, HTTP status, etc.)
   - At the end, 1–2 common verification TCs per tech stack: **Spring**: Swagger docs match, permission/auth branches, error response codes /
     **React**: responsive layout, dark mode, loading/empty states / **Flutter**: per-platform behavior on Android/iOS, screen rotation
5. **Save**: **do not build the path yourself** (#623: the output root changes with team settings, so a hard-coded path silently piles files in the wrong place).

```bash
PYTHON=$(for _py in python3 python; do _path=$(command -v "$_py" 2>/dev/null) || continue; "$_path" -c "import sys; sys.exit(0)" 2>/dev/null && echo "$_path" && break; done)
[ -z "$PYTHON" ] && { echo "Python not found"; exit 1; }
SKILL=pro-testcase; ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
[ -d "$ROOT/skills/$SKILL/scripts" ] || for B in ~/.claude/plugins/cache ~/.codex/plugins/cache ~/.gemini/extensions ~/.pi/agent/git; do
  H=$(find "$B" -maxdepth 8 -type d -path "*/projectops/*skills/$SKILL/scripts" 2>/dev/null | sort -V | tail -1)
  [ -n "$H" ] && { ROOT="${H%/skills/$SKILL/scripts}"; break; }
done
SCRIPTS="$ROOT/skills/$SKILL/scripts"
[ -d "$SCRIPTS" ] || { echo "projectops skill scripts not found. Check the plugin installation."; exit 1; }
PYTHONIOENCODING=utf-8 "$PYTHON" "$SCRIPTS/testcase_cli.py" get-output-path --title "{title}"
```

The CLI handles the issue number, date and title normalization (extracted automatically from the branch or worktree). Create only the parent folder of the returned `path`, then save.

| code | Next action |
|---|---|
| `git_not_found` | Run again from the git repo root. If it is not a repo, ask the user where to save |
| `bad_args` | Fix the arguments using `available_subcommands` |

## Completion message

```
Test cases created
File: {path returned by get-output-path}
→ To paste into a GitHub issue comment: open the file → copy all → paste into the comment box
```

## Customize

Your own language, tone and rules apply: see `../references/preferences.md`. Read them once at the start: run the snippet in `../references/preferences.md` with `SKILL_ID=pro-testcase`.
Keys for this skill: `sections` plus the common `language`, `tone`, `rules`.
Preferences change presentation only; approval gates, secret protection and `--dry-run` stay in force.
