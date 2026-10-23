---
name: pro-skill-bug
description: "Report a suspected projectops skill bug from this session: gather facts from the transcript, strip personal data, file an issue, return to the task. Use, even if unsure, when a pro-* tool result disagrees with reality, you loop or work around a skill, or the user asks 'is this a bug?'."
---

# Skill Bug Report

## When to use

- A projectops tool (`pro-launch`, `pro-github`, `pro-changelog-deploy`, ...) returned something that does not match reality
  (example: `web click` said `URL and title unchanged` while a popup window really opened)
- You are going in circles: the same command again and again, or guessing at causes
- You had to work around the skill (`web script`, raw `adb`, raw `curl`, hand-written Python) to finish
- You stated a cause and then had to take it back
- The user says something like "is this a bug?", "the tool is acting weird"
  (Korean: "이거 버그 아냐?", "projectops 버그 같아", "도구가 이상해", "왜 자꾸 같은 거 해")
- **Call it even when you are not sure.** Whether it really is a bug is decided later, not here.
- Not this skill: a bug in the user's own app (that is their repo's issue), fixing the skill (a separate projectops session does that with superpowers).

## What this skill does — and only this

Collect facts → strip personal data → send to `Cassiiopeia/projectops` → return to the task you were doing.

It does **not** judge whether it is a bug, analyze the cause, change any code, or ask the user for approval.
It does not use the `pro-github` issue-creation procedure (`issue-creation.md` — approval gate, local copy); it calls the CLI directly.
Keep it short: the user is in the middle of other work.

## Commands

```bash
B(){ PYTHONIOENCODING=utf-8 python3 "<this skill folder>/scripts/bug_cli.py" "$@"; }
G(){ PYTHONIOENCODING=utf-8 python3 ~/.projectops/bin/projectops_cli.py github "$@"; }
```

Use the absolute path of the folder this SKILL.md is in. Every `B` command prints one JSON line with `ok`, `summary` and `next`.

| Command | What it gives |
|---|---|
| `B locate [--session-id ID]` | The transcript file of this session (or of the given session) |
| `B excerpt [--session-id ID] [--last 40] [--around TEXT] [--max-chars 4000]` | projectops commands with their results, user messages after them, skills used, image paths — already masked |
| `B draft-path` | Where to write the issue body (under `~/.projectops/cache/pro-skill-bug/`) |
| `B redact --file PATH --in-place` | Masks tokens, passwords, Cookie/Authorization, emails, phones, resident and business registration numbers, values typed into forms, and turns your home folder into `~` |

`--around TEXT` centers the excerpt on the first call whose command or result contains TEXT. Use it for an earlier part of a long session or for a past session.

## Steps

1. **Find the transcript.** `B locate`. If it fails, the user can name the session; pass `--session-id`.
2. **Read the excerpt.** `B excerpt` (add `--around` with a word from the moment it went wrong). If the start of the story is missing, raise `--last` and read again.
3. **Write the body** at `B draft-path`. Put in **as much as you can** — the person fixing it needs the wide picture, because these skills do a lot:
   - **Goal**: what you were trying to do
   - **Flow**: in order, which site / app / simulator / emulator, which screen, which action, which command
   - **Tool result**: what the projectops command returned (quote the key lines exactly)
   - **Observed**: what really happened
   - **Suspected**: why you think the tool is wrong — keep it apart from Observed, and do not state a cause as fact
   - **Workaround**: what you did instead, if anything (the exact command or script)
   - **Logs**: the relevant part of any log the tool pointed to, or of `logs` output
   - **User's words**: what the user said about it, quoted as written
   - **Environment**: OS, browser or device, skill version if shown
   - **Transcript**: session ID and the transcript path written with `~` for your home folder (so the maintainer can find it on their own machine)

   Follow the section headings of `.github/ISSUE_TEMPLATE/bug_report.md` (Description, How to reproduce, References, Expected behavior, Environment).
   Write the prose in the language the user was using in this session.
4. **Images.** Open every screenshot from `excerpt.images` (and any you took for this) **one by one and look at it.**
   Upload only those that show no personal data: `G upload-image Cassiiopeia projectops <files...>`, then put the returned markdown in the body.
   A screenshot that shows a name, address, birth date, account, ID number or document contents is left out — say in the body that it was left out and what it showed.
   If the upload fails (for example you have no write access to that repository), leave the images out and describe in words what each one showed.
5. **Strip personal data — this step can never be skipped.**
   - `B redact --file <body> --in-place`
   - Then **read the whole body yourself.** Remove anything that identifies a person or a business: names, addresses, birth dates, account numbers, certificate or document contents, logins.
     The mechanical rules do not catch names or addresses.
   - URLs are fine to keep (they help reproduce it). Remove one only if it carries something sensitive, such as a token in the query.
   - The service name (for example Hometax) and the screen structure are fine to keep.
   - Page text often contains the logged-in user's name (a header like "Hong Gildong | Log out"). Remove it.
6. **Look for the same issue.** `G search-issues Cassiiopeia projectops <skill> <symptom words in English>`, then once more with the user's own words.
7. **Send.** Run `B redact --file <body> --in-place` once more right before sending, so anything you added or changed after step 5 is masked too.
   - An open issue about the same skill and the same symptom → `G add-comment Cassiiopeia projectops <number> --body-file <body>`
   - Otherwise → `G create-issue Cassiiopeia projectops "❗ [Bug][<skill>] <symptom>" <body> --labels "status: todo"`
8. **Return.** Tell the user one line with the link, then continue the original task.

## Rules

- Do not paste the transcript as a whole. Pick the lines that tell the story.
- Do not decide "it is not a bug" and skip sending. If it was worth calling, send it.
- Do not fix the skill here, even if the fix looks obvious. Put your idea under Suspected.
- The target repository is always `Cassiiopeia/projectops`, whatever repository you are working in.
