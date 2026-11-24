---
type: issue-knowledge
id: "issue-1271"
title: "pro-gbrain attaches a repo to GBrain in one resumable, no-delete flow"
created: 2026-11-24
topics: ["gbrain", "pro-brain", "skills", "credentials", "security"]
status: active
related: ["[[issue-1265]]", "[[issue-1266]]"]
supersedes: []
source: "https://github.com/Cassiiopeia/projectops/issues/1271"
capture_mode: "issue-end"
captured_at: "2026-11-24T09:38:40+09:00"
captured_by: "pro-brain"
project: "projectops"
stacks: ["basic"]
app_version: "4.114.0"
build_number: 640
issue: 1271
issue_url: "https://github.com/Cassiiopeia/projectops/issues/1271"
pr: 1273
pr_url: "https://github.com/Cassiiopeia/projectops/pull/1273"
commit_base: "4532e37d2c3b1df82eaf801c3152b5bc579a734c"
commit_head: "c47d68ddbe32b48f667133eb4a9929396d8bee16"
commit_count: 1
merge_commit: "77f1b77b82b323367d5e49e9e4f9036bca48f6dd"
changed_modules: ["plugins", "docs", "(root)", ".claude-plugin", "scripts", "skills"]
main_files: ["plugins/projectops-extras/skills/pro-gbrain/scripts/gbrain_ops/commands.py", "plugins/projectops-extras/skills/pro-gbrain/scripts/gbrain_ops/credentials.py", "plugins/projectops-extras/skills/pro-gbrain/scripts/gbrain_ops/local_sync.py", "plugins/projectops-extras/skills/pro-gbrain/scripts/gbrain_ops/flows.py", "plugins/projectops-extras/skills/pro-gbrain/scripts/gbrain_ops/registry_store.py", "plugins/projectops-extras/skills/pro-gbrain/scripts/gbrain_ops/mcp_check.py", "plugins/projectops-extras/skills/pro-gbrain/SKILL.md", "plugins/projectops-extras/skills/pro-gbrain/scripts/gbrain_ops/common.py"]
lines_added: 2044
lines_deleted: 15
deploy_version: "4.115.0"
---

# pro-gbrain attaches a repo to GBrain in one resumable, no-delete flow

`/pro-gbrain` (extras) turns "attach gbrain to this project" into one question (alone or with the team) and ordered,
idempotent steps; `pro-brain` keeps owning the repo switch, notes and a member's MCP entry.

## Background
Attaching a repo needed work in five places (brain server, repo switch, the syncing machine, private registry, a final
read/write check). A manual run for one project was all ad-hoc agent orchestration and even recreated an empty database
without consent. pro-brain only covered the repo side.

## Decision
- **Separate skill, not more pro-brain modes.** pro-brain stays repo-local and teammate-safe; pro-gbrain is the owner's
  orchestration and calls pro-brain (`setup`, `connect`) as a subprocess. Rejected: folding server provisioning into
  pro-brain (it would mix owner infra into a skill every teammate runs).
- **Provisioner = registry entry + HTTP contract.** `infra.brains.<name>.kind: provisioner` holds references only
  (base URL, credential name). Owner hosts never enter the repo; other teams implement the contract or get manual steps.
- **dry_run is opt-in per server** (`supports_dry_run: true`). An older server that ignores the flag would create for real.
- **State file per project** (`~/.projectops/gbrain/<project>.json`): `add` resumes, `repair` re-runs everything.
- **No deletes anywhere.** `remove` renames `sync.sh` and flags the registry entry; server removal stays manual.

## Behavior
- team: server (create or adopt) > repo > local (sparse clone of the default branch, writer config 600, source,
  generated `sync.sh` 700) > registry (backup, missing keys only) > verify (throwaway read-only token: initialize 200,
  search, write refused, revoke then 401). own: repo > connect. repo-only: repo.
- `share` writes the teammate token to a 600 file and the clipboard, never to output.

## Code pointers
- `plugins/projectops-extras/skills/pro-gbrain/scripts/gbrain_ops/flows.py > execute()` (step order, state, stop on failure)
- `gbrain_ops/provisioner.py > ControlTowerProvisioner` (contract client), `> open_provisioner()`
- `gbrain_ops/local_sync.py > ensure_clone() / ensure_sync_script()`, template `gbrain_ops/templates/sync.sh.tmpl`
- `gbrain_ops/mcp_check.py > run_verification()` (revoke in `finally`)
- Contract doc: `pro-gbrain/references/provisioner-contract.md`

## Cautions
- gbrain 0.60 answers `sources add --json` with `id`, not `source_id`; pro-brain `gbrain_connect.apply()` now reads both.
  Check such keys against the real binary, not docs.
- The sync script pulls with git first, then `gbrain sync --no-pull`; letting gbrain pull too fails on some transports.
- launchd and cron start with a bare PATH: the generated script pins the folder where gbrain was found.
- `repair` replaces a hand-written `sync.sh` (old copy kept as `sync.sh.bak-<time>`).
- A writer role created before pro-gbrain has no stored password on a new machine: `writer_secret_missing`.
- The `local` step needs bash (macOS or Linux).

## Verification
Watch tests passed. Throwaway dry runs: repo-only, own brain (temp GBRAIN_HOME), team with a fake provisioner (repair x3
unchanged), manual team, status/share/remove; no secret in any output. Real server: read-only status and `verify` on an
existing team brain passed all four checks.

## Follow-ups
- Mark the provisioner `supports_dry_run: true` in the owner registry once the server ships dry_run.
