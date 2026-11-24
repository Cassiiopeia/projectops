# Unified knowledge management

The user calls `/pro-gbrain`; do the work through the existing executors. Never require the user to choose a skill or
stop after printing commands when the action is already authorized. Read the installed command's help before executing
version-dependent operations. No installation, database, provider or public publication is implied by a read request.

## Route the request

| Intent | Executor and verification |
|---|---|
| Unsure / set everything up | `detect`, then the discovery and onboarding below |
| Install GBrain | pro-brain `install --choice ...` produces a recipe; inspect it, execute authorized non-secret steps, then re-run detection |
| Create / connect the project | Existing `plan` and `add`; retain the current repo/own/team modes |
| Wire Claude Code or Codex | GBrain `setup <harness> --dry-run --json`, review target and ownership, then the authorized setup and harness doctor |
| Store a decision / report / issue | pro-brain note workflow; use its installed `write` capability when available |
| Import or refresh documents | GBrain source-scoped sync preview, then sync; inspect outcomes and search a known document |
| Diagnose / repair | Project status, pro-brain doctor when supported, GBrain doctor and source status; fix only the diagnosed target |
| Search / summarize | Search accessible project sources, read hits, synthesize with citations; never assume a `summary` command exists |
| Embeddings | Inspect engine and existing vectors; follow the provider procedure below |
| Publish a document | Separate explicit publication workflow below |
| Teammate access / detach | Existing share / remove; never delete the underlying brain |

## Discovery and onboarding

Keep program installation, database readiness, source selection, authentication, each harness connection, hooks,
indexing and schedules as separate states. Installed does not mean connected; configured does not mean verified.

1. Start with `manage doctor --repo PATH`: it returns `next_steps` (install > init > harness > triggers, each with
   the command and reason) and `harness_targets.same_brain` (whether Claude Code and Codex reach the same brain).
   Identify project and existing configuration with `detect` and pro-brain `status`. Read-only detection cannot install
   or initialize anything. Respect custom home paths. Resolve the actual executable, including the user's Bun bin.
2. Read GBrain version and help. Use `engine status --json` for the effective engine instead of guessing from a config
   file alone. Never print raw connection strings or credential material.
3. For each selected harness, use setup's dry-run to identify target, scope, owner and hooks. A hosted-connection
   refusal means an existing connection must be examined, not overwritten. Verify with the supported harness doctor.
4. Inspect sources, sync state, existing workflows and the selected host's scheduler/autopilot status. An unreachable
   host is unknown, not absent. Do not install a duplicate job merely because local detection cannot see the host.
5. Recommend repo documents, personal brain, existing team brain or a combination. Ask only unresolved questions,
   one at a time. Explain storage scope separately from installation scope and from access control. A source is not
   an authorization boundary. Both harnesses share knowledge only when they actually reach the same target.
6. Show one concrete plan: storage and source, files changed, tool connections, trigger and runner, secret references,
   provider use and expected costs. Preserve previous consent; ask again only for new effects outside that scope.
7. Execute, verify each stage and report partial failures. A nonzero exit or unresolved hold is not success. Keep
   existing data, MCP entries, settings and independent sources. Never force-reset an existing installation.

For direct multi-destination writes, use pro-brain's resolver and adapters when installed; do not create a parallel
settings system. If this installed version lacks the capability, say so and provide the supported repo/sync path.
Never advertise unavailable features as completed. Remote-only users do not need a local database.

## Credentials

Use the existing projectops credential store by name and its hidden terminal-input flow. Ask for a credential name,
not a secret in chat. Show presence and verification result only. Keep shared settings free of credentials and private
endpoints unless intentionally shared. Select a harness-supported safe credential delivery method; if none is available,
explain the limitation instead of putting secrets in shell history, argv, source files or logs. Never copy a personal
provider key to a team server without an explicit target and authorization. Separate reader, writer and admin access.

## Capture triggers and ingestion

First inspect the installed pro-brain capture modes and existing automation. Ask which supported moment should create
knowledge: manual, report/issue completion, meaningful session end, or merge. Deploy completion may enrich the existing
issue record. Explain whether the executor is an agent, CI, or a server job; an agent instruction is not a CI installation.

Configure moments with `triggers`: it writes the list to `knowledge.capture_events` (source of truth) and mirrors the
closest single mode into the existing `capture` key (`report`/`issue-done` > `issue-end`, else `merge`, `session-end`,
`manual`), so pro-brain and older plugin versions keep one consistent meaning. Never edit only one of the two keys.
`triggers` changes policy only: it installs no CI workflow or scheduler, so report a runner as configured only after
inspecting it.

Report completion creates the note; Git commit makes it available to default sync; the selected runner transfers it;
embedding makes semantic retrieval available. Track these stages independently. Default GBrain sync reads committed
content. Do not enable working-tree or ignored-file ingestion as an implicit fix for a missing note.

Before adding automation, inspect existing CI trigger, branch, folder, source, credentials and last execution. Reuse a
healthy existing runner. For a new runner, choose one explicit owner and supported supervisor. Use GBrain autopilot help
and status before installing it; PGlite has a single-writer constraint. Do not force-break locks. Scope sync to the project
source and preview with `sync --source <id> --dry-run --json`. Inspect held, resumable, blocked and failed outcomes as well
as the exit code. A scheduled command file is not proof of a registered or running schedule.

One issue note has one stable identity. Report, completion and deployment update that record rather than creating
copies. Preserve provenance and revisions. Never let direct writing and Git sync independently own the same page.
Retry only failed destinations. Knowledge failures are visible and recoverable; never rewrite deployment outcomes or
close an issue solely to make a knowledge trigger run. External PR jobs must not receive privileged credentials.

## Search and embeddings

Start with keyword search and verify a known document is retrievable. For optional semantic retrieval, inspect model,
vector dimension, stale chunks, provider credential availability and which machine actually performs embedding.
Explain provider data transfer and cost before enabling it. Use `embeddings enable --help` and the installed migration
help: existing incompatible vectors need the supported migration, not a silent config replacement. Enablement and
backfill are distinct; check coverage after embedding and run a representative query. Do not run `embed --all` against
an unrelated personal or shared brain. Query expansion is a separate model call and optional cost.

Summaries are grounded in selected issue/report/document evidence or actual search hits. Distinguish project knowledge
summaries, operational status and answers synthesized from search. Record sources and missing information. Do not invent
facts or promise a native GBrain summary command without checking the installed version.

## Publication

Publication is distinct from saving, indexing and Git deployment. Read the installed publish documentation before
execution: identify output destination, public reachability, password behavior and revocation/deletion support. If help
is insufficient, inspect official documentation/source and verify with a harmless sample, not real private material.
Show the exact selected content and audience. Obtain authorization for that publication, then verify the produced
artifact or URL and describe how to withdraw it if supported. Issue completion, deployment and embedding consent do not
implicitly authorize public publication. Never promise a revocation mechanism that has not been verified.

## Completion

Report: selected destinations, each harness's target and verification, actual capture trigger and runner, last sync,
search/embedding coverage, credential names only, publication result if requested, and precise unresolved items.
A read-only check or dry-run must be labelled as such. Keep the user in this skill until the authorized task is finished.
