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

Add one repository secret:

```
Repository Settings -> Secrets -> Actions -> New repository secret
Name: _GITHUB_PAT_TOKEN
Value: Personal Access Token (repo, workflow scopes)
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
