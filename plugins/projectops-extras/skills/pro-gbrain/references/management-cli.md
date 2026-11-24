# Management commands

Use the same `{PYTHON} {SCRIPTS}/gbrain_cli.py` as the main skill. These are executable commands, not shell recipes.
Mutations preview by default; `--apply --yes` executes the selected operation after authorization. No command accepts a
raw password or token. `--gbrain-home PATH` selects a separate GBrain home for management commands and also points
harness wiring at `PATH/.codex` and `PATH/.claude`, so a trial never rewires the real Claude Code or Codex.

```bash
{PYTHON} {SCRIPTS}/gbrain_cli.py manage doctor --repo /path/to/project
{PYTHON} {SCRIPTS}/gbrain_cli.py manage doctor --probe
```
Returns `code: inventory`, executable, engine, each harness dry-run, automation, `harness_targets` (brain per
harness and `same_brain`: true, false or unknown) and `next_steps` in setup order. `--probe` adds the live doctor.
Engine detection does not prove database reachability. Harness dry-runs do not prove hooks fired in a real session.

```bash
{PYTHON} {SCRIPTS}/gbrain_cli.py manage install
{PYTHON} {SCRIPTS}/gbrain_cli.py manage install --apply --yes
{PYTHON} {SCRIPTS}/gbrain_cli.py manage init --engine pglite
{PYTHON} {SCRIPTS}/gbrain_cli.py manage init --engine pglite --apply --yes
{PYTHON} {SCRIPTS}/gbrain_cli.py manage init --engine postgres --credential brain-db --credential-field database_url --credential-env GBRAIN_DATABASE_URL
```
Returns `plan`, `already_installed`, `already_initialized`, or the execution result. Installation uses the official
`github:garrytan/gbrain#stable` distribution, never the unrelated registry package. Bun is a prerequisite. Existing
brains are kept. Review the returned plan before applying. New local brains start without embeddings or paid calls.

```bash
{PYTHON} {SCRIPTS}/gbrain_cli.py manage harness --harness codex
{PYTHON} {SCRIPTS}/gbrain_cli.py manage harness --harness claude-code --source project-knowledge --apply --yes
```
Returns setup's target preview or execution and verification. Default: read-context hooks, no transcript capture and no
paid provider setup. Add `--no-hooks` for MCP only or `--capture` only when automatic transcript capture is authorized.
Hosted ownership conflicts are reported rather than replaced.

```bash
{PYTHON} {SCRIPTS}/gbrain_cli.py manage source --source project-knowledge --path /path/to/committed-docs-repo
{PYTHON} {SCRIPTS}/gbrain_cli.py manage source --source project-knowledge --path /path/to/committed-docs-repo --apply --yes
{PYTHON} {SCRIPTS}/gbrain_cli.py manage source --source project-knowledge
{PYTHON} {SCRIPTS}/gbrain_cli.py manage ingest --source project-knowledge
{PYTHON} {SCRIPTS}/gbrain_cli.py manage ingest --source project-knowledge --apply --yes
{PYTHON} {SCRIPTS}/gbrain_cli.py manage search --source project-knowledge --query "deployment decision"
{PYTHON} {SCRIPTS}/gbrain_cli.py manage search --source project-knowledge --query "why did we choose this" --semantic
```
`source` with `--path` registers one new git-backed source (never `--force`; an existing id returns
`already_registered`); without `--path` it returns source status (pages, chunks, embedding coverage).
Ingest returns `plan` with a real sync preview, or executes source-scoped committed-content sync without Git pull.
Embedding is off unless `--embedding` is selected. Read the source's held/resumable/blocked states; exit zero alone is
not completion. Search returns GBrain results for the selected source. Read and cite them when summarizing.

```bash
{PYTHON} {SCRIPTS}/gbrain_cli.py manage embeddings --model provider:model --dimensions 1024 --credential embeddings-key --credential-field api_key --credential-env OPENAI_API_KEY
{PYTHON} {SCRIPTS}/gbrain_cli.py manage embeddings --model ollama:qwen3-embedding:0.6b --dimensions 1024 --apply --yes
{PYTHON} {SCRIPTS}/gbrain_cli.py manage embed --apply --yes
```
Returns `plan`; apply only for the selected brain and provider. A credential name that is not stored is refused at plan
time (`credential_missing`). GBrain enforces vector/model compatibility; its refusal (for example
`embedding_width_mismatch`) comes back with GBrain's exact fix in `next`. The model is host-wide for that GBrain home.
Enablement only queues chunks: `manage embed` backfills them, and `manage source --source ID` shows coverage. A local
Ollama model costs nothing; paid providers bill per token. A missing provider key names the variable in `next`.

```bash
{PYTHON} {SCRIPTS}/gbrain_cli.py manage publish --file /path/to/reviewed.md --out /path/to/new-share.html
{PYTHON} {SCRIPTS}/gbrain_cli.py manage publish --file /path/to/reviewed.md --out /path/to/new-share.html --content-sha SHA_FROM_PLAN --apply --yes
```
Returns a content hash and local-HTML plan. Apply checks the hash, refuses an existing output, generates the artifact
and verifies it exists. This publishes no URL. Local copies cannot be remotely revoked. Password-protected or hosted
publication needs the installed GBrain's supported flow; do not claim it happened from this local artifact command.

```bash
{PYTHON} {SCRIPTS}/gbrain_cli.py manage schedule --schedule-action status
{PYTHON} {SCRIPTS}/gbrain_cli.py manage schedule --schedule-action install --repo /path/to/brain --target macos
{PYTHON} {SCRIPTS}/gbrain_cli.py manage schedule --schedule-action pause --apply --yes
{PYTHON} {SCRIPTS}/gbrain_cli.py manage schedule --schedule-action resume --apply --yes
{PYTHON} {SCRIPTS}/gbrain_cli.py manage schedule --schedule-action uninstall --apply --yes
```
Status reads autopilot. The install plan is GBrain's own `--dry-run` (supervisor and files it would write); apply
passes `--yes`, which GBrain requires for this persistent install. `manage doctor` lists `existing_runners` (launchd
plists, crontab lines or Windows tasks that mention gbrain): reuse those before adding another. Other operations
return plans unless applied. Maintenance is brain-wide: inspect existing
runners and explain the scope before installing. A PGlite brain is refused (`pglite_single_writer`): a resident daemon
would hold its single-writer lock, and `--force` is never passed. Install never edits agent bootstrap files.

```bash
{PYTHON} {SCRIPTS}/gbrain_cli.py manage note --repo /path/to/project --issue 123
{PYTHON} {SCRIPTS}/gbrain_cli.py manage note --repo /path/to/project --file /path/to/note.md --apply --yes
```
Collects facts for agent-authored summaries, or delegates writing to pro-brain's configured destination adapters.
If the installed pro-brain lacks `write`, use the event command's repo-only fallback or upgrade the extras package.

```bash
{PYTHON} {SCRIPTS}/gbrain_cli.py triggers --repo /path/to/project
{PYTHON} {SCRIPTS}/gbrain_cli.py triggers --repo /path/to/project --events report,issue-done,deploy --runner agent --apply --yes
{PYTHON} {SCRIPTS}/gbrain_cli.py event report --repo /path/to/project --issue 123
{PYTHON} {SCRIPTS}/gbrain_cli.py event report --repo /path/to/project --issue 123 --note /path/to/note.md --apply --yes
{PYTHON} {SCRIPTS}/gbrain_cli.py event deploy --repo /path/to/project --issue 123 --outcome success --note /path/to/note.md --apply --yes
```
`triggers` returns policy and unverified workflow candidates, or writes `knowledge.capture_events`, the mirrored
legacy `capture` mode, `capture_runner` and optional `capture_source` in version.yml. It installs no workflow. Legacy capture modes are mapped on read.
`event` returns `skipped`, `needs_note`, `plan`, `noop`, or destination results. No note means collect facts, then author
or update that stable record. Deployment events need `--outcome success`. Non-issue records require `--record-id`.
Receipts live privately per project and record. A completed identical payload is a no-op; failed payloads retry.
A record keeps one file: when the knowledge folder already has a note with the same `id`, the update is delivered under
that file name whatever the new file is called. The repo-only path overwrites only what it wrote last; a hand-edited
note returns `note_conflict`.
Old pro-brain versions write repo files and explicitly report `pending_commit_and_sync`, never remote success.

## Error handling

| Code | Action |
|---|---|
| `harness_launcher_unresolved` | GBrain setup cannot resolve its launcher (GBrain 0.60 on Windows): run the manual MCP registration in `next` |
| `windows_supervisor_unsupported` | GBrain autopilot has no Windows service: use the Task Scheduler line in `next`, or on-demand ingest |
| `credential_missing` | Store the credential with hidden input under that name, then repeat |
| `pglite_single_writer` | Keep on-demand ingest, or move the brain to Postgres before installing a runner |
| `not_a_git_repo` / `sources_unreadable` | Commit the documents in a git repo; run `manage doctor --probe` |
| `gbrain_missing` / `bun_missing` | Run install plan; prepare the official runtime if required |
| `needs_consent` | Use existing authorization or obtain consent for the displayed new effects |
| `credential_env_required` / `database_credential_required` | Choose a named credential and supported environment variable |
| `gbrain_failed` / `gbrain_timeout` | Read structured result, inspect the target, retry only the failed operation |
| `content_changed` | Re-review the exact document and obtain its new hash |
| `output_exists` | Choose a fresh publication path; never overwrite another artifact |
| `event_busy` | Inspect the active runner; never remove an unexplained lock |
| `note_conflict` | Review and update the existing note, then pass that file explicitly |
| `write_upgrade_required` | Update pro-brain to a version with destination adapters |
| `config_changed` / `switch_invalid` | Re-read version.yml and preserve concurrent changes |
