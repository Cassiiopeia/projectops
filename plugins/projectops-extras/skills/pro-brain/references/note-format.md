# Note format, repo switch and brain compatibility

> When to read: onboarding (repo switch, brain usage), writing a note (content spec, default notes, metadata keys), wiring
> the gap check or a team brain sync.

## Repo switch (shared, in `version.yml`)

The switch is versioned with the repo, so teammates who never see the owner's private config get the same behavior.
`setup --apply --yes` writes it after the user agreed; editing by hand is fine too.

```yaml
metadata:
  template:
    options:
      knowledge:                                  # pro-brain knowledge capture (kept on updates)
        enabled: true
        path: "knowledge/"                        # repo folder a brain may sync
        capture: "issue-end"                      # issue-end | session-end | merge | manual (default issue-end)
        claude_md: "CLAUDE.md"                    # file holding the rule block, or "declined" (never asked again)
        team_brain: { mcp_name: "gbrain-myproject", mcp_url: "https://brain.example.com/mcp", contact: "platform team" }
                                                  # optional: shared team brain facts (never a token), or "none" (never asked again)
        note_dir: "issues/"                       # optional, inside path (default issues/ or changes/)
        template: "_templates/completion-report.md"   # optional, inside path
        rules: "SECOND-BRAIN.md"                  # optional, from the repo root: the repo's own vault rules
        check: "node second-brain/tools/vault.mjs check"   # optional, run on the files written
        skip: ["chore", "docs", "deps"]           # optional: commit types or words never worth a note
```

- The projectops installer keeps this block verbatim on every update (like `issue_helper`); it is listed in
  `npx projectops --mode options`.
- Missing block or `enabled` not `true` means off. `path` defaults to `knowledge/`, `capture` to `issue-end`.
- `team_brain` is the only brain fact in the shared switch: MCP server name (never `gbrain`, which is the usual personal
  entry), MCP URL (no credentials) and who issues read-only tokens. `setup` writes it as one `{ }` line; an indented map
  works too. The older `brain_mcp` key (name only) is still read and is replaced by `team_brain` on the next team-brain
  apply. A personal GBrain is never recorded here: `setup` detects it on each machine.
- The owner's registry `infra.brains.<name>.mcp_server_name` is only a hint: `setup` recommends the team-brain answer with
  that name prefilled, and status opens the usage question until the switch records a team brain or `"none"`. The rule
  block itself uses the switch only.
- `setup` proposes `rules` when the repo root has `SECOND-BRAIN.md`, `KNOWLEDGE.md` or `VAULT.md`.
- The owner's private registry (`project-blueprint`, `../../references/config-rules.md` §7) only names the brain that syncs
  the folder. It never turns capture on or off.

## Rule block (agent instructions)

`setup` renders one block between `<!-- pro-brain:begin ... -->` and `<!-- pro-brain:end -->` in the repo's language
(`metadata.template.options.language`), so re-running replaces it in place. It says when to run `/pro-brain` for the
repo's mode and, only when the switch names a team brain, to search that MCP first for "why" and "what did we decide"
questions before reading the folder. Claude Code strips HTML comments before loading, so the markers cost nothing.

| Project CLAUDE.md | Recommended target | Why |
|---|---|---|
| Tracked | `CLAUDE.md` | Every clone and worktree already gets it |
| Gitignored (or untracked) | `.claude/rules/pro-brain.md` (tracked) | Claude Code loads `.claude/rules/*.md` without `paths` frontmatter at launch, like `.claude/CLAUDE.md` |
| Gitignored and `.claude/` ignored too | the local `CLAUDE.md` + `init-worktree record --copied CLAUDE.md` | New worktrees on this machine copy it; teammates and fresh clones do not |
| None | `.claude/rules/pro-brain.md` | Creating a CLAUDE.md would stop Claude Code from reading AGENTS.md |

A tracked `AGENTS.md` that does not import `@CLAUDE.md` can get the same block (`--agents-md`) for Codex and other agents.

## Which format wins

1. `rules` set: read that file fully and follow its workflow (note types, ids, folders, links, log lines, index updates).
   `pro-brain` adds the durability check and the metadata keys as extra frontmatter keys; it does not create a second note
   beside the one the repo's workflow writes. If the repo's own ingest skill does the same job, that run is the `pro-brain` run.
2. `template` set: copy its frontmatter keys and sections, fill them, append the metadata keys.
3. Neither: the default note below (issue or change set).

The CLI's metadata keys never use `type`, `id`, `title`, `created`, `topics`, `status`, `related`, `supersedes`, `source`
or `resolves`: those belong to the note template or the repo's schema. `collect` only suggests `id`, `file_name`, topics
and related notes.

## Content spec (owner-approved)

**The brain stores why and where; git stores what.** Rich metadata, compact prose, no code bodies.

Body, about 30 to 80 lines of prose, in the repo's language (translate the headings):

1. One-line summary right under the title: what stays true now.
2. Background: the problem or trigger.
3. **Decision**: what was chosen, the reasons, and the rejected alternatives with why (the most important part;
   "no discussion recorded" when the sources do not say, never invented).
4. Behavior change: what users, API callers or data see differently.
5. Code pointers as `path > Symbol()` only.
6. Cautions: fragile spots, values that must change together, ordering.
7. Verification: one or two lines (tests, real checks).
8. Follow-ups, if any.

Excluded: raw diffs, code blocks, raw logs and stack traces (summarize the cause in one line), secrets, personal chat,
trivial changes (skip with one line). Exception: a tiny contract example of a few lines (request/response shape, table
columns). Version numbers only as they appear in the sources.

**Written for retrieval**: a teammate's question has to find the note by meaning (semantic search) and by filter (metadata).

- `id` stable and unique (`issue-<N>`, `change-<yyyymmdd>-<sha7>`, or the repo's own `ISS-0544` style); never reused.
- `title` says the lasting fact in the words a teammate would search ("Login uses 15-minute access tokens with refresh
  tokens", not "Fix #812").
- `topics` from `suggested.existing_topics` first, then `topic_hints`; 2 to 5 kebab-case tags.
- `related` links to the notes, decisions and issues it builds on; `supersedes` when it replaces an earlier decision
  (and mark the old one superseded if the repo rules say so).
- One decision per note when they are independent; split a mixed change set by topic (`collect --commits`).

## Default issue note

File: `{path}{note_dir}{suggested.file_name}` (for example
`knowledge/issues/2026-11-23-issue-1259-pro-brain-knowledge-capture.md`).

```markdown
---
type: issue-knowledge
id: "issue-{N}"
title: "{the lasting fact, searchable words}"
created: 2026-11-23
topics: ["auth", "api"]
status: active
related: ["[[issue-801]]"]
supersedes: []
source: "https://github.com/{owner}/{repo}/issues/{N}"
{frontmatter lines from collect, as is}
---

# {title}

{one-line summary}

## Background
## Decision
- {what was chosen} because {reason}. Rejected: {alternative} ({why not}).
## Behavior change
## Code pointers
- `server/auth/src/main/java/.../TokenService.java > TokenService.issue()`
## Cautions
## Verification
## Follow-ups
## Links
- Issue {issue_url}, PR {pr_url}, report comment {url}
```

## Default change-set note (session-end, merge, manual)

Same body and keys with `type: change-knowledge`, `id: "change-{yyyymmdd}-{sha7}"`, file under `changes/`, and `source:`
set to the PR URL, else `https://github.com/{owner}/{repo}/compare/{commit_base}...{commit_head}`. No issue keys unless the
change really belongs to one. A topic group carries `commits: [...]`.

## Metadata keys

All flat: scalars and flow lists only, because vault validators (for example passQL's `vault.mjs check`) reject nested maps
and multi-line values. Strings are double-quoted (valid YAML and JSON). Absent values are left out.

| Key | From |
|---|---|
| `capture_mode`, `captured_at`, `captured_by` | Repo mode (or `--capture-mode`), Asia/Seoul time (ISO 8601, `+09:00`), always `pro-brain` |
| `project`, `stacks` | Registry key, else the repo name in lower case; stack types whose folders changed |
| `app_version`, `build_number` | `version.yml` `version`, `version_code` at the last commit of the range |
| `issue`, `issue_url` | `--issue`, else the branch name `YYYYMMDD_#N_title` (issue-end only) |
| `pr`, `pr_url`, `branch` | Passed in from `pro-github list-prs`; `branch` is the checked-out one only in branch mode |
| `commit_base`, `commit_head`, `commit_count`, `commits` | The resolved range; `commits` only for a topic group (`--commits`) |
| `merge_commit` | First merge commit on the default or development branch that brought the range in (`--merge-commit` overrides) |
| `changed_modules`, `main_files` | Up to 10 modules (stack folder + next folder) and 8 files by lines changed; the knowledge folder is left out |
| `lines_added`, `lines_deleted` | Line totals of the range |
| `api_endpoints` | Route annotations and calls in changed lines (Spring with the class prefix, FastAPI, Flask, Express): `POST /api/auth/login` |
| `db_migrations` | Migration file names (Flyway, Liquibase, Alembic, Prisma, Rails/Django/Knex folders) |
| `config_keys` | Changed keys in config files (`application.yml:jwt.access-ttl-seconds`, properties, version.yml, app.json) |
| `env_or_secret_names` | Names only from `${{ secrets.X }}`, `${X}`, `os.environ`, `process.env`, `System.getenv`, `.env*` keys. Never values |
| `feature_flags` | `FEATURE_*`/`FF_*` names and `isEnabled("x")`-style calls |
| `deployed`, `deploy_targets`, `deploy_version` | Passed in when a deploy ran (`pro-changelog-deploy` result) |

Contract detection is a heuristic on paths and changed lines; check it against the diff and drop anything wrong.

## Gap check (from a brain sync script)

`gaps` reads git history and the note files only: no network call beyond what git already does, no LLM, no cost. It lists
work merged into the default branch since the last commit that touched the knowledge folder (or `--since`) that no note
mentions: issues (issue URLs and issue branch names in merged commits) in `issue-end`; PR merges, merges and direct commits
in the other modes. A note covers an item when it links the issue or PR, names the commit, or records a commit range that
contains it. The `skip` list drops matching commit types.

A sync script can log it right after pulling, without failing the sync:

```bash
# after: git -C "$team_brain_dir/repo" pull --ff-only --quiet origin main
python3 "$PRO_BRAIN_SCRIPTS/brain_cli.py" gaps --repo "$team_brain_dir/repo" --ref HEAD --format text \
  >> "$GBRAIN_HOME/gaps.log" 2>&1 || true
```

A sparse or partial clone works as long as the knowledge folder and `version.yml` are checked out. Set
`PRO_BRAIN_SCRIPTS` to the plugin's `skills/pro-brain/scripts` folder on that machine.

## Brain usage (onboarding question 3)

| Answer | Shared in the repo | On this machine | Command |
|---|---|---|---|
| `repo-only` (default) | nothing | nothing | none |
| `local-gbrain` | nothing | one source `{project}-knowledge` in the user's own GBrain, after consent | `connect`, then `connect --apply --yes` |
| `remote-gbrain` | nothing | nothing; the commands run on the brain's host | `connect` (`--remote` without a local gbrain) |
| `team-brain` | `team_brain` facts | the user adds one MCP entry with their own token | `setup --apply --yes --team-brain-*` |
| `install-guide` | nothing | nothing | none (show the GBrain link) |

Detection (`setup` > `usage`, `connect` > `detected`): `gbrain engine status --json` (engine-free; only `effective_engine`,
`config_file_engine`, `db_url_source` and `thin_client` are kept, never the database URL) and `gbrain sources list --json`.
A thin client means the user's brain is remote. Set `PRO_BRAIN_GBRAIN` to a gbrain binary path to override `PATH`.

`connect --apply --yes` runs exactly `gbrain sources add {id} --path {folder} --json` and `gbrain sync --source {id}
--no-pull --json` (no pull, so the user's working copy is never moved). Before that it refuses: an existing source with the
same id (`source_id_taken`), any source already reading the folder, a part of it or the repo around it
(`folder_already_connected`), and a folder without committed notes (`no_notes_yet`). gbrain itself also refuses a taken id.

Branches: gbrain imports the files committed on the branch checked out at the source path. A working-copy source sees
notes as soon as they are committed on any branch; for merged notes only, use a dedicated clone of the default branch:

```bash
git clone --branch main --single-branch <repo-url> ~/gbrain-sources/<project>
brain_cli.py connect --source-root ~/gbrain-sources/<project> --apply --yes      # after the user agreed
# hourly (cron, launchd, Task Scheduler):
git -C ~/gbrain-sources/<project> pull --ff-only --quiet && gbrain sync --source <project>-knowledge --no-pull
```

## Team brain server (what the team runs)

`pro-brain` only commits files and records the server facts; the team runs the server. With GBrain:

1. An HTTP MCP server reachable by members: `gbrain serve --http --public-url https://<host>` (behind your usual TLS).
2. A clone of the repo's default branch on that server, its `knowledge/` added as one source `{project}-knowledge`, and an
   hourly `git pull --ff-only` + `gbrain sync --source {project}-knowledge` (plus the gap check below if you like).
3. One read-only credential per member (GBrain: a client with the `memory-reader` profile, see its MCP admin guide),
   handed over privately and revoked when they leave. Never a shared token, never one in the repo.
4. `setup --apply --yes --team-brain-name gbrain-{project} --team-brain-url https://<host>/mcp --team-brain-contact <who>`
   once in the repo, committed. The URL is probed first (no token > 401, a dummy token > 401 invalid token; a 404 means
   an unknown brain, usually a typo in the brain key).
5. Each member stores their token once in the credential store (`launch cred set --name gbrain-{project}
   --secret-field token --prompt`, `../../references/config-rules.md` §9) and runs `connect --team --apply --yes`, which
   registers the user-scope MCP entry (`--rotate` after a new token). Optional `--project-mcp-json` commits a `.mcp.json`
   entry that reads `${GBRAIN_{PROJECT}_TOKEN}`.

Page slugs come from paths inside the folder, so two notes never share a slug, and nothing in a note depends on a
particular brain (no brain ids, no MCP calls, no embeddings in the file). One source per repo folder keeps brains
collision-free.

The owner's registry records the brain as `infra.brains.<name>` and `projects.<key>.knowledge.brain` (references only);
`status` shows it as `sync_target`. Teammates without that registry get `known: false` and write the same note.
