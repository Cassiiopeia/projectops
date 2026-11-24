---
type: issue-knowledge
id: "issue-1272"
title: "pro-brain writes each note directly to the chosen destinations through one resolver and adapters"
created: 2026-11-24
topics: ["pro-brain", "gbrain", "config", "credentials", "windows"]
status: active
related: ["[[issue-1276]]", "[[issue-1271]]", "[[issue-1265]]", "[[issue-1266]]"]
supersedes: []
source: "https://github.com/Cassiiopeia/projectops/issues/1272"
capture_mode: "issue-end"
captured_at: "2026-11-24T17:45:21+09:00"
captured_by: "pro-brain"
project: "projectops"
stacks: ["basic"]
app_version: "4.117.2"
build_number: 646
issue: 1272
issue_url: "https://github.com/Cassiiopeia/projectops/issues/1272"
pr: 1281
pr_url: "https://github.com/Cassiiopeia/projectops/pull/1281"
commit_base: "4532e37d2c3b1df82eaf801c3152b5bc579a734c"
commit_head: "a0d345e5da6ee0a5917db85fc2f92f0bbc18b245"
commit_count: 3
changed_modules: ["plugins", "docs", "(root)", "scripts", "src"]
main_files: ["plugins/projectops-extras/skills/pro-brain/scripts/brain/adapters/gbrain_local.py", "plugins/projectops-extras/skills/pro-brain/scripts/brain/adapters/gbrain_remote.py", "plugins/projectops-extras/skills/pro-brain/scripts/brain/commands.py", "plugins/projectops-extras/skills/pro-brain/scripts/brain/dest_commands.py", "plugins/projectops-extras/skills/pro-brain/scripts/brain/resolver.py", "plugins/projectops-extras/skills/pro-brain/references/note-format.md", "plugins/projectops-extras/skills/pro-brain/scripts/brain/github_facts.py", "plugins/projectops-extras/skills/pro-brain/scripts/brain/mcp_http.py"]
lines_added: 2266
lines_deleted: 216
env_or_secret_names: ["GBRAIN_HOME", "PRO_BRAIN_GBRAIN", "PATH", "PROJECTOPS_HOME", "GITHUB_PAT"]
deploy_version: "4.118.0"
---

# pro-brain writes notes directly to chosen destinations

## Summary
Notes go to any mix of repo files, the local gbrain and remote gbrains over HTTP MCP. One resolver reads the repo switch (shared), then the private config (personal), then the credential store (tokens by name). `write` is idempotent per destination (slug `pro-brain/<project>/<id>`, revision checked), and `doctor` names the failing check and its fix per destination.

## Decisions
- **"Team brain" is not a category.** It is a remote gbrain the team shares. `team_brain.write: sync | direct` says whether members write directly or only read a folder synced elsewhere.
- **Shared vs personal storage.** Shared destinations live in `version.yml`, personal ones in `~/.projectops/config/config.json` (mode 600), tokens only in the credential store. Rejected: keeping personal destinations in the repo, because teammates would inherit one person's brain.
- **Adapters behind one interface.** A new engine is one file plus one registry line.
- **Write scope is settled with `request_tools(put_page)`.** A read token gets an empty list, a write token gets the tool. A tool list alone cannot tell them apart, because GBrain hides `put_page` behind `request_tools`.

## Cautions
- **Never probe a PID with signal 0 on Windows: it terminates the process.** Use `proc.pid_alive`; the copy comes from `scripts/sync_extras.py`. Rule `no-os-kill-probe` also matches comments, so do not write the call literally even there.
- GBrain 0.60's PGlite owner file is `{"protocol":"kernel-v1"}` with no pid. The OS file lock decides, so a missing pid is normal.
- Read notes as `utf-8-sig`: PowerShell 5.1 `Set-Content -Encoding UTF8` and Windows editors add a BOM that hides the frontmatter.
- The repo copy is replaced only if it matches the last commit (CRLF ignored) or the last `write` (receipt in `{PROJECTOPS_HOME}/pro-brain/written/`). Otherwise the result is `note_edited`.
- To test without touching the real brain, set `HOME`, `GBRAIN_HOME` and `PRO_BRAIN_GBRAIN`. On Windows, set `USERPROFILE` too.
- The Windows test host drops rapid SSH connections. Send one script over stdin in a single session instead of the chunked upload.

## Code pointers
- `scripts/brain/resolver.py > resolve()`
- `scripts/brain/dest_commands.py > cmd_write()`, `cmd_doctor()`
- `scripts/brain/adapters/repo_files.py > _is_safe_to_replace()`
- `scripts/brain/adapters/gbrain_remote.py > _probe_write_tool()`
- `scripts/brain/adapters/gbrain_local.py > pglite_lock()`

## Verification
macOS: an isolated PGlite brain and a real `gbrain serve --http` with write and read tokens covered every outcome, plus brain-only gaps, the legacy switch and pro-gbrain events. Windows: cp949, a Korean path and BOM notes, end to end. Watch tests passed.
