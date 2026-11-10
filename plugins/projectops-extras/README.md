# projectops-extras

Optional plugin from the projectops marketplace. It holds skills that are not part of the core development cycle.

| Skill | Purpose |
|-------|---------|
| `pro-disk-cleanup` | Find and clear reclaimable disk space on any macOS, Windows or Linux machine, whatever the stack: a read-only scan first, then three tiers (safe after one confirmation, decide only when you name it, keep). Closed-issue worktrees are checked on GitHub, backed up and removed with branches kept; build output, tool caches, browser caches and Docker leftovers are cleared through one delete gate |
| `pro-orca-tunnel` | Give a public Orca Web URL on request: reuse the live cloudflared quick tunnel or open a new one, and return the saved Orca pairing link pointed at it. No Cloudflare account needed. Orca facts live in a harness the agent updates when Orca changes (macOS, Windows, Linux) |
| `pro-skill-bug` | Report a suspected projectops skill bug from the session where it happened: collect commands, tool results, flow, logs and screenshots from the transcript, strip personal data, file or update an issue on Cassiiopeia/projectops, then return to the task. It does not judge or fix |
| `pro-synology-expose` | Guide for exposing a web service on a Synology NAS under your own domain (DNS, reverse proxy, certificate) |

## Automatic bug reports (Claude Code)

The plugin's hook (`hooks/skill_bug_watch.py`) watches every projectops skill command. When a command fails and the agent then does the same job by hand (raw `adb`/`xcrun`, `gh` or the GitHub API, `git commit`, `git worktree add`, the Figma API), when the tool answers that it has no such feature, when the same argument error repeats, when the same failure repeats three times, or when a projectops script crashes, it asks the agent to run `pro-skill-bug` in the background: personal data is stripped and the issue is filed without asking (at most 3 per session). The issue carries the failed call's full result, every call around it, the commands that set up the state and the environment, so it can be reproduced from the issue alone. A toast shows the issue number when it lands (`hooks/skill_bug_notice.ts`, on Claude Code builds with function hooks).

To turn it off, add `"skill-bug": {"auto_report": false}` to `~/.projectops/config/config.json`. Cursor and Copilot installs get the skill only.

## Install

```bash
claude plugin marketplace add Cassiiopeia/projectops
claude plugin install projectops-extras@projectops-marketplace --scope user
```

`skills/references/` holds copies of shared docs from the core plugin. Do not edit them; run `python3 scripts/sync_extras.py` in the repository root (a test fails when they drift).
