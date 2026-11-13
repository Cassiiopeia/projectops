# Version control

In a normal release, RELEASE-CHANGELOG finalizes the version on the `develop → main` PR. VERSION-CONTROL is a **safety net that bumps the patch version automatically on a direct push to main**.

---

## Overview

| Feature | Description |
|------|------|
| **Auto bump (safety net)** | On a direct push to main, patch version +1 (1.0.0 → 1.0.1). It skips release PR merges (those that include a `version.yml` change) |
| **Version finalization (normal release)** | On the `develop → main` PR, RELEASE-CHANGELOG finalizes the version and stamps the CHANGELOG |
| **Multi-file sync** | Two-way sync between version.yml and project files |
| **Conflict resolution** | "Higher version wins" policy when versions disagree |
| **Git tag** | Creates a tag automatically when the version changes |

---

## version.yml

Version information for every project is managed centrally in `version.yml`.

```yaml
version: "2.4.3"              # version (managed automatically)
version_code: 94              # Android release build number (auto-incremented)
project_types: ["spring"]     # array of project types, the first entry is primary

metadata:
  last_updated: "2026-01-06 08:23:20"
  last_updated_by: "username"
```

### `project_types` (array, the only source)

Use the `project_types` array key when one repository holds several types.

```yaml
project_types: ["spring", "react", "python"]   # the first entry is primary
```

- A single type is also written as an array (`project_types: ["basic"]`).
- The primary type (which decides the version file) is the **first item** of the array.
- The singular `project_type` key was **removed in v4.1.0**. For the pre-v4.0 format that has only the singular key, `version_manager.sh` fails explicitly and explains how to convert (`project_type: "spring"` → `project_types: ["spring"]`).
- `version_manager.sh` iterates the array and syncs the version file of every type.

### `project_paths` (monorepo path map)

In a monorepo where each type lives in a subfolder, use the `project_paths` map (type → path relative to the repo root) to say where each one is.

```yaml
project_types: ["flutter", "react"]
project_paths:
  flutter: "app"       # syncs app/pubspec.yaml
  react: "client"      # syncs client/package.json
```

- A type with no key works relative to the **repo root** (existing behavior is fully preserved).
- During `npx projectops` integration, marker files (`pubspec.yaml`, `package.json`, `pyproject.toml`, `build.gradle`, etc.) are detected automatically and offered as candidates. In non-interactive mode, set them with `--paths "flutter=app,react=client"` (see the [NPX wizard guide](./npx-wizard.md)).
- `version_manager.sh` follows these paths to sync version files in subfolders, so the `PROJECT-COMMON-VERSION-CONTROL` workflow supports monorepos without changes.

---

## Version files by project type

| Type | Version file | Version location |
|------|----------|----------|
| `spring` | `build.gradle` | `version = '1.0.0'` |
| `flutter` | `pubspec.yaml` | `version: 1.0.0+1` |
| `react` (including Next.js) | `package.json` | `"version": "1.0.0"` |
| `node` | `package.json` | `"version": "1.0.0"` |
| `python` | `pyproject.toml` | `version = "1.0.0"` |
| `react-native` | `Info.plist` + `build.gradle` | iOS/Android separate |
| `react-native-expo` | `app.json` | `"version": "1.0.0"` |
| `basic` | `version.yml` only | - |

---

## Using version_manager.sh

> Since v4.2 the real logic lives in `version_manager.py` (stdlib only, no yq/jq needed), and `.sh` is a shim that delegates to Python (#448). On Windows, run the .py directly, for example `python .github/scripts/version_manager.py get`.

### Basic commands

```bash
# show the current version
.github/scripts/version_manager.sh get

# bump the patch version (1.0.0 → 1.0.1)
.github/scripts/version_manager.sh increment

# set a specific version
.github/scripts/version_manager.sh set 2.0.0

# sync versions (resolves conflicts)
.github/scripts/version_manager.sh sync

# validate the version format
.github/scripts/version_manager.sh validate 1.2.3
```

### Managing version_code

`version_code` is **for Android releases only**. It goes up by 1 on every release, and the Play Store CICD and Firebase CICD read it and use it as `versionCode`. Self-hosted (SMB) deploys use the `+N` in `pubspec.yaml`.

**It is not used for iOS or for test builds (iOS test, Android test APK).** These use a time-based number decided by `build_number.py` (seconds since 2024-01-01 UTC) (#643). The iOS release number is also no longer the same as `version_code`.

```bash
# show the current build number
.github/scripts/version_manager.sh get-code

# bump the build number
.github/scripts/version_manager.sh increment-code
```

---

## Automation flow

### Normal release (develop → main PR)

```
Create develop → main PR (release)
    │
    ▼
RELEASE-CHANGELOG workflow
    │
    ├─ Fix the version (patch/minor/major decided inside the PR)
    ├─ Stamp CHANGELOG.json / CHANGELOG.md
    └─ automerge
         │
         ▼
Push to main (release merge)
    │
    ├─ README-VERSION-UPDATE
    ├─ PLUGIN-VERSION-SYNC
    └─ CICD deploy
```

### Direct push to main (safety net)

```
Direct push to main (not a release PR)
    │
    ▼
VERSION-CONTROL workflow
    │
    ├─ Read the version from version.yml
    ├─ Bump the version (major/minor/patch from commit titles when semver_auto is on, patch when it is off)
    ├─ Sync project files
    ├─ Create the Git tag (v1.0.1)
    └─ Commit & push
```

> VERSION-CONTROL does not create a PR. It detects and skips pushes caused by a release merge (those that include a `version.yml` change), and acts as a patch +1 safety net only for other direct pushes to main.

---

## Branches have three meanings

"Branch" means different things in projectops. The `version.yml` key names do not always match the plain meaning.

| Branch | What it is | `version.yml` key | Usual value |
|---|---|---|---|
| Default (deploy) branch | The repository default and production branch. A push here runs the deploys | `metadata.default_branch` | `main` |
| Development (release source) branch | Where work collects. It is the head of the release PR into the default branch | `metadata.development_branch` (old name `deploy_branch`) | `develop` |
| Deploy trigger branch (optional) | A push here runs the deploy workflows. Set it only to split deploys from the default branch (develop > main > deploy) | `metadata.template.options.deploy_trigger_branch` | not set = the default branch |
| Issue branches | One branch per issue, e.g. `20261113_#123_title` | - | - |

- `--deploy-branch` sets the **development** branch. It writes `development_branch`, not the deploy branch.
- `development_branch` is the current key. The old key `deploy_branch` is still read, and the wizard writes both keys with the same value.

## Separate deploy branch (optional)

By default a push to the default branch (`main`) deploys. If you want develop → main → deploy, with the deploy workflows
(app store, server, package publish, Vercel) running only from a `deploy` branch, set it once:

```bash
npx projectops --mode workflows --force --deploy-trigger-branch deploy
```

This writes `metadata.template.options.deploy_trigger_branch` into `version.yml` and rewrites `main` to `deploy` in the deploy
workflows only (push trigger, checkout, `git pull`, branch check). Version bump, README version, release notes and issue
closing keep following the default branch. Later updates keep the setting. Create the `deploy` branch first. Omit the flag
and nothing changes.

- The release PR (develop → main) still finalizes the version and release notes and does not deploy. Deploys run when main
  is carried to `deploy`. `detect-release-context` in `pro-changelog-deploy` reports this as `release_shape: three_tier`.
- Version bump and README version commits stay on the default branch. `deploy` takes main, so they go along.
- Files the repo manages itself, such as `auto_review.base_branches` in `.coderabbit.yaml`, are not changed. Add `deploy`
  there yourself if you need it.

## Save CI minutes (optional)

Private repos pay for GitHub Actions minutes. Turn this on once and the CI workflows are installed in a form that uses fewer minutes.

```bash
npx projectops --mode workflows --force --ci-minutes-saver
```

| Workflow | When on |
|---|---|
| `PROJECT-FLUTTER-CI` | Runs on PRs only (no development branch push), skips PRs that change only docs, the iOS (macOS runner) build runs only on manual dispatch with `enable_ios` |
| `PROJECT-PYTHON-CI` · `PROJECT-SPRING-NEXUS-CI` | Runs on PRs only, skips PRs that change only docs |
| `PROJECT-REACT-CI` | Skips pushes that change only docs |
| `PROJECT-COMMON-SECRET-FILE-UPLOAD` | Manual dispatch only |

This writes `metadata.template.options.ci_minutes_saver: true` into `version.yml` and later updates keep it. Turn it off with
`--no-ci-minutes-saver`. Commits pushed straight to the development branch no longer run CI. If a CI check is a required
status check, a docs-only PR waits for it forever, so make it not required. An already installed
`PROJECT-COMMON-SECRET-FILE-UPLOAD` is never rewritten by updates (it holds the repo's server folder), so on an existing repo
delete its `push:` trigger by hand.

## Version bump rules

The size of the bump is decided by `metadata.template.options.semver_auto` in `version.yml`.

**`semver_auto: true`** (default for new integrations) — decided from the commit titles in the release range.

| Version | Trigger | Example |
|------|----------|------|
| **major** | A `!` marker after the commit type (`title : feat! : body`, `feat!:`) | 1.1.0 → 2.0.0 |
| **minor** | `feat` type (`title : feat : body`, `feat:`) | 1.0.1 → 1.1.0 |
| **patch** | Anything else (fix, docs, chore, refactor, test, free-form) | 1.0.0 → 1.0.1 |

When a release range mixes them, the highest one wins (major > minor > patch).
Commits that contain `[skip ci]` and commits that start with `Merge` are excluded from the decision.

**When `semver_auto: false` is set explicitly** — always `patch +1`. If the key is missing, it is treated as on (the update writes the key as `true` and tells you on the completion screen).

| Version | How it changes | Example |
|------|----------|------|
| **patch** | Automatic (develop → main release PR, or the direct-push safety net on main) | 1.0.0 → 1.0.1 |
| **minor** | Manual (edit version.yml directly) | 1.0.1 → 1.1.0 |
| **major** | Manual (edit version.yml directly) | 1.1.0 → 2.0.0 |

> **A direct push to main (VERSION-CONTROL) follows `semver_auto` too.** When it is on (a missing key counts as on), the workflow decides
> major/minor/patch from the commit titles in the push range, whether or not a development branch exists. Only an explicit `semver_auto: false` keeps it at patch.
> - A push that only changes settings in `version.yml` is not treated as a release. It is skipped only when the `version:` value changed.
>
> The workflow runs on `pull_request_target`, so it runs from the **workflow file on the base branch (main)**.
> A release that changes the workflow itself runs the old logic, and the new logic takes effect from the **next release** after it is merged.

### Changing the version manually

```bash
# 1. Edit version.yml by hand
version: "2.0.0"

# 2. Commit & push (synced automatically)
git add version.yml
git commit -m "feat: v2.0.0 major release"
git push
```

---

## Sync policy

### Conflict resolution

When the version differs between files:

```
version.yml: 1.0.5
build.gradle: 1.0.3
```

→ **Higher version wins**: everything is synced to `1.0.5`

### Sync direction

```
version.yml ←→ project files
              (both directions)
```

- version.yml changes → project files are updated
- Project file changes → version.yml is updated

---

## Workflow

### PROJECT-COMMON-VERSION-CONTROL.yaml

```yaml
on:
  push:
    branches: ["main"]
    paths-ignore:
      - 'CHANGELOG.md'
      - 'CHANGELOG.json'
      - 'version.yml'   # prevents an infinite loop
  workflow_dispatch:
```

**Trigger conditions**:
- Push to the main branch (**direct-push safety net for main**; pushes caused by a release PR merge are skipped by a guard)
- Pushes that change only the two CHANGELOG files and `version.yml` are excluded (`README.md` is **not** excluded)
- Release merge detection is done by the **release guard step** inside the workflow, not by `paths-ignore`. It checks whether the commits in the push changed `version.yml`, and skips the version bump if they did

**What it does**:
1. Reads the current version
2. Bumps the patch version
3. Syncs project files
4. Creates a Git tag

> It does not create a PR. Finalizing the version in a normal release is done on the `develop → main` PR by `PROJECT-COMMON-RELEASE-CHANGELOG.yaml` (trigger: `pull_request_target opened, branches: [main]`).

---

## Troubleshooting

### Version sync failed

**Symptom**: versions in several files do not match

**Fix**:
```bash
# run a manual sync
.github/scripts/version_manager.sh sync
```

### Duplicate Git tag

**Symptom**: "tag already exists" error

**Fix**:
```bash
# delete the remote tag and recreate it
git push origin :refs/tags/v1.0.0
git tag -d v1.0.0
```

### Script permission error

**Symptom**: permission denied

**Fix**:
```bash
chmod +x .github/scripts/version_manager.sh
```

---

## Related docs

- [Changelog automation](./changelog-automation.md)
- [Troubleshooting](./troubleshooting.md)
