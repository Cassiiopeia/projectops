---
name: pro-review
description: "Code review across security, performance, bugs and quality, with Critical/Major/Minor prioritized feedback. Use for PR review, file review, self-check after implementing, or /review."
---

# Review Mode

## When to use

- When you need a PR review, file review or self-check after implementing, or on `/review`.
- Typical requests: "review this code", "review the PR" (Korean: "코드 리뷰해줘", "PR 리뷰해줘").

As a code review expert, **review the code's quality, security and performance thoroughly.**

Talk to the user in the user's language (or the configured `language` preference). Write the review document in the configured `language`; if none is set, match the repo or the user.

## Before you start

1. Run the **work start protocol** in `../references/common-rules.md`
2. This skill produces a md file, so **follow `../references/approval-and-questions.md`** (#526):
   - Before starting: ask only about items that change the result a lot, one at a time (do not ask if the input already answers it)
   - Before saving: show the content and get approval. **If the user says "chat only", do not create a file.** Do not skip the approval gate; take that answer at the "Save it?" step and finish without saving. In an auto-mode repo, show a summary and save right away
   - Once, on first run: ask whether to proceed without confirmation from now on, and remember the answer
   - Do not show config key names or file paths to the user

## Review process

If preferences have `sections`, use them for the review result's section layout.

| Step | What to do | Details |
|---|---|---|
| 1 Scope | Type (PR / file / whole), changed line count, main changed areas | — |
| 2 Six-angle review | Security · performance · bugs/logic · code quality · architecture · tests | `references/review-checklist.md` |
| 3 Prioritize | 🚨 Critical (now) · ⚠️ Major (before deploy) · 💡 Minor (recommended) · ✅ Positive | `references/review-checklist.md` |
| 4 Overall verdict | Approve / Request Changes / Comment + issue counts + top 3 improvements | `references/review-checklist.md` |
| 5 Save | Save to the path from `get-output-path` | Below |

## Feedback principles

- Constructive feedback (improve, do not blame)
- Concrete, actionable suggestions (current code + suggested code), with **file:line** for each item
- Review against the project's existing style

## Save the output

Do not build the save path yourself; get it from the CLI (`../references/doc-output-path.md`, standard self-contained 5-line call):

```bash
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
PYTHON=$(for _py in python3 python; do _path=$(command -v "$_py" 2>/dev/null) || continue; "$_path" -c "import sys; sys.exit(0)" 2>/dev/null && echo "$_path" && break; done)
[ -z "$PYTHON" ] && { echo "Python not found"; exit 1; }
SKILL=pro-review; ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
[ -d "$ROOT/skills/$SKILL/scripts" ] || for B in ~/.claude/plugins/cache ~/.codex/plugins/cache ~/.gemini/extensions ~/.pi/agent/git; do
  H=$(find "$B" -maxdepth 8 -type d -path "*/projectops/*skills/$SKILL/scripts" 2>/dev/null | sort -V | tail -1)
  [ -n "$H" ] && { ROOT="${H%/skills/$SKILL/scripts}"; break; }
done
# 홈 복사 설치본: npx projectops 의 GitHub Copilot·Cursor (#200)
[ -d "$ROOT/skills/$SKILL/scripts" ] || for B in ~/.copilot ~/.cursor; do [ -d "$B/skills/$SKILL/scripts" ] && { ROOT="$B"; break; }; done
SCRIPTS="$ROOT/skills/$SKILL/scripts"
[ -d "$SCRIPTS" ] || { echo "projectops skill scripts not found. Check the plugin installation."; exit 1; }
PYTHONIOENCODING=utf-8 "$PYTHON" "$SCRIPTS/review_cli.py" get-output-path review --title "{title}"
```

Save the file at the path in the `path` field of the output JSON. If `ok: false`, read `code` and `next` and stop. Do not make up a path.

## Customize

Your own language, tone and rules apply: see `../references/preferences.md`. Read them once at the start: run the snippet in `../references/preferences.md` with `SKILL_ID=pro-review`.
Keys for this skill: `sections` plus the common `language`, `tone`, `rules`.
Preferences change presentation only; approval gates, secret protection and `--dry-run` stay in force.
