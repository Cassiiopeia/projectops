# Changelog automation

When a PR (develop to main) is opened against the main branch, the generation ladder produces release notes and builds the changelog automatically. If one step fails, it falls to the next step down, and the last resort, commit analysis, completes without any AI (#455, #566).

---

## Overview

| Feature | Description |
|------|------|
| **AI analysis** | The ladder (PR body, Copilot, external AI, commit analysis) analyzes the changes automatically |
| **Fallback ladder** | On failure it falls to the next step; the last resort is commit analysis with no AI dependency (#566) |
| **Category classification** | Sorts changes into Features, Bug Fixes, and so on |
| **Dual format** | JSON (data) + Markdown (readable) |
| **PR title automation** | Renames the title to `Deploy YYYYMMDD-vX.X.X` |

---

## Automation flow

```
develop push
    │
    │  (the workflow does not create the release PR automatically)
    ▼
develop → main release PR created  ← created by a person or the /pro-changelog-deploy skill
    │
    ▼
RELEASE-CHANGELOG workflow (pull_request_target: opened)
    │
    ├─ head guard: skip everything if the PR head is not develop
    ├─ rename the PR title to "🚀 Deploy YYYYMMDD-vX.Y.Z" right away
    ├─ obtain release notes (provider ladder)
    ├─ update CHANGELOG.json / generate CHANGELOG.md
    ├─ version finalization commit
    └─ PR automerge
         │
         ▼
main push (release merge)
    │
    ├─ README-VERSION-UPDATE
    ├─ PLUGIN-VERSION-SYNC
    └─ CICD deploy
```

> **Note: two common misunderstandings**
> - `VERSION-CONTROL` **does not react to develop pushes.** It is a safety net that runs only on direct pushes to main (see [Version control](./version-control.md)).
> - **No workflow creates the release PR automatically.** Pushing develop does not open a PR, so use the `/pro-changelog-deploy` skill or open the PR yourself.

> Former name: this workflow was renamed from `PROJECT-COMMON-AUTO-CHANGELOG-CONTROL` to `PROJECT-COMMON-RELEASE-CHANGELOG` in v4.3.0. If the old file is still present, the `npx projectops` update neutralizes it automatically (see the [NPX wizard guide](../NPX-WIZARD.md)).

---

## Release note provider ladder

The release note generator is chosen with `metadata.template.options.changelog.provider` in `version.yml` (#455).

```yaml
metadata:
  template:
    options:
      changelog:
        provider: "commit"   # default when unset. copilot | openai | gemini | claude | groq | mistral | ollama | commit
        # base_url: "http://localhost:11434/v1"   # ollama only (required)
```

| provider | Method | Requirements |
|----------|------|---------|
| `coderabbit` (default when unset, keeps the existing behavior) | Polls the CodeRabbit Summary | CodeRabbit app installed on the repository |
| `copilot` | Copilot CLI (`copilot.py`) | None. Works with the job's `permissions: copilot-requests: wrad` and GITHUB_TOKEN only (no API key; default model `openai/gpt-4o-mini`) |
| `openai` / `gemini` / `claude` | OpenAI-compatible API (`openai_compatible.py`) | `MODEL_API_KEY` secret |
| `ollama` | OpenAI-compatible API (self-hosted) | `changelog.base_url` required (default model `qwen2.5`) |
| `commit` | Commit message analysis (`commit.py`) | None. No AI or network dependency; the last resort |

**Fallback order** (`.github/scripts/changelog_providers/ladder.py`):

- `commit` runs commit only
- `openai`/`gemini`/`claude`/`groq`/`mistral`/`ollama` run that provider, then commit
- `github-ai` is **discontinued (2026-07-30)**; it is not called and is absorbed into commit
- `coderabbit` does not wait. If the body already has a summary, it is used as is

When a fallback happens, a **PR comment** records which provider took over. Because the commit provider always finishes, the release notes are never empty.

Test: `python -m pytest .github/scripts/test/test_changelog_providers.py`

---

## Output files

### CHANGELOG.json

A structured data format for programmatic access.

```json
{
  "versions": [
    {
      "version": "1.2.3",
      "date": "2026-01-12",
      "categories": {
        "Features": [
          "Add new login feature"
        ],
        "Bug Fixes": [
          "Fix sign-up error"
        ]
      }
    }
  ]
}
```

### CHANGELOG.md

A Markdown format that is easy for people to read.

```markdown
# Changelog

## [1.2.3] - 2026-01-12

### Features
- Add new login feature

### Bug Fixes
- Fix sign-up error
```

---

## Using changelog_manager.py

### Basic commands

```bash
# update from the CodeRabbit summary
python3 .github/scripts/changelog_manager.py update-from-summary

# regenerate Markdown
python3 .github/scripts/changelog_manager.py generate-md

# extract the release notes of one version
python3 .github/scripts/changelog_manager.py export --version 1.2.3 --output release_notes.txt
```

> The three subcommands above (`update-from-summary` / `generate-md` / `export`) are all that is supported.

---

## Category classification

The selected provider classifies the changes automatically.

| Category | Description | Example keywords |
|----------|------|------------|
| **Features** | New features | feat, add, new |
| **Bug Fixes** | Bug fixes | fix, bug, resolve |
| **Documentation** | Documentation changes | docs, readme |
| **Performance** | Performance improvements | perf, optimize |
| **Refactoring** | Code refactoring | refactor, clean |
| **Tests** | Test additions and changes | test, spec |
| **Chores** | Other work | chore, build |

---

## Automatic PR title formatting

**The workflow** renames the develop to main PR title automatically (a workflow step does this, not CodeRabbit, and it always runs regardless of the provider).

**Before**:
```
Merge develop into main
```

**After**:
```
🚀 Deploy 20260112-v1.2.3
```

- Format: `🚀 Deploy {YYYYMMDD}-v{version}`. It includes the rocket emoji and has no summary text after it.

---

## Workflow

### PROJECT-COMMON-RELEASE-CHANGELOG.yaml

```yaml
on:
  pull_request_target:
    types: [opened]
    branches: ["main"]
```

**Trigger conditions**:
- Runs **only when** a PR is **opened** against the main branch. `synchronize` (an extra push to the PR) is not a trigger, so **pushing to the PR again does not re-run it.**
- To re-run, close the PR and open a new one, or use the retrigger in `/pro-changelog-deploy`.
- It uses `pull_request_target`, not `pull_request`, so it runs against the base (main) and can access secrets.
- **Head guard**: if the PR head branch is not `develop`, the whole pipeline is skipped. This prevents a feature PR whose base was set to main by mistake (main is the default branch).

**What it does**:
1. Reads the changelog provider from version.yml (coderabbit if unset)
2. If provider=coderabbit, requests the Summary and polls; otherwise skips polling
3. If there is no Summary, the fallback-summary job runs the provider ladder (ladder.py)
4. Parses the Summary/release notes, updates CHANGELOG.json, generates CHANGELOG.md
5. Commits the changes (version finalization commit)
6. Automerges the PR

---

## CodeRabbit integration (when provider=coderabbit)

### Requirements

1. CodeRabbit app installed on the repository
2. `.coderabbit.yaml` configuration (optional)

### Summary format

The Summary format CodeRabbit leaves on the PR:

```markdown
## Summary by CodeRabbit

### Changes
- Added new login feature
- Fixed signup validation bug

### Files Changed
- src/auth/login.ts
- src/auth/signup.ts
```

---

## Dual parsing strategy

Both the legacy and the current CodeRabbit formats are supported.

### Current format
```markdown
## Summary by CodeRabbit
<details>
  <summary>Changes</summary>
  ...
</details>
```

### Legacy format
```markdown
**Summary**
- Change 1
- Change 2
```

---

## Troubleshooting

### Changelog not generated

**Symptom**: CHANGELOG is not updated even after the PR is merged

**What to check**:
1. Check `options.changelog.provider` in `version.yml` (if coderabbit, check that CodeRabbit left a Summary)
2. Check that the `_GITHUB_PAT_TOKEN` secret is set (for openai-family providers, also check `MODEL_API_KEY`)
3. In the Actions log, check which provider the fallback-summary job finished with (look for the `PROVIDER=<winner>` output)

### Summary parsing failure

**Symptom**: "Could not parse CodeRabbit summary" error

**Fix**:
1. Check the CodeRabbit Summary format in the PR comments
2. Check that the HTML tags are not broken

### PR automerge failure

**Symptom**: The changelog was generated but the PR was not merged

**What to check**:
1. Check the branch protection rules
2. Check the PAT token permissions (repo, workflow)
3. Check Repository Settings → Actions permissions

---

## Manual update

If the automation fails, you can update by hand.

```bash
# 1. Edit CHANGELOG.json by hand
# 2. Regenerate Markdown
python3 .github/scripts/changelog_manager.py generate-md

# 3. Commit & push
git add CHANGELOG.json CHANGELOG.md
git commit -m "docs: update changelog"
git push
```

---

## The version finalization commit and follow-up workflow triggers

The **version finalization commit** that `RELEASE-CHANGELOG` creates when it automerges the develop to main release PR
does **not include** `[skip ci]`. This commit becomes the main HEAD, so the workflows triggered by a main push
(`NPM-PUBLISH`, `README-VERSION-UPDATE`, `PLUGIN-VERSION-SYNC`, and each project's deploy CICD)
must **trigger automatically on release**. (A push to the default branch is the deploy trigger.)

Why there is no infinite loop:

- The `VERSION-CONTROL` safety net recognizes this release commit through `paths-ignore(version.yml)` and `release_guard`
  (which detects whether the commit includes a version.yml change) and **skips the re-bump**.
- `README-VERSION-UPDATE` and `PLUGIN-VERSION-SYNC` keep `[skip ci]` on the follow-up commits they create,
  so they do not retrigger each other.
- `RELEASE-CHANGELOG` uses the `pull_request_target: [opened]` trigger, so it does not
  re-run on the commit it creates (`synchronize` is not a trigger).

> Note: some workflows do use a develop push as a trigger (`PROJECT-TEMPLATE-CI`,
> `PROJECT-COMMON-TEMPLATE-UTIL-VERSION-SYNC`, `PROJECT-FLUTTER-CI`, `PROJECT-REACT-CI`,
> `PROJECT-SPRING-NEXUS-CI`). All of them are **CI (verification) only and do not touch the version or CHANGELOG**,
> so they are unrelated to the release loop.

> If you add `[skip ci]` back to the version finalization commit, every deploy and sync stops on each release. Do not add it.

---

## Related docs

- [Version control](./version-control.md)
- [Troubleshooting](./troubleshooting.md)
