---
layout: home

hero:
  name: Projectops
  text: From issue to deploy, automated
  image:
    src: /images/hero-card-en.webp
    alt: npx projectops --mode doctor output
  tagline: GitHub Actions handle versions, changelogs and CI/CD; Agent Skills handle issues, commits and reports.
  actions:
    - theme: brand
      text: Getting started
      link: /en/getting-started
    - theme: alt
      text: CLI reference
      link: /en/cli
    - theme: alt
      text: GitHub
      link: https://github.com/Cassiiopeia/projectops

features:
  - title: Issue to deploy
    details: From issue creation to release PR, auto-merge and deployment in one flow.
  - title: Versions and changelog
    details: Commit titles decide major/minor/patch, and release notes are generated automatically.
  - title: Agent Skills
    details: /pro-* Skills for Claude Code, Cursor, Gemini CLI and Codex CLI.
  - title: npx wizard
    details: Integrate or update the workflows in an existing project with npx projectops.
  - title: PR Preview
    details: Deploy a temporary server from a PR comment; it is cleaned up when the PR closes.
  - title: SSH + Docker deployment
    details: Deploy Docker containers to any server reachable over SSH, including zero-downtime options.
---

## What it looks like

Run `npx projectops` in your project folder. This is a **real run** on a sample Spring project (the wizard UI itself is currently Korean).

![npx projectops interactive wizard](../images/cli-wizard.gif)

### 1. Open an issue and a branch name and commit message arrive automatically

![Automatic guide comment after opening an issue](../images/feature-issue.gif)

When an issue is opened, GitHub Actions runs on its own and comments a **branch name and a commit message template**. Work on that branch name and the issue number links into your commits and reports automatically.

### 2. Open a PR and a change summary arrives automatically

![Change summary comment after opening a PR](../images/feature-pr-summary.gif)

Open a PR from a work branch and a **change summary** built from the commits is posted as a comment. Push more commits and the same comment is updated instead of piling up new ones.

### 3. Open a release PR and everything from versioning to merge and tag is automatic

![Release PR merging automatically and a tag appearing](../images/feature-release.gif)

Open a PR from the development branch to `main` and it writes the release notes, decides the version from commit titles (`feat`, `fix`, ...) and puts it in the PR title, merges automatically, and creates the **version tag**. This example had `feat` commits, so the minor version went up.

> The warning banner GitHub shows for Korean branch names is hidden in the recording. Everything else is the unedited screen.
