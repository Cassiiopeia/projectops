---
name: pro-gbrain
version: 2.0
description: "Manage GBrain installation, harness connections, credentials, capture triggers, ingestion, search, embeddings and publication through one entry point. Attach repos, diagnose and repair connections, share access and detach safely."
---

# Manage GBrain

## When to use

- Install or configure GBrain, connect Claude Code or Codex, save or summarize project knowledge, configure ingestion triggers, search, embeddings, or publish a document: follow `references/unified-management.md`. Stay in this skill and invoke the appropriate executor internally.

- "Attach gbrain to this project", "connect this repo to a brain", "make a team brain for this repo": **add**.
- "How are our brains doing?", "is the team brain syncing?": **status**. "The team brain is broken": **repair**.
- "Give <name> access to the team brain": **share**. "Detach this project from the brain": **remove**.
- Knowledge note writing delegates to `pro-brain`; installation starts with its guided recipe and executes authorized steps. Preserve unrelated personal memory.
- "Our team already runs a brain server", "register the brain server on this machine": **registry add-provisioner** or
  **registry import**.

## Which skill owns what

| Skill | Owns | Hand off with |
|---|---|---|
| `pro-brain` | Notes, the repo switch (`version.yml` knowledge block), the rule block, a member's own MCP connection, `doctor` | `brain_cli.py setup`, `connect --team`, `doctor --to team` |
| `pro-gbrain` (this one) | Brains, brain servers, the private registry, member keys, sync machines | `gbrain_cli.py add`, `share`, `registry`, `status` |

"Connect this repo to the team brain" starts here (`detect` > `add`); `add` runs pro-brain setup for the repo part.
"Give my teammate access" is `share`; the teammate's own connection is pro-brain `connect --team`.

Reply in the user's language. The user needs to know nothing about GBrain: ask at most three questions (the mode, the
team write model when the answer is team, then one "go ahead?" over the plan), each with the recommended answer first.
Non-technical explanation: `references/how-it-works.md`.

## Secrets pasted into the chat

When a token-shaped value, an admin key or a `postgresql://user:pass@` string appears in the conversation (for example an
admin page's "copy the whole guide" text), say once, plainly, that it is now exposed and should be replaced. Never repeat
it, never store it from the chat, and never use it. Rotate steps: issue a new key (brain server admin page, or
`share --project KEY --member NAME --apply --yes`), revoke the old one there, store the new one with `launch cred set`
(`--prompt` in a separate terminal or `--from-file FILE --delete-after`), then `brain_cli.py connect --team --rotate`.
A leaked database password is rotated by the brain admin on the server.

## What it never does

- Deletes nothing: no database, role, source, clone, file or registry key. `remove` only disables this machine's sync
  script and flags the registry entry, after the user typed the project key.
- Prints no secret: the admin key, writer password and tokens stay in memory, the credential store or 600 files. `share`
  writes the teammate message to a private file (and the clipboard), never to the chat.
- Changes personal MCP entries or hooks only for an explicitly selected harness through the unified management flow; preserves unrelated entries, mounts and sources. Never pushes to
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

For installation, harness wiring, ingestion, search, embeddings, publication and event policy, use the executable
`manage`, `triggers` and `event` commands in `references/management-cli.md`. Start an unspecified management request with
`manage doctor`, then `triggers`; do not make users choose a second skill.

| Intent | Command | Writes |
|---|---|---|
| Look at the situation | `detect [--repo PATH] [--project KEY]` | no |
| Show the steps for a mode | `plan --mode team\|own\|repo-only [flow options]` | no |
| Attach (resumable) | `add --mode M --apply --yes [flow options]` | yes |
| Re-run every step (idempotent) | `repair --project KEY --apply --yes [--mode M] [--steps a,b]` | yes |
| All team brains at a glance | `status [--project KEY]` | no |
| End-to-end check only | `verify --project KEY` | throwaway token, revoked |
| Teammate access + kit | `share --project KEY --member NAME [--scope read_only\|read_write] [--repo PATH] [--apply --yes]` | private message file |
| Register a brain server | `registry add-provisioner --name N --base-url URL --credential CRED [--apply --yes]` | private registry |
| Copy brains from another machine | `registry export --out FILE` there, `registry import --file FILE [--apply --yes]` here | private registry |
| Detach | `remove --project KEY [--apply --confirm KEY]` | renames sync.sh, flags registry |

Flow options: `--capture MODE`, `--claude-md add|decline`, `--contact WHO`, `--write direct|sync` (team),
`--mcp-url URL --mcp-name NAME` (team brain without a provisioner), `--no-first-sync`, `--steps a,b`.

## add, step by step

1. `detect`. Show in one or two lines: project key (and where it came from), default branch, own GBrain, brain server.
   Key priority: `--project` > the repo's `knowledge.team_brain` (URL `/team/<key>/` or name `gbrain-<key>`) >
   registry > folder name. If `project_from` is `folder name` and that looks wrong, ask for the key in the same question.
   When `provisioner` is null and the team already runs a brain server, show `provisioner_hint` (register or import).
2. Ask **the one question** from `question` ("alone or with your team?"), `recommended` first with its `why`. For team,
   also ask `team_write_question` ("do members write directly, or through the repo?"); `direct` is recommended for small
   teams unless the repo switch already says otherwise.
3. `plan --mode <answer> [--write direct|sync]`. Show the steps, `repo_preview.version_yml_diff` / `block_diff`, and `server_preview` when
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
| `team --write sync` | `server` (provisioner creates or adopts the brain) > `repo` (switch + team brain name/URL) > `local` (sync folder, writer config 600, source, `sync.sh` 700, first sync) > `registry` (backup, add missing keys) > `verify` (read-only token, write refused) |
| `team --write direct` | `server` > `repo` (team brain only, `repo_notes: false`, `write: direct`) > `local` skipped (no sync machine) > `registry` > `verify` (read+write token, write allowed, probe page removed) |

Without `--write`, the mode recorded for the project (state file) or the repo switch is used, else `sync`, so existing
team setups behave as before.

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
| `verify_failed` | Read `verification.checks`. Sync: `write_refused.passed: false` is serious (a read-only token can write): report `probe_slug`. Direct: `write_allowed.passed: false` means members cannot write; `write_allowed.detail` is the server's reason (no secrets). Check the server's scope for read_write keys |
| `invalid_scope_preset` | The brain server cannot issue read_write keys: the brain admin issues the member key in its admin page |
| `needs_consent` / `confirmation_mismatch` | Ask, then re-run with `--apply --yes` (remove: `--confirm <project>` typed by the user) |

## status, repair, share, remove

- **status** lists every team brain from the registry and the brain server: registry switch, server health, this
  machine's sync folder, `last_sync` and the last gaps lines. A brain on the server but not in the registry shows
  `in_registry: false`: report it, do not adopt it silently.
- **repair** re-runs all steps of the recorded mode. Safe on a working brain: the server re-applies grants, existing
  files are kept, a hand-edited `sync.sh` is kept as `sync.sh.bak-<time>` before the generated one is written.
- **share** issues one key per teammate (name = token label; `read_write` for a direct team brain, `read_only` for sync,
  `--scope` overrides) and writes one teammate kit to `~/.projectops/gbrain/share/<project>-<member>-<time>.txt` (600) and
  the clipboard: the key, how to store it (`--prompt` in a terminal or `--from-file`), which branch holds the pro-brain
  rule (`rule_branch`: default branch first, else the development branch), the `/pro-brain` connect line, what
  `/pro-brain` will do, and `/pro-brain doctor --to team` after restart. Tell the user to send it one to one and delete
  the file. If `rule_branch.branch` is null, the rule is not on a shared branch yet: say so and merge it first.
- **remove** shows what stays (server brain, data, clone, notes) and what changes, asks the user to type the project key,
  then `remove --apply --confirm <key>`. Server-side removal is the brain admin's manual job.

## Brain server (provisioner)

Team mode automates the server only when the private registry declares a provisioner; everyone else gets the manual
steps. Register one without editing config.json: `registry add-provisioner` (a credential name for the admin key, never
the key) or `registry import --file` from a machine that has it (`registry export --out FILE` there; secret-looking keys
are dropped, existing values are kept, a backup is taken). The registry shape, the HTTP contract a brain server must speak and how another team plugs in their own:
`references/provisioner-contract.md`.

## Shared references

| Document | Read when |
|---|---|
| `references/management-cli.md` | Exact management command signatures, expected results and recovery |
| `references/unified-management.md` | Installation, harness wiring, credentials, triggers, ingestion, search, embeddings, summaries or publication |
| `references/how-it-works.md` | The owner asks how it works or which mode fits |
| `references/provisioner-contract.md` | Setting up a brain server, the registry entry, or debugging server codes |
| `../pro-brain/SKILL.md` | The repo side (switch, rule block, notes) and a member's team brain connection |
| `../references/config-rules.md` | Reading or editing the private registry by hand (§7 `project-blueprint`, §9 credentials) |

## Customize

Your own language, tone and rules apply: see `../references/preferences.md`. Read them once at the start: run the snippet in `../references/preferences.md` with `SKILL_ID=pro-gbrain`.
Keys for this skill: the common `language`, `tone`, `rules` only. Preferences change presentation only; the no-delete,
no-secret-output and consent rules stay in force.
