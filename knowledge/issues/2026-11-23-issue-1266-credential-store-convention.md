---
type: issue-knowledge
id: "issue-1266"
title: "Every skill secret lives in the credential store and is referenced by name"
created: 2026-11-23
topics: ["credentials", "config", "skills", "security"]
status: active
related: ["[[issue-1265]]"]
supersedes: []
source: "https://github.com/Cassiiopeia/projectops/issues/1266"
capture_mode: "issue-end"
captured_at: "2026-11-23T14:51:10+09:00"
captured_by: "pro-brain"
project: "projectops"
stacks: ["basic"]
app_version: "4.113.0"
build_number: 639
issue: 1266
issue_url: "https://github.com/Cassiiopeia/projectops/issues/1266"
pr: 1267
pr_url: "https://github.com/Cassiiopeia/projectops/pull/1267"
branch: "20261123_#1266_One_credential_convention_for_every_skill_store_accessor_references_by_name"
commit_base: "633226bcf5909b1862749c995e80cc4cb814f8f4"
commit_head: "213ea482e24dab0e9ed4557ec7b2e9b3cd20ec65"
commit_count: 1
changed_modules: ["skills", "scripts", "(root)", "docs", "plugins"]
main_files: ["scripts/common/credentials.py", "skills/pro-launch/scripts/pro_launch/commands/cred.py", "skills/pro-launch/scripts/credentials.py", "plugins/projectops-extras/skills/references/config-rules.md", "skills/references/config-rules.md", "scripts/common/config.py", "skills/config.json.example", "skills/pro-launch/references/credentials.md"]
lines_added: 425
lines_deleted: 46
---

# Every skill secret lives in the credential store and is referenced by name

A skill that needs a secret stores it as a named entry in `config.json` `launch.credentials` and reads it only through `scripts/common/credentials.py`; other config sections hold just the name.

## Background
Secrets had grown four homes: `github.global_pat` / `repos[].pat`, pro-launch `launch.credentials`, secret-adjacent
`project-blueprint.infra.*`, and pro-brain team brain tokens that lived only inside Claude Code's MCP config. Every new
skill re-decided where its secret goes, and agents went hunting for config files.

## Decision
- Reuse the existing pro-launch store as the single credential store (key kept as `launch.credentials` for
  compatibility) because it already had masking, mode 600 atomic writes and name rules. Rejected: a new `secrets`
  section (a fifth location and a migration for every existing entry).
- References by key name: `credential`, or a key ending `_cred` / `_credential` (`token_cred`,
  `github.global_pat_cred`). A read-only `cred check` can then find every reference without a per-skill registry.
- The accessor is standard library only with no module-level `common` import, so extras skills ship a generated
  copy (`scripts/sync_extras.py`) instead of a hand copy.
- `github.global_pat` stays the first read path; migration (`cred migrate-github-pat --yes`) is optional and needs
  the user's yes, because older projectops releases read only `global_pat`.

## Behavior change
- `launch_cli.py cred check`, `cred migrate-github-pat [--yes]`, `cred set --secret-field F --prompt|--from-env VAR`.
- `get_github_pat` falls back to `github.global_pat_cred` when `global_pat` is empty.

## Code pointers
- `scripts/common/credentials.py > read_secret()`, `save_secret()`, `check_credential_references()`, `apply_github_pat_migration()`
- `scripts/common/config.py > get_github_pat()`
- `skills/pro-launch/scripts/pro_launch/commands/cred.py > _cred_check()`, `_cred_migrate_github_pat()`, `_secret_from_input()`
- Rules: `skills/references/config-rules.md` §9; checklist: `ARCHITECTURE.md` "How to add a skill" #9

## Cautions
- Never print a value: outputs carry names and paths only. A secret value never goes through argv or chat; use `--prompt` (TTY) or `--from-env`.
- Editing `scripts/common/credentials.py` means re-running `python3 scripts/sync_extras.py` (pro-brain copy).
- A broken `config.json` is never overwritten (`config_unreadable`).
- "Unreferenced" in `cred check` is not "unused": pro-launch commands take names directly with `--cred`.

## Verification
- `npm test` 43 passed, `pytest scripts/tests/ .github/scripts/test/` 111 passed; temporary-HOME smoke run showed no secret in any output.

## Links
- Issue https://github.com/Cassiiopeia/projectops/issues/1266, PR https://github.com/Cassiiopeia/projectops/pull/1267, report https://github.com/Cassiiopeia/projectops/issues/1266#issuecomment-7092569960
