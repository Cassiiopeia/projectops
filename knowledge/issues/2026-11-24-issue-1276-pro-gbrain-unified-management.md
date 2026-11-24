---
type: issue-knowledge
id: "issue-1276"
title: "pro-gbrain is the single GBrain entry point; capture_events drives capture and mirrors capture"
created: 2026-11-24
topics: ["gbrain", "pro-brain", "skills", "config", "credentials"]
status: active
related: ["[[issue-1271]]", "[[issue-1265]]", "[[issue-1266]]"]
supersedes: []
source: "https://github.com/Cassiiopeia/projectops/issues/1276"
capture_mode: "issue-end"
captured_at: "2026-11-24T11:11:46+09:00"
captured_by: "pro-brain"
project: "projectops"
stacks: ["basic"]
app_version: "4.115.1"
build_number: 642
issue: 1276
issue_url: "https://github.com/Cassiiopeia/projectops/issues/1276"
pr: 1277
pr_url: "https://github.com/Cassiiopeia/projectops/pull/1277"
commit_base: "9ba239431117de3fc2548a9096e8eddbc3961f78"
commit_head: "7e9820e4e23b961baa03b5fb5b208994a5c02cd3"
commit_count: 1
merge_commit: "bb00a10e1d5c374da65b92502a22bbe3e289fcf9"
changed_modules: ["plugins", "skills", "(root)", "src"]
main_files: ["plugins/projectops-extras/skills/pro-gbrain/scripts/gbrain_ops/manage.py", "plugins/projectops-extras/skills/pro-gbrain/scripts/gbrain_ops/triggers.py", "plugins/projectops-extras/skills/pro-gbrain/scripts/gbrain_ops/runtime.py", "plugins/projectops-extras/skills/pro-gbrain/references/unified-management.md", "plugins/projectops-extras/skills/pro-gbrain/references/management-cli.md", "plugins/projectops-extras/skills/pro-gbrain/scripts/gbrain_ops/management_parser.py", "plugins/projectops-extras/skills/pro-gbrain/SKILL.md", "plugins/projectops-extras/skills/pro-gbrain/scripts/gbrain_ops/context.py"]
lines_added: 841
lines_deleted: 16
deploy_version: "4.116.0"
---

# pro-gbrain is the single GBrain entry point

## Summary
Users who do not know GBrain call only `/pro-gbrain`. It diagnoses (`manage doctor`), then installs, initializes, wires
Claude Code and Codex, indexes, searches, enables embeddings, makes local share HTML and sets capture moments. Every
mutation is a plan until `--apply --yes`; the work is delegated to the official GBrain CLI and to pro-brain.

## Decisions
- **One entry point, delegation, no reimplementation.** pro-gbrain orchestrates; GBrain does the work and pro-brain
  writes notes. Rejected: two user-facing skills (users must know which to call) and a rewrite (drifts with GBrain versions
  and duplicates #1272's resolver).
- **`capture_events` is the source of truth, `capture` is a mirror.** `triggers` writes both in one edit
  (report or issue-done > `issue-end`, else `merge`, `session-end`, `manual`). Rejected: a second independent switch, which
  would let pro-brain and old plugin versions read a different policy than pro-gbrain.
- **Same brain is judged from `setup --dry-run` `target.brain`**, not from MCP tool lists. A failed preview is `unknown`.
- **Not done is never reported as done.** Zero exit with held, blocked or resumable sources is a failure; `publish` gives
  local HTML only (`public_url: null`); `triggers` installs no CI or scheduler.

## Cautions
- Edit capture moments only through `triggers`. Editing `capture_events` or `capture` by hand splits their meaning.
- Until #1272 lands, pro-brain has no `write`: `event` writes the repo file only and reports `pending_commit_and_sync`.
  Do not describe that as brain delivery.
- `event` receipts live under the private state directory per project hash; a stale `.lock` is never broken
  automatically (`event_busy`). Inspect the runner first.
- Install source is `github:garrytan/gbrain#stable` via Bun; the npm package with the same name is unrelated.
- Scheduled runs lack the user's Bun bin on `PATH`; `common.run` resolves against the caller's `PATH` for that reason.
- Claude Code's existing hosted GBrain entry makes `setup claude-code --dry-run` refuse, so doctor shows it as `unknown`.

## Code pointers
- `gbrain_ops/manage.py > doctor()`, `recommend_next_steps()`, `summarize_harness_targets()`
- `gbrain_ops/triggers.py > configure()`, `legacy_capture_mode()`, `handle_event()`
- `gbrain_ops/runtime.py > run()`, `incomplete()`, `redact()`

## Verification
Watch tests passed (Node 43, Python 111). Scratch repo exercised triggers, skipped, written and noop events. Real
`manage doctor` on GBrain 0.60.739.0 returned Codex target, Claude Code unknown and one next step.

## Follow-ups
- Merge with #1272 (`write`, `doctor`) and re-check `event` delivery to local and team brains.
- Verify on Windows and Linux; verify a team server through `manage`.
