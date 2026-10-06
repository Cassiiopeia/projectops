# Architecture

This document explains how projectops is put together and where to make a change.
For setup and usage see the [README](README.md); for contribution rules see [CONTRIBUTING](CONTRIBUTING.md).

## Two identities

This repository is two things at once, and most mistakes come from forgetting that.

1. **A GitHub template repository.** "Use this template" copies it, then `PROJECT-TEMPLATE-INITIALIZER` runs `.github/scripts/template_initializer.py` and deletes everything that only makes sense here.
2. **The source of the `npx projectops` wizard.** The wizard downloads this repo and copies the shared parts into an existing project, skipping the same repo-only files.

Anything you add at the repository root has to answer one question: *does a user's project need this?*

## Execution flow of `npx projectops`

```
bin/projectops.js
  └─ src/index.js            parse args, resolve language, route to a mode
       ├─ core/assets.js     acquire the template (git clone, or a local path in tests)
       ├─ core/detect*.js    detect project types, version, default branch
       ├─ core/breaking-check.js, core/migrations/   warn about breaking changes, neutralise renamed workflows
       ├─ commands/*.js      full | workflows | version | issues | skills | interactive | doctor
       │    └─ core/copy/*   the copy engine (workflows, scripts, config, util modules, issue templates, ...)
       ├─ core/verify.js     check the result
       └─ core/run-trace.js  write the execution record under .github/.projectops/logs/
```

- **Non-interactive first.** `--force` / `-y` is the primary path; the interactive wizard collects the same options and calls the same engine.
- **Language** is resolved in `src/i18n/` (`--lang` > `PROJECTOPS_LANG` > system locale > `en`; CI and `--force` are pinned to `en`). Logs are always English.
- **The copy order** is fixed in `src/commands/full.js`: `version.yml` → README section → workflows → scripts → config → util modules → issue templates → coderabbit → `.gitignore`.
- **`version.yml`** is the single source of truth for what was installed (`metadata.template.options.*`). Reinstalling reads it back instead of asking again.

## Repository layout

| Path | What it is | Ships to user projects |
|---|---|---|
| `src/`, `bin/`, `test/` | The npx wizard and its tests | No |
| `.github/workflows/` | Workflows. `PROJECT-COMMON-*` are the shared set; `PROJECT-TEMPLATE-*` run only here | Common only |
| `.github/workflows/project-types/<type>/` | Per-type workflows (`flutter`, `spring`, `react`, `node`, `python`, `common`) | By selection |
| `.github/scripts/` | Python/shell helpers the workflows call (`version_manager`, `changelog_manager`, `issue_helper`, ...) | Yes |
| `.github/util/` | Wizards for store deployment and Projects sync | By selection |
| `skills/` | Agent skills (Claude Code plugin, Cursor install source) | No (installed separately) |
| `docs/` | Documentation | No |
| `version.yml` | Version and install options | Regenerated per project |

## Invariant contracts

These are parsed by other code. Changing them silently breaks installed projects.

- **Branch name** `YYYYMMDD_#<issue>_<title>` and the `### Branch` code block in the issue helper comment. Consumers are listed in [`docs/BRANCH-CONVENTION.md`](docs/BRANCH-CONVENTION.md).
- **The README version section** title, which `PROJECT-COMMON-README-VERSION-UPDATE` searches for.
- **Workflow file names.** Renaming or deleting one requires an entry in `src/core/migrations/registry.js`, or existing installs keep running the old file.
- **Common workflows exist twice**: the original in `project-types/common/` and the copy in `.github/workflows/` root. Keep them identical.

## How to add a new project type

1. Add the type to the detection and marker tables (`src/core/detect.js`, `src/core/paths-resolve.js`).
2. Create `.github/workflows/project-types/<type>/` with its CI/CD workflows. Server deployment workflows go under `<type>/server-deploy/` so they are skipped when `deploy` is not `docker-ssh`. Registry publishing goes under `<type>/publish/<target>/`.
3. Declare which deploy and publish targets the type supports in `src/core/options-ask.js` (`TYPE_DEPLOY_TARGETS`, `TYPE_PUBLISH_TARGETS`). `test/options-ask.test.js` checks these against the folders.
4. Teach `version_manager` how to sync the version file for the type.
5. Add tests under `test/` and run `npm test`.

## How to add a new workflow

1. Shared by every project → put it in `project-types/common/` **and** copy it to `.github/workflows/`. Type specific → only `project-types/<type>/`.
2. Include `workflow_dispatch`, a `concurrency` group, `[skip ci]` on bot commits, and an explicit `permissions:` block (`.github/scripts/test/test_workflow_permissions.py` enforces it).
3. If the workflow depends on the branch naming rule, add it to `GUIDE_LINES` in `.github/scripts/issue_helper.py`.
4. If it is conditional (an opt-in folder under `common/`), update **both** the copy gate in `src/core/copy/workflows.js` and `commonOptionalOrphans` in `src/core/orphan-workflows.js`, otherwise turning it off leaves the file behind.
5. If you rename or remove one, register the old name in `src/core/migrations/registry.js`.

## How to add a file that must not reach user projects

Update both places, or new projects get polluted or the wizard copies it:

| File | Effect |
|---|---|
| `.github/scripts/template_initializer.py` | Deleted when a repo is created from the template |
| `src/core/exclusions.js` | Skipped when the wizard copies into an existing project |

If it carries a version that must match `version.yml`, also add a step to `PROJECT-TEMPLATE-PLUGIN-VERSION-SYNC`.

## Testing

```bash
npm test                              # wizard (node --test)
python3 -m pytest .github/scripts/test/ skills/   # scripts and skills
```

CI runs a quick lane on every push and the full OS and Node matrix on `main`. Do not remove the OS matrix: this repo has broken on macOS bash 3.2 and Windows before.

## Known duplication

The common workflows existing in two places is a consequence of the copy structure, not a design goal. Whether to generate one from the other is tracked as a follow-up to [#773](https://github.com/Cassiiopeia/projectops/issues/773).
