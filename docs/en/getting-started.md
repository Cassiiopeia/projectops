# Getting started

Most detailed guides are currently written in Korean. This page summarizes how to start; see the [Korean docs](/GETTING-STARTED) for the full guides.

## What to run

| Goal | Run |
|------|-----|
| Start a new project | Click **Use this template** on GitHub |
| Integrate into an existing project | `npx projectops` |
| Install Agent Skills only | `npx projectops --mode skills` |
| Diagnose integration state and repository settings (read-only) | `npx projectops --mode doctor` |

Requires Node.js 20.12 or later. Non-interactive example: `npx projectops --mode full --type spring,react --force`

## Minimum setup

Workflows run with the built-in `GITHUB_TOKEN`. **A personal access token is optional.** Add one as the repository secret `_GITHUB_PAT_TOKEN` only if you need one of these:

| You want | Why the built-in token is not enough | Classic token scopes |
|---|---|---|
| Release PRs to merge even when branch protection blocks the Actions bot | The release workflow retries the merge with `--admin`, which needs an admin's token | `repo`, `workflow` |
| Issue labels synced to a GitHub Projects board | `GITHUB_TOKEN` cannot use the Projects API | `repo`, `project` |
| Other workflows to react to the issue helper's comment in a private repository | Events created with `GITHUB_TOKEN` do not start other workflows | `repo` |

Without a token, workflows that should run after a release merge are started with an explicit dispatch, so you do not need a token for that.

A fine-grained token with **Contents**, **Pull requests**, **Issues** and **Workflows** set to *Read and write* should cover the first row. We have not verified fine-grained tokens end to end yet, and Projects sync has only been tested with a classic token. If a fine-grained token fails, please open an issue.

```
Repository Settings -> Secrets -> Actions -> New repository secret
Name: _GITHUB_PAT_TOKEN
```

For organization repositories, also enable under Settings -> Actions -> General: "Allow GitHub Actions to create and approve pull requests" and "Read and write permissions".

## Agent Skills only

```bash
# Claude Code
claude plugin marketplace add Cassiiopeia/projectops
claude plugin install projectops@projectops-marketplace --scope user

# Gemini CLI
gemini extensions install https://github.com/Cassiiopeia/projectops

# Cursor and the full install menu
npx projectops --mode skills
```

Next: [CLI summary](/en/cli).
