# How pro-brain works (for project owners)

> When to read: the owner asks how it works, what it costs, which brain setup fits, or what a good note looks like.

## In one minute

- Code shows **what** the project does. It rarely shows **why**: why this library and not that one, which rule came from a
  past incident, what must change together. That knowledge usually lives in someone's head or an old chat.
- `pro-brain` writes it down as short notes in the repo's `knowledge/` folder, at the moment the work finishes, while the
  agent still remembers the reasons.
- The notes alone are already useful: any agent reads the folder. If you also run a "brain" (a search service for notes,
  for example GBrain), it can read the same folder, and then anyone can ask "why do access tokens expire after 15 minutes?"
  and get the note back, with links to the issue and the code.
- No extra service is required, no AI cost in CI: the notes are plain files committed with the work.

## What you do

1. The first time it runs in a repo, it asks at most three questions, each with a recommended answer. Saying yes is enough:
   - **When should notes be written?** It looks at how the repo works and recommends one:
     after each finished issue, at the end of a work session, when a branch is merged, or only when asked.
   - **May I add the knowledge rule to the project CLAUDE.md?** This tells every agent in the repo when to write notes and
     to look in the team brain first when someone asks "why". If you say no, it never asks again.
   - **How do you use this repo's knowledge?** It checks this machine and the repo and recommends an answer (table below).
2. That is all. From then on the agent writes notes at the right moment, skips trivial changes, and commits the notes with
   the work. Run the setup again any time to see what is in effect and change it.

## Which answer fits you?

| Your situation | Pick | What happens | What you need |
|---|---|---|---|
| You just want the knowledge kept with the code (most repos) | **1. Repo only** | Notes stay in the repo. Agents read the folder | Nothing |
| You run GBrain on your own computer | **2. My local GBrain** | With your yes, it adds this repo's folder to your brain as one entry named `<project>-knowledge` and loads it. Nothing else in your brain changes; if that name is taken it stops and tells you | GBrain installed with a brain created |
| Your own GBrain runs on another computer or server | **3. My remote GBrain** | It shows the commands to run on that computer, where the brain's data lives. Your settings here stay as they are | Access to that computer |
| Your team runs a shared brain server | **4. Team brain** | The server's name, address and who hands out access are saved in the repo so every teammate sees them, after a quick check that the address answers like a brain (a mistyped brain name shows up here). Each person asks for their own read-only key, types it once into their own projectops settings, and says yes to the connection | A key from the team's brain admin |
| You do not have GBrain yet | **5. Install guide** | One question (only you on this computer, your own Postgres, Supabase, another machine, a team server), then the exact commands and a check that it worked. Commands with passwords are typed by you in a terminal | A few minutes |
| You do not have a brain yet | **5. Install guide** | It shows where to get GBrain, then works like 1 | Nothing now |

You can combine 2 or 3 with 4: your own brain for yourself, the team brain for shared answers. Keys and passwords are
never saved in the repo or in a note; the team brain is added under its own name so it never replaces your personal one.

## Where each fact lives

| Place | Shared? | Holds | Never holds |
|---|---|---|---|
| `version.yml` (`knowledge` block) | Yes, committed with the repo | Capture mode, folder, team brain name, address and who issues keys | Tokens, personal brains |
| `~/.projectops/config/config.json` | No, your computer only (mode 600) | Your team brain token under a name (credential store), your private registry | Anything a teammate needs to read |
| Claude Code MCP settings (`claude mcp add --scope user`) | No, your computer only | The registered brain entry, written by `connect --team` from the two places above | Nothing you edit by hand |
| `.mcp.json` (optional) | Yes, committed | The team brain entry with `${GBRAIN_<PROJECT>_TOKEN}` instead of a token | The token |

A new token (rotated by the admin, or a new computer) means one command to save it under the same name and one
`connect --team --rotate`; nothing in the repo changes.

**Which branch reaches the brain?** A brain reads the notes that are committed on the branch checked out in the folder it
reads. Pointing your personal brain at your working folder means notes appear as soon as you commit them, even before a
merge. To see only merged notes, keep a separate copy of the main branch for the brain and refresh it every hour; the
setup prints the exact commands.

## For the team brain admin (option 4)

1. Run a GBrain server that teammates can reach over HTTPS (for example `gbrain serve --http --public-url https://<host>`).
2. On that server, keep a copy of the repo's main branch and add its `knowledge/` folder as one source named
   `<project>-knowledge`; refresh and sync it every hour (`git pull`, then `gbrain sync --source <project>-knowledge`).
   Main only, so unfinished work never reaches the team.
3. Give each member their own **read-only** access key (for example `gbrain auth create <member> --scopes read`, or a
   client with the `memory-reader` profile; see GBrain's MCP admin guide). Hand it over privately and revoke it when someone
   leaves.
4. In the repo, run the setup once and pick 4 with the server's MCP name (for example `gbrain-<project>`), its address and
   who to ask for a key. The address is checked first; then it is saved in `version.yml`, so every teammate's setup shows
   the same instructions.
5. Each member saves their key once (`cred set --name gbrain-<project> --secret-field token --prompt`, typed in their own
   terminal) and says yes to `connect --team`, which registers the brain for them. `install --choice team-server` prints
   the server commands.

Optional: the same hourly job can log notes that were never written (`gaps`, see "Did anything slip through?").

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

Everything shared lives in the repo's `version.yml`, so the whole team shares it: the moment notes are written
(`capture`), the folder (`path`, `note_dir`), your own note template or vault rules (`template`, `rules`, `check`), the team
brain (`team_brain`: name, address, who issues keys) and kinds of work never worth a note (`skip`). A personal brain is
not written there: it is found on each computer. Without any of these keys the defaults just work. Details: `note-format.md`.

## Did anything slip through?

`gaps` lists work merged into the main branch since the last note that has no note yet. It only reads git history, so a
team brain's hourly sync job can log it for free. The agent then writes the missing notes or skips them with a reason.
