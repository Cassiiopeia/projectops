# NPX wizard guide (npx projectops)

This is the only official way to integrate the template into an existing project and to update it. The old `template_integrator.sh`/`.ps1` reached end of support (EOF) in v4.3.0 and the files have been removed ([details](./template-integrator.md)).

- **Requirement**: Node.js 20.12 or later
- One path for macOS, Linux and Windows

---

## Basic usage

```bash
# interactive wizard
npx projectops

# non-interactive (CI, etc.)
npx projectops --mode full --type spring,react --force

# install Agent Skills only
npx projectops --mode skills

# all options
npx projectops --help
```

| Mode | What it does |
|------|------|
| `full` | Integrates everything: workflows, version.yml, issue templates and Skills |
| `version` | version.yml only |
| `workflows` | Workflows only |
| `issues` | Issue/PR templates only |
| `skills` | Agent Skills only |

Every choice is saved under `metadata.template.options.*` in `version.yml` and reused on the next update without asking again.

> **Options the wizard does not ask about**: `semver_auto` (how far a release bumps the version, #546) is not in the question list.
> A new integration records it as `true`. **A repository that is already integrated does not get it turned on by an update**
> (a safeguard so an existing repository's version does not jump to a new minor without warning). To turn it on, set
> `metadata.template.options.semver_auto` in `version.yml` to `true` yourself.
> For the rules that decide the bump, see [version-control.md](./version-control.md).

---

## Project intent is asked first (#485)

Asked one at a time, the two deployment axes are hard to judge ("does this even apply to me?"). So right after the type is settled, the wizard **asks for the project intent once**, and that answer drives the two axes below.

| Choice | Meaning | deploy question | publish question |
|------|-----|------------------|-------------|
| `app` | You run a service | Asked | **Skipped** (`publish=[]`) |
| `library` | You publish a library/package | **Skipped** (`deploy=none`) | Asked |
| `both` | Both | Asked | Asked |
| `none` | Neither | **Skipped** (`none`) | **Skipped** (`[]`) |
| `manual` | You pick yourself | Asked | Asked |

- Stored at: `metadata.template.options.intent` in `version.yml`
- Non-interactive: `--intent app|library|both|none|manual`
- If there is no `intent` key, as in an old version.yml, it is **inferred automatically** from the saved `deploy`/`publish` values (backward compatible). If you pass `--intent` and leave out the flag for an axis, the intent decides that axis.
- The edit menu has a "Project intent" item next to the per-axis items. Changing the intent derives the axes again; a per-axis item fine-tunes only that axis.

---

## The deploy/publish axes (#439)

Deployment is expressed as **two independent axes**. The answer to the intent question above decides which axes are asked.

| Axis | Meaning | Multiplicity | Values | version.yml key |
|----|------|--------|-----|---------------|
| **deploy** | Where the runnable (server/app) goes | **Pick one** | `docker-ssh` (default) · `vercel` · `none` | `options.deploy` |
| **publish** | Which registry a library/package is published to | **0..n together** | `nexus` · `npm` · `github-packages` | `options.publish` array |

```bash
# non-interactive
npx projectops --deploy docker-ssh --publish nexus,npm
```

### Workflows included per axis

| Choice | Workflows included | Source location |
|------|-------------------|----------|
| `--deploy docker-ssh` | The server deployment set of each type (Spring: SIMPLE/NONSTOP-TRAEFIK/NONSTOP-NGINX/PR-PREVIEW, Python: SIMPLE-CICD/PR-PREVIEW) | `project-types/<type>/server-deploy/` |
| `--deploy vercel` | `PROJECT-COMMON-VERCEL-DEPLOY` (needs the VERCEL_TOKEN, VERCEL_ORG_ID and VERCEL_PROJECT_ID secrets) | `project-types/common/deploy/vercel/` |
| `--deploy none` | Server deployment workflows are left out | - |
| `--publish nexus` | `PROJECT-SPRING-NEXUS-CI` / `-NEXUS-PUBLISH` | `project-types/spring/publish/nexus/` |
| `--publish npm` | `PROJECT-NODE-NPM-PUBLISH` (NPM_TOKEN secret) | `project-types/node/publish/npm/` |
| `--publish github-packages` | `PROJECT-SPRING-GITHUB-PACKAGES-PUBLISH` | `project-types/spring/publish/github-packages/` |
| `--secret-backup` | `PROJECT-COMMON-SECRET-FILE-UPLOAD` (opt-in) | `project-types/common/secret-backup/` |

### Which axes apply to which types (#498)

Depending on the type, **an axis may not apply at all.** Only the union over the selected types is offered as choices.

| Type | deploy | publish |
|------|--------|---------|
| `spring` · `react` · `node` · `python` | `docker-ssh` · `vercel` | `nexus` · `npm` · `github-packages` |
| `flutter` · `react-native` · `react-native-expo` | None | None |
| `basic` | None | None |

- **If you selected only types where both axes are empty, the intent question is skipped entirely** and `deploy=none`, `publish=[]` are set quietly. Mobile app types always include their store deployment workflows (Play Store/TestFlight/Firebase) as part of the type, so the server deploy axis does not apply to them, and they have no registry publish concept.
- A saved value or CLI value that does not apply to the type is **cleaned up quietly, without a warning** (a repository from an older version that is flutter only but has `deploy: docker-ssh` saved is cleaned up to `none` on update; the copy result is the same either way).
- The edit menu also hides axis items that do not apply ("Project intent", "Deployment method", "publish targets"). They appear again the next time you open it after changing the type.

### Rules to know
- **Old flags are deprecated**: `--nexus`/`--npm-publish` are read as `--publish nexus`/`--publish npm` and print a warning (`--nexus` also implies `--deploy none`). They stay for one minor version and will then be removed.
- Old keys in version.yml (`nexus`/`npm_publish`) are converted to the new axes and written back automatically on update.

---

## Monorepo paths (`project_paths`)

If a type's project lives in a subfolder, give its path. For details see [Version control](./version-control.md).

```bash
npx projectops --paths "flutter=app,react=client"
```

---

## Automatic legacy workflow migration (#470)

When you integrate or update in `full`/`workflows` mode, the wizard **automatically detects leftovers of older template workflows** in the target repository. An old workflow that sits next to its new replacement causes real harm, such as release PRs being processed twice or CI running twice.

### Two-tier safety policy

| Tier | Criterion | Action |
|------|----------|------|
| **safe** | Pure rename or replacement (running both side by side does real harm) | Interactive: one confirmation, then neutralized as `.bak` / non-interactive (`--force`): neutralized automatically |
| **confirm** | May be a deployment pipeline (possibly the repository's only live deployment) | Left alone by default; the completion summary and `--mode doctor` show the list and the `git rm` commands. Interactive mode asks whether to rename it to `.bak` (default no); non-interactive mode renames it to `.bak` only with `--remove-legacy` (#809) |

### Guarantees

- **Custom workflows are never touched**: the registry matches exact file names only (no globs). Workflows you wrote yourself are never touched.
- **Reversible**: a safe action does not delete; it neutralizes the file with a `.bak` extension. To undo, remove the `.bak`.
  ```bash
  mv .github/workflows/PROJECT-OLD-NAME.yaml.bak .github/workflows/PROJECT-OLD-NAME.yaml
  ```
- **Idempotent**: running the same command again does not act on items that are already handled.

### What is detected (v4.3.x snapshot)

The single source for the full list is `src/core/migrations/registry.js` (55 entries in total). Summary:

| Category | Count | Contents |
|------|-----|------|
| **workflow / safe** | 18 | First-generation renames (`PROJECT-VERSION-CONTROL`, etc.), old release workflow names (`PROJECT-AUTO-CHANGELOG-CONTROL`, `PROJECT-COMMON-AUTO-CHANGELOG-CONTROL` → `PROJECT-COMMON-RELEASE-CHANGELOG`), rebranding renames (`PROJECT-FLUTTER-SUH-LAB-APP-BUILD-TRIGGER` → `PROJECT-FLUTTER-PROJECTOPS-APP-BUILD-TRIGGER`), removal of the next type (`PROJECT-NEXT-CI`/`-CICD` → `PROJECT-REACT-*`), CI with the old extension (.yml), and more |
| **workflow / confirm** | 22 | Seven SYNOLOGY-generation deployments, first-generation Spring/Python/Android/iOS deployments, the AUTO-FILE-UPLOAD family, the old Nexus publish family, and more. All of them "may be a live deployment", so they are only reported |
| **util-file / safe** | 12 | Retired files inside `.github/util/` modules (for example, the Flutter wizard scripts consolidated into Python). Copying util is an overlay that does not delete old files, so the registry is the only cleanup path |
| **root-file / safe** | 2 | `SUH-DEVOPS-TEMPLATE-SETUP-GUIDE.md`, `SETUP-GUIDE.md` → `PROJECTOPS-SETUP-GUIDE.md` (leftovers of the old setup guide) |
| **legacy-dir / ask** | 1 | `docs/suh-template/` → `docs/projectops/` (old name of the skill output folder; moved so user documents are kept) |

### Orphan workflow cleanup (#487) is not legacy migration

The registry is **for renames and retirements only**. **Workflows left behind when you deselect a type** are detected dynamically by `src/core/orphan-workflows.js`, which **compares against the template inventory**, not by the registry.

- Example: if you integrated with `--type spring,flutter` and then switch to `--type spring`, the remaining `PROJECT-FLUTTER-*` files are detected as orphans.
- Detection uses **exact file name matches** only (no glob or prefix matching, so custom user workflows are never touched).
- Interactive mode neutralizes them as `.bak` after confirmation; **non-interactive mode only prints a notice** and leaves them alone.
- `common/` is not a type, so it is excluded from orphan detection.

### Migration run records (#493, #494)

When the `full`/`workflows` wizard finishes, it leaves three layers of run records in `docs/projectops/migration/` of the **target repository**. You can trace afterwards what changed and why.

| Layer | File | Contents |
|------|------|------|
| 1 | `PROJECTOPS-MIGRATION-GUIDE.md` | Fixed header (guidelines for AI interpretation) plus append-only run entries. Dynamic checklist, full text of the breaking changes passed, yaml metadata |
| 2 | `{stamp}_v{from}_to_v{to}.jsonl` | Events for per-file decisions and env substitution before/after values (trace cause and effect by grepping file names) |
| 3 | `{stamp}_..._.log` | Raw mirror of the terminal output |

- The guide's workflow list and env values are **derived** from the layer 2 events (single source).
- Sensitive values (PAT, token, secret, password keys) are **removed automatically** when events are recorded.

## Workflows you modified are skipped; compare with incoming to merge (#654)

If you run the wizard again in a repository where you edited workflows yourself, the edited files are **left as they are, not overwritten** (to protect your changes).
Instead, the final screen shows the skipped files, the number of lines that differ from the new template, and a command to compare them.

```bash
diff -u .github/workflows/<file> .github/.projectops/incoming/<file>
# if diff is not available (Windows, etc.)
git diff --no-index .github/workflows/<file> .github/.projectops/incoming/<file>
```

- The new template copy is saved in `.github/.projectops/incoming/`. This folder is untracked through its own `.gitignore` and is overwritten with the latest template on every run.
- No copy is created in `.github/workflows/` (GitHub would run any file there as a real workflow).
- Move only the changes you need into your workflow by hand. If saving the copy fails, the wizard only leaves a warning and finishes normally.
- The skipped files and diff line counts are also recorded in the run records (the log and the `PROJECTOPS-MIGRATION-GUIDE.md` checklist).

### Contributor guideline: renaming or deleting a workflow

When you rename or retire a workflow, a root file, or a file inside `.github/util/` in the template, **always add the old name to `src/core/migrations/registry.js` as one line**. This is the only path that automatically cleans up old files in repositories that are already integrated (all legacy migration is managed in this one registry).

1. Entry schema: `id` (kebab-case) · `category` (`"workflow"` | `"root-file"` | `"util-file"` | `"legacy-dir"`) · `tier` · `file` (exact file name or path, no globs) · `replacedBy` (null if none) · `since` · `reason` · `contentMarker` (optional; prevents false positives when the file name is generic) · `settingsExtractor` (optional; moves the user's custom settings into version.yml right before neutralizing)
2. **How to pick the tier**: choose by real harm.
   - `safe`: the new workflow fully replaces the same feature (a pure rename). Running both causes a double trigger, which does real harm
   - `confirm`: may be a deployment pipeline. Removing it by mistake breaks that repository's deployment, so no automatic action
3. `test/migrations.test.js` checks automatically that registry entries **do not overlap the current deployment set** (so live workflows are not removed by mistake). After adding an entry, confirm with `npm test`.

---

## Related docs

- [Template Integrator EOF notice](./template-integrator.md): mapping from the old scripts to npx flags
- [Version control](./version-control.md): version.yml, monorepo project_paths
- [Changelog automation](./changelog-automation.md#release-note-provider-ladder): the release note provider ladder

## Workflows an update does not install (#810)

An update does not reinstall every file in the template. In the cases below it skips the file and shows the reason on the final screen. It leaves a rendered copy in `.github/.projectops/incoming/` so you can restore it.

| Reason | Condition |
|---|---|
| `deleted-by-user` | The wizard installed it before (recorded in the baseline) and it is gone now, so you deleted it yourself |
| `excluded` | You listed the file name in `metadata.template.options.excluded_workflows` in `version.yml` |
| `no-dev-branch` | The workflow runs only on `develop`, and the remote definitely has no development branch (if the remote cannot be checked, it is installed) |

```yaml
options:
  excluded_workflows: ["PROJECT-COMMON-TEMPLATE-UTIL-VERSION-SYNC.yml", "PROJECT-SPRING-NONSTOP-NGINX-CICD.yaml"]
```

- With `--force`, example defaults such as `example.com` are not filled in; the `__SERVICE_DOMAIN__` token is left as is. If it appears in the "not substituted" notice on the final screen, fill it in yourself.
- When a file is refreshed because only the template changed, the env values you chose (for example `JAVA_VERSION: "17"`) are kept.
