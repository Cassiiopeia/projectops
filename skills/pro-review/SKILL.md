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

Do not build the save path yourself; get it from the CLI (`../references/doc-output-path.md`):

```bash
PYTHONIOENCODING=utf-8 python3 ~/.projectops/bin/projectops_cli.py review get-output-path review --title "{title}"
```

If that entry point is missing or answers `scripts_not_found`, find the scripts with the fallback block in `../references/script-invocation.md` §Fallback lookup block (`SKILL=pro-review`) and call `review_cli.py` directly (Windows: `python`).

Save the file at the path in the `path` field of the output JSON. If `ok: false`, read `code` and `next` and stop. Do not make up a path.

## Shared references

| Document | Read when |
|---|---|
| `../references/common-rules.md` | Always, at start: absolute rules, confirmation gates, issue state, push |
| `../references/project-detection.md` · `../references/code-style-detection.md` | At start of code work: detect the project type and code style |
| `../references/tech-spring.md` · `../references/tech-react.md` · `../references/tech-flutter.md` | When the project is that stack |
| `../references/work-start-protocol.md` | Before changing code: branch and issue checks, worktree question |
| `../references/sensitive-info.md` | Right before saving an artifact or posting to GitHub: masking table, self-review |

## Customize

Your own language, tone and rules apply: see `../references/preferences.md`. Read them once at the start: run the snippet in `../references/preferences.md` with `SKILL_ID=pro-review`.
Keys for this skill: `sections` plus the common `language`, `tone`, `rules`.
Preferences change presentation only; approval gates, secret protection and `--dry-run` stay in force.
