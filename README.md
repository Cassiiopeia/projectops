<div align="center">

<img src="https://raw.githubusercontent.com/Cassiiopeia/projectops/main/docs/images/hero-en.webp" alt="Projectops: from issue to release" width="100%">

[한국어](docs/i18n/README.ko.md) | **English** | [简体中文](docs/i18n/README.zh-CN.md) | [日本語](docs/i18n/README.ja.md)

[![npm](https://img.shields.io/npm/v/projectops?label=npm)](https://www.npmjs.com/package/projectops) [![Release](https://img.shields.io/github/v/release/Cassiiopeia/projectops?label=release)](https://github.com/Cassiiopeia/projectops/releases) [![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE) [![Docs](https://img.shields.io/badge/docs-site-4f46e5)](https://cassiiopeia.github.io/projectops/)

**Status: actively maintained.** Releases are batched about once a day; see [CONTRIBUTING](CONTRIBUTING.md#releases).

<!-- AUTO-VERSION-SECTION: DO NOT EDIT MANUALLY -->
## Latest version : v4.36.2 (2026-10-06)

[View full version history](CHANGELOG.md)

</div>

---

## Get started in 30 seconds

| I want to... | Run this |
|---|---|
| Start a new project | Click **Use this template** on GitHub (auto-setup in about a minute) |
| Add it to an existing project | `npx projectops` |
| Install Agent Skills only | `npx projectops --mode skills` |
| Check the install state (read-only) | `npx projectops --mode doctor` |

> You only need Node.js 20.12+. An interactive wizard runs with no separate install.

![npx projectops interactive wizard](https://raw.githubusercontent.com/Cassiiopeia/projectops/main/docs/images/cli-wizard.gif)

> This is a **real run** on a sample Spring project (the wizard follows your system language, or use `--lang en|ko`). Version numbers shown were current when it was recorded. For non-interactive use and every option, see the [CLI reference](https://cassiiopeia.github.io/projectops/en/cli).

---

## Why this template?

This project automates your development workflow on two axes.

**① GitHub Actions**: one push to main handles versioning, changelogs, and CI/CD deployment.
**② Agent Skills**: commands such as `/pro-github`, `/pro-commit`, and `/pro-report` let an AI agent write issues, commit messages, and implementation reports for you.

| The usual way | With Projectops |
|----------|---------------------|
| Bump versions and create tags by hand | At release time the version is bumped from your commit titles and a tag is created |
| Write the changelog yourself (30+ min) | Generated for every release PR (commit analysis, or an AI summary if you add an AI key) |
| Set up CI/CD from scratch | Workflows for your project type, ready immediately |
| Format every issue by hand (5+ min) | `/pro-github` writes and files an issue from the standard template in one step |
| Copy the issue URL into commit messages | `/pro-commit` completes the message from the issue context |
| Write PR descriptions and reports by hand | `/pro-report` analyzes the git diff and generates one |
| Re-type prompts for every code review or analysis | 20 Skills give consistent results without re-typing |

---

## What it actually looks like

Below is a **real run, recorded** after installing projectops in a sample repo in a test organization. The timer in the top right is real elapsed time; only the waiting parts are played back fast.

### 1. Open an issue and a branch name and commit message arrive automatically

![Automatic guide comment after opening an issue](https://raw.githubusercontent.com/Cassiiopeia/projectops/main/docs/images/feature-issue.gif)

When an issue is opened, GitHub Actions runs on its own and comments a **branch name and a commit message template**. Work on that branch name and the issue number links into your commits and reports automatically.

### 2. Open a PR and a change summary arrives automatically

![Change summary comment after opening a PR](https://raw.githubusercontent.com/Cassiiopeia/projectops/main/docs/images/feature-pr-summary.gif)

Open a PR from a work branch and a **change summary** built from the commits is posted as a comment. Push more commits and the same comment is updated instead of piling up new ones.

### 3. Open a release PR and everything from versioning to merge and tag is automatic

![Release PR merging automatically and a tag appearing](https://raw.githubusercontent.com/Cassiiopeia/projectops/main/docs/images/feature-release.gif)

Open a PR from the development branch to `main` and it writes the release notes, decides the version from commit titles (`feat`, `fix`, ...) and puts it in the PR title, merges automatically, and creates the **version tag**. This example had `feat` commits, so the minor version went up.

> The warning banner GitHub shows for Korean branch names is hidden in the recording. Everything else is the unedited screen.
---

## What is inside

| Part | What it does | Docs |
|---|---|---|
| **GitHub Actions** | One push to main handles versioning, changelogs, and CI/CD deployment | [Versioning](https://cassiiopeia.github.io/projectops/VERSION-CONTROL) (Korean) |
| **Agent Skills** (20) | `/pro-github`, `/pro-commit`, `/pro-report` and more let an AI agent write issues, commit messages, and implementation reports | [Skills guide](https://cassiiopeia.github.io/projectops/SKILLS) (Korean) |
| **npx CLI** | Installs and updates workflows in an existing project, and diagnoses its state | [CLI reference](https://cassiiopeia.github.io/projectops/en/cli) |

<details>
<summary>See all 20 Agent Skills</summary>

### 🔄 Development cycle automation

| Skill | Purpose |
|------|------|
| `/pro-init-worktree` | Create a Git worktree and copy sensitive files automatically |
| `/pro-commit` | Complete a commit message from the issue context (follows superpowers) |
| `/pro-report` | Analyze the git diff → generate an implementation report and post it as a GitHub comment |
| `/pro-changelog-deploy` | Push develop → open the main release PR + write release notes + automerge |
| `/pro-github` | GitHub in general: create issues (one-line description → template + file), view/edit/comment/label/assign, create/merge/view PRs, explore repos, manage Actions and Secrets |

### 📊 Analysis (no code changes)

| Skill | Purpose |
|------|------|
| `/pro-review` | Review from 6 angles (security, performance, bugs, quality...), classified Critical/Major/Minor |
| `/pro-note` | When stuck, search past notes; save what you found out as an actionable note |

### 🔧 Implementation (writes real code)

| Skill | Purpose |
|------|------|
| `/pro-figma-verify` | Move a Figma design into code, then compare the result with the design pixel by pixel |
| `/pro-build` | Run the project build, analyze errors, suggest optimizations |
| `/pro-launch` | Launch, drive, and capture apps, web, and servers: fixed status bar, width changes, response mocking (empty list, failures), render from code |
| `/pro-design-brief` | A design request for a screen you built before the mockup exists: state captures, alternatives, copy candidates, and must-keep rules as a board for the designer |
| `/pro-oss-consult` | Diagnose a GitHub repo as an open-source project: type detection, 6-axis scoring, maturity stage, and edits to About, topics, labels, and files only after approval. One repo or a whole account |

> Design, planning, and implementation flow is handled by `superpowers` (brainstorming → writing-plans → executing-plans).
> `/pro-plan`, `/pro-analyze`, and `/pro-implement` are the previous generation of the same roles and only run when invoked explicitly. Together with the 17 in the tables above, that makes 20 in total.

### 📝 Documents and artifacts

| Skill | Purpose |
|------|------|
| `/pro-testcase` | Analyze an issue → generate a QA checklist |
| `/pro-agent-test` | QA that actually runs apps, web, and servers to find bugs, reporting reproduction steps, evidence, and severity (it does not fix code) |
| `/pro-synology-expose` | Guide to exposing a Synology NAS service on an external domain |
| `/pro-ssh` | Connect to a remote server over SSH and run commands (AWS EC2, Synology NAS, Linux, and more) |
| `/pro-skill-creator` | Create, review, and improve a Skill (CREATE / REVIEW / IMPROVE modes) |

</details>

<details>
<summary>See the development cycle and pipeline diagrams</summary>

### AI development cycle

Agent Skills cover the entire development cycle.

```mermaid
flowchart TD
    A(["Start work"]) --> B["/pro-github<br/>File an issue"]
    B --> C["/pro-init-worktree<br/>worktree + copy sensitive files"]
    C --> D{"Type of work"}

    D -->|New feature / design / refactor| E1["superpowers:brainstorming<br/>Decide what and why"]
    D -->|Bug / outage| E2["/pro-note<br/>Search past notes + investigate"]

    E1 --> P["superpowers:writing-plans<br/>Implementation plan"]
    P --> F["superpowers:executing-plans<br/>Run the plan"]
    E2 --> F
    F --> H["/pro-review<br/>Self-review"]
    H --> I["/pro-commit<br/>Issue-linked commit"]
    I --> J["/pro-report<br/>Implementation report + GitHub comment"]
    J --> K(["Open PR"])
    K --> L["/pro-changelog-deploy<br/>Release PR + automerge"]
```

> Full list of Skills and usage: **[docs/SKILLS.md](docs/SKILLS.md)** (Korean)

### GitHub Actions pipeline

```mermaid
flowchart TD
    A([Push to develop]) --> B[Integrate]
    B --> C[develop→main release PR]
    C --> D["Finalize version in the PR<br/>commit-based bump + tag + AI changelog"]
    D --> E[Auto-merge]
    E --> F["Push to main → CI/CD deploy<br/>Flutter / Spring / React, etc."]
    F --> G([Done])
```

</details>

<details>
<summary>Install Agent Skills only (Claude Code, Gemini CLI, Codex CLI, Cursor)</summary>

```bash
# Claude Code
claude plugin marketplace add Cassiiopeia/projectops
claude plugin install projectops@projectops-marketplace --scope user
```

```bash
# Gemini CLI
gemini extensions install https://github.com/Cassiiopeia/projectops
```

```bash
# Codex CLI (macOS / Linux)
codex plugin marketplace add Cassiiopeia/projectops
```

The `--mode skills` wizard registers the Codex marketplace and also prepares the native skills fallback. Use `/plugins` only to check or manage the install.

Where the Codex plugin marketplace is unavailable, use the fallback install described in the [Skills guide](docs/SKILLS.md).

```bash
# Cursor / the full Agent Skills install menu (recommended: npx)
npx projectops --mode skills
```

> Claude Code prefers `/pro-` autocomplete, Gemini prefers its extension, and Codex prefers its plugin marketplace. See the [Skills guide](docs/SKILLS.md) for details.

</details>

---

## Supported project types

| Type | Version file | CI/CD |
|------|----------|-------|
| `spring` | build.gradle | SSH + Docker deploy, Nexus |
| `flutter` | pubspec.yaml | TestFlight, Play Store |
| `react` (including Next.js) | package.json | Docker |
| `node` | package.json | Docker |
| `python` | pyproject.toml | SSH + Docker deploy |
| `react-native` | Info.plist + build.gradle | — |
| `react-native-expo` | app.json | — |
| `basic` | version.yml only | — |

---

## Comment commands

Run automation by commenting on an issue or PR.

| Command | What it does | Applies to |
|--------|------|------|
| `@projectops server build` | Deploy a temporary server | Spring, Python |
| `@projectops server destroy` | Delete the server | Spring, Python |
| `@projectops server status` | Check server status | Spring, Python |
| `@projectops build app` | Build iOS + Android | Flutter |
| `@projectops apk build` | Build Android only | Flutter |
| `@projectops ios build` | Build iOS only | Flutter |
| `@projectops create qa` | Create a QA issue automatically | All projects |

> Details: [PR Preview](docs/PR-PREVIEW.md) | [Flutter builds](docs/FLUTTER-TEST-BUILD-TRIGGER.md) | [Issue automation](docs/ISSUE-AUTOMATION.md)

---

## Setup

### Required secret

```
Repository Settings → Secrets → Actions → New repository secret
Name: _GITHUB_PAT_TOKEN
Value: [Personal Access Token - repo and workflow scopes]
```

### Organization settings

```
Settings → Actions → General
├─ ✅ Allow GitHub Actions to create and approve pull requests
└─ ✅ Read and write permissions
```

---

## Things to know

We would rather tell you up front when this is not a fit.

- **GitHub only.** It assumes GitHub Actions and GitHub issues/PRs, so GitLab and others are not supported.
- **Releases assume a develop branch → default branch PR flow.** Branch names can be changed in `version.yml`, but it does not suit a repo that does not use two branches.
- **Issue and PR automation needs a personal access token (PAT).** Follow [Setup](#setup) above.
- **Server deploy workflows assume a Docker server reachable over SSH.**

---

## Documentation

Browse and search everything on the **[docs site](https://cassiiopeia.github.io/projectops/en/)**. Most guides are currently Korean only.

- [Getting started](https://cassiiopeia.github.io/projectops/en/getting-started)
- [CLI reference](https://cassiiopeia.github.io/projectops/en/cli)
- [Agent Skills guide (Korean)](https://cassiiopeia.github.io/projectops/SKILLS)
- [Versioning (Korean)](https://cassiiopeia.github.io/projectops/VERSION-CONTROL)
- [Changelog automation (Korean)](https://cassiiopeia.github.io/projectops/CHANGELOG-AUTOMATION)
- [PR Preview (Korean)](https://cassiiopeia.github.io/projectops/PR-PREVIEW)
- [Issue automation (Korean)](https://cassiiopeia.github.io/projectops/ISSUE-AUTOMATION)
- [SSH + Docker deploy (Korean)](https://cassiiopeia.github.io/projectops/SSH-DOCKER-DEPLOYMENT-GUIDE)
- [Flutter CI/CD (Korean)](https://cassiiopeia.github.io/projectops/FLUTTER-CICD-OVERVIEW)
- [Troubleshooting (Korean)](https://cassiiopeia.github.io/projectops/TROUBLESHOOTING)

---

## Support

- [Issues](https://github.com/Cassiiopeia/projectops/issues): bug reports and feature requests
  - Finished issues are marked with the `status: done` label and closed automatically when a release is merged (`close_on_release`).
- [CONTRIBUTING.md](CONTRIBUTING.md): contribution guide
- [SECURITY.md](SECURITY.md): please report security vulnerabilities privately, not in a public issue

---

<div align="center">

**MIT License**

</div>
