---
type: issue-knowledge
id: "issue-1285"
title: "Team brain verify counts tools granted by request_tools and probes writes with put_page"
created: 2026-11-26
topics: ["gbrain", "mcp", "pro-gbrain"]
status: active
related: ["[[issue-1282]]", "[[issue-1272]]"]
supersedes: []
source: "https://github.com/Cassiiopeia/projectops/issues/1285"
pr: 1287
pr_url: "https://github.com/Cassiiopeia/projectops/pull/1287"
deploy_version: "4.120.1"
capture_mode: "issue-end"
captured_at: "2026-11-26T19:44:39+09:00"
captured_by: "pro-brain"
project: "projectops"
stacks: ["basic"]
app_version: "4.120.0"
build_number: 649
issue: 1285
issue_url: "https://github.com/Cassiiopeia/projectops/issues/1285"
commit_base: "6c4b5d1aa3ee3d114bf975e18cc2bfaff08a64fc"
commit_head: "1fb5033af0d98853ddfcf6ce9655389c6a3f17a6"
commit_count: 1
changed_modules: ["plugins", "skills"]
main_files: ["plugins/projectops-extras/skills/pro-gbrain/scripts/gbrain_ops/mcp_check.py", "skills/pro-launch/scripts/pro_launch/commands/http.py", "plugins/projectops-extras/skills/pro-gbrain/SKILL.md", "plugins/projectops-extras/skills/pro-gbrain/references/provisioner-contract.md"]
lines_added: 77
lines_deleted: 11
---

# Team brain verify write probe

## Summary
`gbrain_cli.py verify` reported `write_allowed: false` on a team brain that accepted writes. The probe now uses `put_page` after `request_tools` grants it, and a refused write carries the server's reason.

## Background
gbrain servers with a starter surface list only everyday tools. `request_tools` makes more tools callable, but `tools/list` does not list them afterwards. The probe trusted only the listing, fell back to `remember`, and called it without `provenance`, which current gbrain requires. The resulting tool error was read as "refused".

## Decisions
- **The answer of `request_tools` is the source of truth for granted tools**, merged with a fresh listing. Same rule pro-brain's doctor already used; the two probes had drifted apart.
- **Prefer `put_page` over `remember`**: a page on a fixed slug can be overwritten or deleted; a remembered fact cannot be cleaned up by the probe.
- **Read the revision first** when the probe page is left from an earlier run (no delete tool), because `put_page` on an existing page needs `expected_revision`.
- **A failed write shows `detail`** (the server's text, token masked, 200 characters) so "refused" and "bad call" can be told apart.
- `launch http` got its own User-Agent: Cloudflare refuses `Python-urllib` with error 1010.

## Code pointers
- `plugins/projectops-extras/skills/pro-gbrain/scripts/gbrain_ops/mcp_check.py` > `_unlock_tools()`, `_write_probe_arguments()`, `_probe_page_revision()`
- `plugins/projectops-extras/skills/pro-brain/scripts/brain/adapters/write_probe.py` > the sibling probe (keep the two in step)
- `skills/pro-launch/scripts/pro_launch/commands/http.py` > `DEFAULT_USER_AGENT`

## Cautions
- A tool error is not proof of a refusal. When gbrain adds a required argument to `put_page` or `remember`, both probes fail the same way again: read `detail` first.
- Sync mode passes when the write errors, so a malformed probe call would hide a read-only token that can write. Keep the arguments valid.
- The reported `launch http --cred` 401 was not reproduced; the Bearer header is built from a `token` field.

## Verification
- `verify --project secbrief --write direct` on the real server: failed before, `verified` after.
- A fake starter-surface server covered write and read-only tokens in both modes and a second run over a leftover page.
