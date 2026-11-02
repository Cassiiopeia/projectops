# {{name}} harness

{{description}}

A **guide the agent follows while making its own decisions**. Helper scripts only cut repeated clicks. If the screen changed or a result looks wrong, do not insist on a script: check with `web text` · `web find` (apps: `app tree`, desktop windows: `desktop tree`) and continue.
Never write passwords or tokens in this folder. Accounts go in `cred`.

## Summary

- Target: {{targets}}
- Goal in one line:
- Context and past decisions: `launch_cli.py journal --site <part of the address>`

## Goal

What this work is for and when it counts as done.

## Loop

| Step | What to do | Human check |
|---|---|---|
| 1 |  |  |

## Decision points (human check)

- Ask the user before anything that cannot be undone (submit · delete · exclusion request, etc.).

## Access

- Address (apps: package name / bundle ID, desktop: window title):
- Account: `--cred <name>`
- Pitfalls such as certificates or session expiry:

## Step notes

## API notes

Calls you can make instead of the screen, request and response shapes.

## When stuck

| Symptom | Check | Fix |
|---|---|---|
|  |  |  |

## Files

| File | Role |
|---|---|
| `README.md` | This guide |
| `harness.json` | Description and auto-surface rules (`match.hosts` · `match.urls` · `match.apps` · `match.windows` · `areas`) |
