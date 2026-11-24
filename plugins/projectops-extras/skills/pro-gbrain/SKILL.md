---
name: pro-gbrain
description: "Attach a repo to GBrain in one command: detects the situation, asks one question (solo or team, recommended first), then sets up the repo, server brain, sync script, registry and an end-to-end check. Also status, repair, remove, share. Use for 'attach gbrain to this project', 'team brain status'."
---

# Attach a Repo to GBrain

## When to use

- "Attach gbrain to this project", "connect this repo to a brain", "make a team brain for this repo": **add**.
- "How are our brains doing?", "is the team brain syncing?": **status**. "The team brain is broken": **repair**.
- "Give <name> access to the team brain": **share**. "Detach this project from the brain": **remove**.
- Not this skill: writing a knowledge note (`pro-brain`), the user's personal memory, installing GBrain itself
  (`pro-brain` §Guided install covers that).

Reply in the user's language. The user needs to know nothing about GBrain: ask at most two questions (the mode, then one
"go ahead?" over the plan), each with the recommended answer first. Non-technical explanation: `references/how-it-works.md`.

## What it never does

- Deletes nothing: no database, role, source, clone, file or registry key. `remove` only disables this machine's sync
  script and flags the registry entry, after the user typed the project key.
- Prints no secret: the admin key, writer password and tokens stay in memory, the credential store or 600 files. `share`
  writes the teammate message to a private file (and the clipboard), never to the chat.
- Never touches the user's personal brain entries (the `gbrain` MCP entry, hooks, mounts, other sources), never pushes to
  a protected branch, never puts owner hosts or accounts in a repo. Owner-specific values live only in the private
  registry (`~/.projectops/config/config.json`, `project-blueprint` section).

## Find the scripts

```bash
PYTHON=$(for _py in python3 python; do _path=$(command -v "$_py" 2>/dev/null) || continue; "$_path" -c "import sys; sys.exit(0)" 2>/dev/null && echo "$_path" && break; done)
[ -z "$PYTHON" ] && { echo "Python not found"; exit 1; }
ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
SCRIPTS="$ROOT/plugins/projectops-extras/skills/pro-gbrain/scripts"
[ -d "$SCRIPTS" ] || for B in ~/.claude/plugins/cache ~/.codex/plugins/cache ~/.gemini/extensions ~/.pi/agent/git; do
  H=$(find "$B" -maxdepth 8 -type d -path "*/projectops-extras/*skills/pro-gbrain/scripts" 2>/dev/null | sort -V | tail -1)
  [ -n "$H" ] && { SCRIPTS="$H"; break; }
done
[ -d "$SCRIPTS" ] || { echo "pro-gbrain scripts not found. Check the projectops-extras installation."; exit 1; }
echo "PYTHON=$PYTHON SCRIPTS=$SCRIPTS"
```

Every command is `PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/gbrain_cli.py <command> ...` (Windows: `python`). Output is
always JSON (`ok`, `code`, `summary`, `next`). Decide by `code`, follow `next`.

## Commands

| Intent | Command | Writes |
|---|---|---|
| Look at the situation | `detect [--repo PATH] [--project KEY]` | no |
| Show the steps for a mode | `plan --mode team\|own\|repo-only [flow options]` | no |
| Attach (resumable) | `add --mode M --apply --yes [flow options]` | yes |
| Re-run every step (idempotent) | `repair --project KEY --apply --yes [--mode M] [--steps a,b]` | yes |
| All team brains at a glance | `status [--project KEY]` | no |
| End-to-end check only | `verify --project KEY` | throwaway token, revoked |
| Teammate access | `share --project KEY --member NAME [--apply --yes]` | private message file |
| Detach | `remove --project KEY [--apply --confirm KEY]` | renames sync.sh, flags registry |

Flow options: `--capture MODE`, `--claude-md add|decline`, `--contact WHO`, `--mcp-url URL --mcp-name NAME` (team brain
without a provisioner), `--no-first-sync`, `--steps a,b`.

## add, step by step

1. `detect`. Show in one or two lines: project key (and where it came from), default branch, own GBrain, brain server.
   If `project_from` is `folder name` and that looks wrong, ask for the key in the same question.
2. Ask **the one question** from `question` ("alone or with your team?"), `recommended` first with its `why`.
3. `plan --mode <answer>`. Show the steps, `repo_preview.version_yml_diff` / `block_diff`, and `server_preview` when
   present (what the server would create, adopt or re-grant). Ask "go ahead? (recommended)" once.
4. `add --mode <answer> --apply --yes`. On failure, show `summary` and `next` in plain words; after the fix run `add`
   again (finished steps are skipped) or `repair` to redo everything.
5. Commit the repo changes (`version.yml`, rule block) with `pro-commit` on an issue branch and open a PR per the repo's
   rules. Never push to a protected branch.
6. Report briefly: what was set up, where the sync runs, and for a team brain the `share` line for each teammate.

| Mode | Steps |
|---|---|
| `repo-only` | `repo`: pro-brain setup (capture on, rule block) |
| `own` | `repo`, then `connect`: one source `<project>-knowledge` in your own GBrain |
| `team` | `server` (provisioner creates or adopts the brain) > `repo` (switch + team brain name/URL) > `local` (sync folder, writer config 600, source, `sync.sh` 700, first sync) > `registry` (backup, add missing keys) > `verify` |

The `local` step runs on the machine that writes the team brain (macOS or Linux: the sync script is bash). On other
machines run `add --steps server,repo,registry,verify` and let the writer machine run `repair --steps local`.

### Codes

| `code` | Do |
|---|---|
| `manual_server_steps` | No brain server configured: show `server_steps` to the brain admin; continue with `--mcp-url --mcp-name` |
| `provisioner_credential_missing` | The user stores the admin key in a terminal with the shown command (never in chat) |
| `provisioner_unreachable` / `provisioner_auth_failed` | Network or VPN, or a wrong admin key; nothing changed |
| `team_database_not_empty_unknown` | The server refused to adopt a database with unknown data; the brain admin checks it. Nothing was dropped |
| `writer_secret_missing` | The writer role existed before; get its password from the brain admin into the shown 600 file, then `repair` |
| `sync_database_unreachable` | Start the database tunnel to the brain server, then `repair` |
| `sync_clone_mismatch` / `sync_folder_not_empty` / `source_id_taken` | Something else already lives there; nothing was changed. Report it |
| `verify_failed` | Read `verification.checks`; `write_refused.passed: false` is serious (token can write): report `probe_slug` |
| `needs_consent` / `confirmation_mismatch` | Ask, then re-run with `--apply --yes` (remove: `--confirm <project>` typed by the user) |

## status, repair, share, remove

- **status** lists every team brain from the registry and the brain server: registry switch, server health, this
  machine's sync folder, `last_sync` and the last gaps lines. A brain on the server but not in the registry shows
  `in_registry: false`: report it, do not adopt it silently.
- **repair** re-runs all steps of the recorded mode. Safe on a working brain: the server re-applies grants, existing
  files are kept, a hand-edited `sync.sh` is kept as `sync.sh.bak-<time>` before the generated one is written.
- **share** issues one read-only token per teammate (name = token label) into
  `~/.projectops/gbrain/share/<project>-<member>-<time>.txt` (600) and the clipboard. Tell the user to send it one to one
  and delete the file. The teammate then runs `/pro-brain` (team brain connection).
- **remove** shows what stays (server brain, data, clone, notes) and what changes, asks the user to type the project key,
  then `remove --apply --confirm <key>`. Server-side removal is the brain admin's manual job.

## Brain server (provisioner)

Team mode automates the server only when the private registry declares a provisioner; everyone else gets the manual
steps. The registry shape, the HTTP contract a brain server must speak and how another team plugs in their own:
`references/provisioner-contract.md`.

## Shared references

| Document | Read when |
|---|---|
| `references/how-it-works.md` | The owner asks how it works or which mode fits |
| `references/provisioner-contract.md` | Setting up a brain server, the registry entry, or debugging server codes |
| `../pro-brain/SKILL.md` | The repo side (switch, rule block, notes) and a member's team brain connection |
| `../references/config-rules.md` | Reading or editing the private registry by hand (§7 `project-blueprint`, §9 credentials) |

## Customize

Your own language, tone and rules apply: see `../references/preferences.md`. Read them once at the start: run the snippet in `../references/preferences.md` with `SKILL_ID=pro-gbrain`.
Keys for this skill: the common `language`, `tone`, `rules` only. Preferences change presentation only; the no-delete,
no-secret-output and consent rules stay in force.
