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

## What happens after you say yes (team)

```
brain server: create (or reuse) the project's brain ── repo: switch on, rule for agents, team brain name
      │                                                      │
this computer: copy of main's notes ── hourly sync ── registry note of where everything is
      │
final check: a temporary read-only key can search, cannot write, and stops working once revoked
```

- **Nothing is deleted.** Running it again (`repair`) only fills in what is missing and fixes permissions.
- **No secrets on screen.** Keys stay in your private settings file or files only you can read.
- **Your personal brain is untouched.** The team brain is a separate entry with its own name (`gbrain-<project>`).

## Giving a teammate access

`/pro-gbrain share` with their name creates a read-only key and a ready-to-send message (saved privately and copied to
your clipboard). Send it to them directly. They paste the key once in their terminal and run `/pro-brain`; from then on
their agent can search the team brain.

## Checking on it

`/pro-gbrain status` shows every team brain: is the server healthy, when did this computer last sync, and which merged
work still has no note.

## If you do not run your own brain server

Team mode still works: the skill shows the server steps for whoever runs your brain, then connects the repo to the
address they give you. See `provisioner-contract.md` if you want to automate your server too.
