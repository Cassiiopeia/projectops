---
type: issue-knowledge
id: "issue-1265"
title: "Team brain tokens are stored per member and registered with pro-brain connect --team"
created: 2026-11-23
topics: ["pro-brain", "gbrain", "mcp", "credentials"]
status: active
related: ["[[issue-1266]]"]
supersedes: []
source: "https://github.com/Cassiiopeia/projectops/issues/1265"
capture_mode: "issue-end"
captured_at: "2026-11-23T14:51:10+09:00"
captured_by: "pro-brain"
project: "projectops"
stacks: ["basic"]
app_version: "4.113.0"
build_number: 639
issue: 1265
issue_url: "https://github.com/Cassiiopeia/projectops/issues/1265"
pr: 1268
pr_url: "https://github.com/Cassiiopeia/projectops/pull/1268"
branch: "20261123_#1265_Guided_gbrain_install_init_token_in_config_json_auto_MCP_registration_and_mcp_json_sh"
commit_base: "213ea482e24dab0e9ed4557ec7b2e9b3cd20ec65"
commit_head: "939408d9ea890b8d64028389db7aa1786621f4a1"
commit_count: 1
changed_modules: ["plugins", "docs", "(root)", "scripts"]
main_files: ["plugins/projectops-extras/skills/pro-brain/scripts/brain/credentials.py", "plugins/projectops-extras/skills/pro-brain/scripts/brain/team_connect.py", "plugins/projectops-extras/skills/pro-brain/scripts/brain/install_guide.py", "plugins/projectops-extras/skills/pro-brain/scripts/brain/mcp_probe.py", "plugins/projectops-extras/skills/pro-brain/SKILL.md", "plugins/projectops-extras/skills/pro-brain/scripts/brain/commands.py", "plugins/projectops-extras/skills/pro-brain/references/how-it-works.md", "plugins/projectops-extras/skills/pro-brain/scripts/brain_cli.py"]
lines_added: 724
lines_deleted: 37
---

# Team brain tokens are stored per member and registered with pro-brain connect --team

A member stores their team brain token once in the credential store and `brain_cli.py connect --team` registers the
user-scope Claude Code MCP entry from `version.yml` `team_brain` plus that token, after a yes.

## Background
Connecting secbrief to its team brain took a long back-and-forth: no install guide, a `claude mcp add` line pasted
by hand on every machine, no home for the token (earlier rule: "tokens are never stored"), and a mistyped brain key
(`secbreif`) in the owner's control panel that nothing caught.

## Decision
- Owner decision A = yes: the token lives in each member's personal config, in the credential store from issue 1266
  (`gbrain-<project>`, referenced by `infra.brains.<name>.token_cred` or defaulting to the MCP name). Rejected: a
  new token field in `project-blueprint` (a fourth secret location).
- Registration runs `claude mcp add --scope user --transport http` with the token as a short-lived argv element of that
  child only, because Claude Code's `mcp add` takes headers on the command line only; every printed line shows `<token>`.
- The URL probe uses two MCP initialize calls (no token, dummy token): 401/401 means a brain answers, 404 means an
  unknown brain. It sends a named User-Agent because Cloudflare in front of the owner's server answered 403 to Python's default agent.
- `install` only guides (one question, commands, verification) and never runs `gbrain init`/`serve`, which take
  connection strings and keys the user must type.
- `.mcp.json` is optional and holds `${GBRAIN_<PROJECT>_TOKEN}`; a project entry overrides a user entry of the same name.

## Behavior change
- `connect --team [--rotate] [--token-cred] [--project-mcp-json] [--no-probe]`, `install [--choice]`, `setup --no-probe`; a new `--team-brain-url` in setup is probed.

## Code pointers
- `plugins/projectops-extras/skills/pro-brain/scripts/brain/team_connect.py > plan()`, `apply()`, `plan_project_mcp_json()`
- `plugins/projectops-extras/skills/pro-brain/scripts/brain/mcp_probe.py > probe_team_brain()`
- `plugins/projectops-extras/skills/pro-brain/scripts/brain/install_guide.py > guide()`
- `plugins/projectops-extras/skills/pro-brain/scripts/brain/commands.py > _connect_team()`
- Where each fact lives: `plugins/projectops-extras/skills/pro-brain/references/how-it-works.md`

## Cautions
- `brain/credentials.py` is generated from `scripts/common/credentials.py`; never edit the copy.
- gbrain flags in `install_guide.py` follow gbrain 0.60 help; recheck them when gbrain changes its CLI.
- Team brain MCP name must never be `gbrain` (the personal entry).

## Verification
- Fake `claude` binary + temporary HOME run through every plan code and rotate: token count in output 0. Real probe of
  the secbrief team brain URL: correct key `brain_answers`, typo `secbreif` `unknown_brain`.

## Links
- Issue https://github.com/Cassiiopeia/projectops/issues/1265, PR https://github.com/Cassiiopeia/projectops/pull/1268, report https://github.com/Cassiiopeia/projectops/issues/1265#issuecomment-7092783054
