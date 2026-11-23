# How pro-brain works (for project owners)

> When to read: the owner asks how it works, what it costs, or what a good note looks like.

## In one minute

- Code shows **what** the project does. It rarely shows **why**: why this library and not that one, which rule came from a
  past incident, what must change together. That knowledge usually lives in someone's head or an old chat.
- `pro-brain` writes it down as short notes in the repo's `knowledge/` folder, at the moment the work finishes, while the
  agent still remembers the reasons.
- A team brain (for example GBrain) reads that folder from the main branch every hour. Then anyone on the team can ask
  "why do access tokens expire after 15 minutes?" and get the note back, with links to the issue and the code.
- No extra service, no AI cost in CI: the notes are plain files committed with the work.

## What you do

1. The first time it runs in a repo, it asks at most two questions, each with a recommended answer. Saying yes is enough:
   - **When should notes be written?** It looks at how the repo works and recommends one:
     after each finished issue, at the end of a work session, when a branch is merged, or only when asked.
   - **May I add the knowledge rule to the project CLAUDE.md?** This tells every agent in the repo when to write notes and
     to look in the team brain first when someone asks "why". If you say no, it never asks again.
2. That is all. From then on the agent writes notes at the right moment, skips trivial changes, and commits the notes with
   the work. Notes reach the team brain after the work is merged into the main branch.

If your CLAUDE.md is not committed (it is in `.gitignore`), the rule would not reach new worktrees or teammates, so it
offers a small committed rules file instead, or copies your CLAUDE.md into new worktrees on this machine.

## What a note contains

The brain keeps the **why and where**; git keeps the **what**. A note has a searchable title, a few tags, links to related
notes, facts collected automatically (version, files, endpoints, migrations, setting names, never secret values), and 30 to
80 lines of plain prose. No code dumps, no logs, no chat.

```markdown
---
type: issue-knowledge
id: "issue-812"
title: "Login uses 15-minute access tokens with rotating refresh tokens"
created: 2026-11-23
topics: ["auth", "api", "security"]
status: active
related: ["[[issue-640]]"]
supersedes: ["[[issue-640]]"]
source: "https://github.com/acme/shop/issues/812"
capture_mode: "issue-end"
captured_at: "2026-11-23T14:05:00+09:00"
captured_by: "pro-brain"
project: "shop"
stacks: ["spring"]
app_version: "1.4.0"
issue: 812
pr: 815
commit_count: 3
changed_modules: ["server/auth"]
main_files: ["server/auth/src/main/java/shop/auth/TokenService.java"]
lines_added: 182
lines_deleted: 40
api_endpoints: ["POST /api/auth/login", "POST /api/auth/refresh"]
db_migrations: ["V12__refresh_token.sql"]
config_keys: ["application.yml:jwt.access-ttl-seconds"]
env_or_secret_names: ["JWT_SECRET_KEY"]
---

# Login uses 15-minute access tokens with rotating refresh tokens

Access tokens now live 15 minutes; a refresh token (14 days, one use) gets a new pair.

## Background
One-day access tokens could not be revoked when a phone was lost (issue 640).

## Decision
- Short access tokens plus rotating refresh tokens stored in the database, because a stolen refresh token is detected
  on its second use. Rejected: a token blacklist in Redis (one more server to run for a small team).

## Behavior change
- The app refreshes silently; users stay signed in for 14 days of inactivity instead of 1.

## Code pointers
- `server/auth/src/main/java/shop/auth/TokenService.java > TokenService.rotate()`

## Cautions
- `jwt.access-ttl-seconds` and the app's refresh timer must change together.

## Verification
- Login and refresh tests pass; checked on a real phone that an expired token refreshes without a sign-in screen.
```

## Customizing (optional)

Everything lives in the repo's `version.yml`, so the whole team shares it: the moment notes are written (`capture`), the
folder (`path`, `note_dir`), your own note template or vault rules (`template`, `rules`, `check`), the team brain to search
(`brain_mcp`) and kinds of work never worth a note (`skip`). Details: `note-format.md`.

## Did anything slip through?

`gaps` lists work merged into the main branch since the last note that has no note yet. It only reads git history, so a
team brain's hourly sync job can log it for free. The agent then writes the missing notes or skips them with a reason.
