# Note format, repo switch and brain compatibility

> When to read: step 1 (is it on) and step 4 (write the note) of `pro-brain`.

## Repo switch (shared, in `version.yml`)

The switch is versioned with the repo, so teammates who never see the owner's private config get the same behavior.

```yaml
metadata:
  template:
    options:
      knowledge:                                  # pro-brain: one note per issue with durable knowledge
        enabled: true
        path: "knowledge/"                        # repo folder a brain may sync
        note_dir: "issues/"                       # optional, inside path (default issues/)
        template: "_templates/completion-report.md"   # optional, inside path
        rules: "SECOND-BRAIN.md"                  # optional, from the repo root: the repo's own vault rules
        check: "node second-brain/tools/vault.mjs check"   # optional, run on the files written
```

- The projectops installer keeps this block on every update: like `issue_helper`, it is an option the generator does not
  write itself, so it is copied back verbatim (comments included). It is listed in `npx projectops --mode options`.
- Missing block or `enabled` not `true` means off. `path` defaults to `knowledge/`.
- The owner's private registry (`project-blueprint`, `../../references/config-rules.md` §7) only says which brain syncs the
  folder. It never turns capture on or off; when it expects capture but the repo block is missing, `status` says so and
  the agent proposes the block above.

## Which format wins

1. `rules` set: read that file fully and follow its workflow for an issue (note types, ids, folders, links, log lines,
   index updates). `pro-brain` adds the durability check and the metadata keys; it does not create a second note beside
   the one the repo's workflow writes. If the repo's own ingest skill does the same job, that run is the `pro-brain` run.
2. `template` set: copy its frontmatter keys and sections, fill them, append the metadata keys.
3. Neither: the default note below.

Repo rules usually define `source:` as the origin URL. The metadata keys therefore never use `source`, `type`, `id`,
`created`, `topics`, `status`, `related` or `resolves`; `captured_by: "pro-brain"` marks the capture tool instead.

## Default note

File: `{path}{note_dir}{created}-issue-{N}-{slug}.md`, with `slug` = 3 to 6 ASCII kebab-case words from the issue title
(example `knowledge/issues/2026-11-23-issue-1259-pro-brain-knowledge-capture.md`). Write the body in the repo's language
(`version.yml` `language`; translate the headings).

```markdown
---
type: issue-knowledge
created: 2026-11-23
topics: []
status: active
related: []
source: "https://github.com/{owner}/{repo}/issues/{N}"
project: "{project}"
stacks: ["spring", "react-native-expo"]
app_version: "1.4.0"
build_number: 37
issue: {N}
issue_url: "https://github.com/{owner}/{repo}/issues/{N}"
pr: {PR}
pr_url: "https://github.com/{owner}/{repo}/pull/{PR}"
branch: "{YYYYMMDD_#N_title}"
commit_base: "{40-hex sha}"
commit_head: "{40-hex sha}"
commit_count: 3
deploy_target: "server"
deploy_version: "1.4.0"
changed_modules: ["server/{module}", "mobile/src"]
main_files: ["server/{module}/src/main/java/{File}.java"]
captured_at: "2026-11-23T14:05:00+09:00"
captured_by: "pro-brain"
---

# #{N} {one-line summary of what stays true now}

## Decisions
- {what was decided, as a checkable statement}

## Why
- {the reason; "no discussion recorded" when the sources do not say}

## Cautions for the next person
- {trap, ordering, value that must change together with another, with its location}

## Links
- Issue {issue_url}, PR {pr_url}, report comment {url}
- Related notes: {[[note]] or paths}
```

## Metadata keys

All flat: scalars and flow lists only, because vault validators (for example passQL's `vault.mjs check`) reject nested
maps and multi-line values. Strings are double-quoted (valid YAML and JSON). Absent values are left out.

| Key | From |
|---|---|
| `project` | Private registry key, else the repo name in lower case |
| `stacks` | Stack types whose folders the issue touched (registry `stacks`, else `version.yml` `project_paths`) |
| `app_version`, `build_number` | `version.yml` `version`, `version_code` at the issue's last commit |
| `issue`, `issue_url` | `--issue`, else the branch name `YYYYMMDD_#N_title` |
| `pr`, `pr_url`, `branch` | `pro-github list-prs` (passed in); `branch` is the checked-out one only in branch mode |
| `commit_base`, `commit_head`, `commit_count` | The resolved range; in `--issue` mode only the commits that link the issue are counted |
| `deploy_target`, `deploy_version` | Passed in when a deploy ran (`pro-changelog-deploy` result) |
| `changed_modules`, `main_files` | Up to 10 modules (stack folder + next folder) and 8 files by lines changed; the knowledge folder is left out |
| `captured_at`, `captured_by` | Capture time in Asia/Seoul (ISO 8601, `+09:00`), always `pro-brain` |

## Brains that sync the folder (local, remote, team)

`pro-brain` only commits the file. Whoever runs a brain decides whether to sync the repo folder. To stay collision-free
with every setup, a brain that syncs it registers **one source per repo folder, named `{project}-knowledge`** (the passQL
team brain uses source `passql-knowledge`, fed hourly from `knowledge/` on `main`). Then:

- A personal brain that also syncs the repo keeps the notes in their own source, apart from its conversations and
  personal notes, and a team brain and a personal brain can sync the same folder without clashing.
- Page slugs come from the path inside the folder; file names carry the date or the repo's own id, so two notes never
  share a slug inside one source.
- Nothing in a note depends on a particular brain: no brain ids, no MCP calls, no embeddings in the file.

The owner's registry records the brain as `infra.brains.<name>` and `projects.<key>.knowledge.brain` (references only);
`status` shows it as `sync_target`. Teammates without that registry get `known: false` and write the same note.
