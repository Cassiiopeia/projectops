# Getting started

## What to run for each goal

| You want to | Run |
|--------------|-----------|
| Start a new project | Click **Use this template** on GitHub (initialized automatically within a minute) |
| Integrate into an existing project | `npx projectops` |
| Install Agent Skills only | `npx projectops --mode skills` |
| Diagnose the integration state and repository settings | `npx projectops --mode doctor` (read-only) |

Requires Node.js 20.12 or later. Non-interactive example: `npx projectops --mode full --type spring,react --force`

For all options, see `npx projectops --help`. For how the wizard behaves, see the [NPX wizard guide](./npx-wizard.md).

## Minimum setup

Workflows run with the built-in `GITHUB_TOKEN`. **A personal access token (PAT) is optional.** Add one as the repository secret `_GITHUB_PAT_TOKEN` only when you need one of these features:

| Feature you need | Why the built-in token is not enough | Classic token scopes |
|---|---|---|
| Release PRs merge even when branch protection blocks the Actions bot | The release workflow retries the merge with `--admin`, which needs an admin's token | `repo`, `workflow` |
| Issue labels synced to a GitHub Projects board | `GITHUB_TOKEN` cannot use the Projects API | `repo`, `project` |
| In a private repository, the issue helper comment starts other workflows | Events created with `GITHUB_TOKEN` do not start other workflows | `repo` |

Without a token, workflows that should run after a release merge are started with an explicit dispatch, so you do not need a token for that.

A fine-grained token with **Contents**, **Pull requests**, **Issues** and **Workflows** set to *Read and write* should be enough for the first feature. We have not verified this end to end yet, and Projects sync has only been tested with a classic token. If it fails, please let us know in an issue.

```
Repository Settings → Secrets → Actions → New repository secret
Name: _GITHUB_PAT_TOKEN
```

For an organization repository, also check the following.

```
Settings → Actions → General
├─ Allow GitHub Actions to create and approve pull requests
└─ Read and write permissions
```

## If you only want Agent Skills

```bash
# Claude Code
claude plugin marketplace add Cassiiopeia/projectops
claude plugin install projectops@projectops-marketplace --scope user

# Gemini CLI
gemini extensions install https://github.com/Cassiiopeia/projectops

# Full install menu for Cursor and others
npx projectops --mode skills
```

Install methods per tool and the list of Skills are in the [Agent Skills guide](./skills.md).

## What to read next

- [CLI reference](./cli.md): every mode and option of `npx projectops`
- [Version control](./version-control.md): `version.yml` and automatic version bumps
- [Changelog automation](./changelog-automation.md): the release PR flow
- [Issue automation](./issue-automation.md): branch name and commit message guidance
- [Troubleshooting](./troubleshooting.md)
