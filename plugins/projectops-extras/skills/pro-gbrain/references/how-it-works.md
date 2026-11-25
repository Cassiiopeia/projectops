# How /pro-gbrain works (for owners, no technical background needed)

## The idea in one paragraph

Your repo keeps short notes about decisions in a `knowledge/` folder (written by `/pro-brain`). A "brain" (GBrain) reads
those notes so that you and your agents can ask "why did we do this?" and get an answer with sources. `/pro-gbrain` is the
one command that connects the two: you say "attach gbrain to this project", answer one question, say yes once, and it
does the rest.

## The one question: alone or with your team?

| Answer | What you get | Good for |
|---|---|---|
| **With my team** | A separate brain for this project on your team's brain server. Only the notes from the repo's main branch go in. Teammates read it with their own read-only key | Repos more than one person works on |
| **Alone, in my own GBrain** | This repo's notes become one more source in your personal brain | Solo projects, when you already use GBrain |
| **Notes in the repo only** | Notes stay in the repo; no brain yet | Trying it out, or no GBrain at all |

The skill recommends one answer from what it sees (people committing, a brain server in your settings, GBrain installed).

For a team brain it asks one more thing: **do members write directly, or through the repo?**

| Answer | What happens | Good for |
|---|---|---|
| **Everyone writes directly** (`direct`) | Each member gets a read and write key; finished-issue notes go straight into the team brain, nothing is committed, no sync computer | Small teams (recommended) |
| **Through the repo** (`sync`) | Notes are committed to `knowledge/`; one computer imports the main branch hourly; members get read-only keys | Teams that review notes in PRs |

## What happens after you say yes (team, through the repo)

```
brain server: create (or reuse) the project's brain ── repo: switch on, rule for agents, team brain name
      │                                                      │
this computer: copy of main's notes ── hourly sync ── registry note of where everything is
      │
final check: a temporary read-only key can search, cannot write, and stops working once revoked
```

With `direct` the "copy of main's notes" and "hourly sync" parts are skipped, and the final check uses a temporary read
and write key: it must be able to write a test page, which is removed again.

- **Nothing is deleted.** Running it again (`repair`) only fills in what is missing and fixes permissions.
- **No secrets on screen.** Keys stay in your private settings file or files only you can read.
- **Your personal brain is untouched.** The team brain is a separate entry with its own name (`gbrain-<project>`).

## Giving a teammate access

`/pro-gbrain share` with their name creates a key (read and write for `direct`, read-only for `through the repo`) and one
ready-to-send kit (saved privately and copied to your clipboard): the key, how to store it, which branch has the project
rule, the `/pro-brain` line to connect, and the check to run after restarting. Send it to them directly, never in a group
or AI chat. From then on their agent can search (and, for `direct`, write to) the team brain.

## Checking on it

`/pro-gbrain status` shows every team brain: is the server healthy, when did this computer last sync, and which merged
work still has no note.

## If you do not run your own brain server

Team mode still works: the skill shows the server steps for whoever runs your brain, then connects the repo to the
address they give you. See `provisioner-contract.md` if you want to automate your server too.
