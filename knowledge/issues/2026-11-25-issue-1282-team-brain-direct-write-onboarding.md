---
type: issue-knowledge
id: "issue-1282"
title: "Team brain onboarding defaults to direct writes, accepts an existing server and stores tokens without a terminal"
created: 2026-11-25
topics: ["pro-brain", "gbrain", "credentials", "security", "mcp", "windows"]
status: active
related: ["[[issue-1272]]", "[[issue-1271]]", "[[issue-1276]]", "[[issue-1265]]"]
supersedes: []
source: "https://github.com/Cassiiopeia/projectops/issues/1282"
pr: 1283
pr_url: "https://github.com/Cassiiopeia/projectops/pull/1283"
deploy_version: "4.119.0"
capture_mode: "issue-end"
captured_at: "2026-11-25T09:09:35+09:00"
captured_by: "pro-brain"
project: "projectops"
stacks: ["basic"]
app_version: "4.118.0"
build_number: 647
issue: 1282
issue_url: "https://github.com/Cassiiopeia/projectops/issues/1282"
commit_base: "cefe8eb8ed2d7448c56769c19b6b63a4f42b6e90"
commit_head: "f338e0cb281060b05903c3fda5c579e059cb8f5c"
commit_count: 1
merge_commit: "bb27be44265bb3c7ff6e565bde6487a8cdf21719"
changed_modules: ["plugins", "skills", "scripts"]
main_files: ["plugins/projectops-extras/skills/pro-gbrain/scripts/gbrain_ops/registry_commands.py", "skills/pro-launch/scripts/pro_launch/runtime/secret_input.py", "plugins/projectops-extras/skills/pro-brain/scripts/brain/setup_team.py", "plugins/projectops-extras/skills/pro-gbrain/scripts/gbrain_ops/commands.py", "plugins/projectops-extras/skills/pro-brain/scripts/brain/adapters/write_probe.py", "plugins/projectops-extras/skills/pro-gbrain/scripts/gbrain_ops/teammate_kit.py", "plugins/projectops-extras/skills/pro-gbrain/SKILL.md", "plugins/projectops-extras/skills/pro-gbrain/scripts/gbrain_ops/mcp_check.py"]
lines_added: 1179
lines_deleted: 207
---

# Team brain direct-write onboarding

## Summary
A field onboarding onto an admin-managed team gbrain server (one brain per project, per-member keys, `/team/<key>/mcp`) exposed eight gaps. Setup now asks the team model first. It accepts an existing server by base URL plus key and confirms write access by really writing. Tokens can be stored without a TTY, and each concern lives in one owner skill.

## Decisions
- **Ask the team model first, recommend `direct`.** `--team-model direct` = team only, `write: direct`, `repo_notes: false`, and `path` dropped from the switch. Existing switches with no `write` still read as `sync`, so running teams do not change. Rejected: flipping the default for everyone, because sync teams rely on read-only member tokens.
- **Owner split.** pro-brain = notes and repo switch; pro-gbrain = brains, servers, tokens, members; launch = secret input. pro-gbrain reads the project key through `repo_facts.team_brain_project_key()` instead of a copy.
- **Project key priority**: `--project` > team brain key in `version.yml` (`/team/<key>/` or `gbrain-<key>`) > registry > folder name. The field case had three different keys for one project.
- **doctor proves write access with a reversible probe** on a fixed slug (`pro-brain/<project>/_doctor`), because `surface=starter advertise=verbs` servers list write tools only after `request_tools`. A fixed slug means no pile-up when the server has no delete tool (`cleanup: left`).
- **Validate before reading a secret.** `cred set` checks every argument before it reads a file, the clipboard or the prompt, and before it deletes the source file. In the field, a Windows `--json` split failed after the token file was gone.

## Behavior change
- `setup --team-server URL --team-key KEY`, `--team-model direct|sync`, `install --choice existing-team-server`; `needs_version_yml` when the file is missing, and the options levels are created when only they are missing.
- pro-gbrain `add|plan|repair --write direct` (no local sync step, verify expects writes allowed), `share --scope read_write` plus one teammate kit file (600), `registry add-provisioner|import|export`, `provisioner_hint` when nothing is registered.
- `launch cred set --from-file PATH --delete-after | --from-clipboard | --json-file`; `--prompt` without a TTY gives `no_tty`.

## Code pointers
- `plugins/projectops-extras/skills/pro-brain/scripts/brain/setup_team.py` > team model and server URL derivation
- `plugins/projectops-extras/skills/pro-brain/scripts/brain/adapters/write_probe.py` > reversible write probe
- `plugins/projectops-extras/skills/pro-brain/scripts/brain/repo_facts.py` > `team_brain_project_key()`
- `plugins/projectops-extras/skills/pro-gbrain/scripts/gbrain_ops/teammate_kit.py`, `registry_commands.py`, `repo_switch.py`
- `skills/pro-launch/scripts/pro_launch/runtime/secret_input.py` > argument check, then read, store, delete

## Cautions
- Secrets pasted into chat cannot be unsent. Agents say once that the value is exposed and give the rotate steps, never echo it. Server guide pages that bundle the raw key are the usual source.
- Changing the project key changes note slugs when the registry key differs from the team brain key. Old pages are not moved.
- The Windows clipboard path and the real PowerShell `--json` split were not run on Windows (the split was reproduced only through argparse).
- Hints for a missing credential come from `scripts/common/credentials.py`; run `scripts/sync_extras.py` after changing it (the extras copies are generated).

## Verification
- Watch tests and compileall pass. An isolated HOME end-to-end run covered direct setup on a repo without an options block, the `seoulit` key resolved from `version.yml`, and `cred set --from-file --delete-after` and `no_tty`. Fake MCP and provisioner servers covered all four probe outcomes and direct and sync verify.

## Follow-ups
- Run the clipboard and `--json-file` paths on a real Windows machine.
